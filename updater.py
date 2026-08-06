"""
updater.py — Auto-update system for StreamMaster.

Checks the GitHub releases API for the latest official release tag.
Compares against the running version. If newer, notifies the browser UI.
Update is always user-initiated — never silent.

Update process:
  1. Browser calls /check_update → returns {current, latest, update_available, url}
  2. User clicks Update in the UI banner
  3. Browser calls /apply_update → downloads zip, extracts to staging folder,
     writes a restart.bat that swaps files and restarts the server,
     returns {status: 'restart_pending'}
  4. Server calls restart.bat via subprocess and exits
  5. restart.bat waits for server to exit, copies new files, relaunches
"""

import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

CURRENT_VERSION  = "2.0"
GITHUB_REPO      = "IVibeStuff/StreamMaster"
API_URL          = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
CACHE_FILE       = Path(__file__).parent / ".update_cache.json"
CACHE_TTL_HOURS  = 24
INSTALL_DIR      = Path(__file__).parent


# ── Version comparison ─────────────────────────────────────────────────────────

def _parse_version(tag: str) -> tuple:
    """Parse a version tag like 'v2.1', 'V2.0.1' or '2.1.3' into a comparable tuple."""
    tag = tag.lstrip('vV').strip()  # handle both v2.0 and V2.0.1
    parts = re.findall(r'\d+', tag)
    return tuple(int(p) for p in parts)


def is_newer(latest_tag: str, current: str = CURRENT_VERSION) -> bool:
    """Return True if latest_tag is strictly newer than current."""
    try:
        return _parse_version(latest_tag) > _parse_version(current)
    except Exception:
        return False


# ── GitHub API ─────────────────────────────────────────────────────────────────

def _fetch_latest_release() -> dict:
    """
    Fetch the latest official release from GitHub.
    Returns dict with keys: tag_name, html_url, assets (list of asset dicts).
    Raises on network error.
    """
    req = urllib.request.Request(
        API_URL,
        headers={
            'User-Agent': f'StreamMaster/{CURRENT_VERSION}',
            'Accept':     'application/vnd.github+json',
        }
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read().decode())


def _get_zip_asset(release: dict) -> dict | None:
    """Find the zip release asset (SpotifyMaster.zip or StreamMaster*.zip)."""
    for asset in release.get('assets', []):
        name = asset.get('name', '').lower()
        if name.endswith('.zip'):
            return asset
    return None


def _read_cache() -> dict:
    try:
        if CACHE_FILE.exists():
            data = json.loads(CACHE_FILE.read_text())
            age_hours = (time.time() - data.get('ts', 0)) / 3600
            if age_hours < CACHE_TTL_HOURS:
                return data
    except Exception:
        pass
    return {}


def _write_cache(data: dict) -> None:
    try:
        data['ts'] = time.time()
        CACHE_FILE.write_text(json.dumps(data))
    except Exception:
        pass


# ── Public API ─────────────────────────────────────────────────────────────────

# Shared state — populated by background thread on startup
_update_state = {
    'checked':          False,
    'update_available': False,
    'current_version':  CURRENT_VERSION,
    'latest_version':   None,
    'release_url':      None,
    'asset_url':        None,
    'asset_name':       None,
    'error':            None,
}
_state_lock = threading.Lock()


def get_update_state() -> dict:
    with _state_lock:
        return dict(_update_state)


def check_for_updates_background() -> None:
    """
    Run the update check in a background thread.
    Called once on server startup. Result stored in _update_state.
    """
    def _run():
        # Try cache first
        cached = _read_cache()
        if cached.get('checked'):
            with _state_lock:
                _update_state.update(cached)
            print(f"  Updater    : cached result — "
                  f"{'update available: ' + cached.get('latest_version','?') if cached.get('update_available') else 'up to date'}")
            return

        try:
            release  = _fetch_latest_release()
            tag      = release.get('tag_name', '')
            html_url = release.get('html_url', '')
            asset    = _get_zip_asset(release)
            avail    = is_newer(tag)

            result = {
                'checked':          True,
                'update_available': avail,
                'current_version':  CURRENT_VERSION,
                'latest_version':   tag.lstrip('vV'),
                'release_url':      html_url,
                'asset_url':        asset['browser_download_url'] if asset else None,
                'asset_name':       asset['name'] if asset else None,
                'error':            None,
            }
            with _state_lock:
                _update_state.update(result)
            _write_cache(result)

            if avail:
                print(f"  Updater    : update available → v{tag.lstrip('vV')} "
                      f"(running v{CURRENT_VERSION})")
            else:
                print(f"  Updater    : up to date (v{CURRENT_VERSION})")

        except Exception as e:
            err_str = str(e)
            # 404 means no releases published yet — not a real error
            if '404' in err_str:
                print(f"  Updater    : no releases found on GitHub yet — skipping")
            else:
                with _state_lock:
                    _update_state['checked'] = True
                    _update_state['error']   = err_str
                print(f"  Updater    : check failed — {e}")

    threading.Thread(target=_run, daemon=True).start()


def download_and_stage(asset_url: str, asset_name: str) -> Path:
    """
    Download the release zip to a staging directory.
    Returns path to the staging directory containing extracted files.
    """
    stage_dir = Path(tempfile.mkdtemp(prefix='sm_update_'))
    zip_path  = stage_dir / asset_name

    print(f"  Updater    : downloading {asset_name}…")
    req = urllib.request.Request(
        asset_url,
        headers={'User-Agent': f'StreamMaster/{CURRENT_VERSION}'}
    )
    with urllib.request.urlopen(req, timeout=120) as resp, \
         open(zip_path, 'wb') as out:
        shutil.copyfileobj(resp, out)

    print(f"  Updater    : extracting…")
    import zipfile
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(stage_dir / 'extracted')

    zip_path.unlink()
    return stage_dir


def write_restart_script(stage_dir: Path) -> Path:
    """
    Write a Windows .bat script that:
      1. Waits for the server process to exit
      2. Copies new files from staging over the install directory
      3. Preserves history.json
      4. Relaunches via Launch_Silent.vbs or Launch.bat
      5. Cleans up the staging directory

    Returns path to the .bat file.
    """
    extracted = stage_dir / 'extracted'
    bat_path  = stage_dir / 'restart.bat'

    # Find the extracted subfolder (zip may have a top-level folder)
    subdirs = [d for d in extracted.iterdir() if d.is_dir()]
    src_dir = subdirs[0] if subdirs else extracted

    script = f"""@echo off
chcp 65001 >nul
title StreamMaster Update
echo.
echo  Applying StreamMaster update...
echo.

REM Wait for server to exit (up to 10 seconds)
timeout /t 3 /nobreak >nul

REM Preserve history before copying
set HISTORY="{INSTALL_DIR / 'history.json'}"
set HISTORY_TMP="{stage_dir / 'history_backup.json'}"
if exist %HISTORY% copy /Y %HISTORY% %HISTORY_TMP% >nul

REM Copy new files
xcopy /E /Y /I "{src_dir}\\*" "{INSTALL_DIR}\\" >nul

REM Restore history
if exist %HISTORY_TMP% copy /Y %HISTORY_TMP% %HISTORY% >nul

REM Clear update cache so next launch re-checks
del /Q "{CACHE_FILE}" >nul 2>&1

echo  Update complete. Restarting StreamMaster...
timeout /t 1 /nobreak >nul

REM Relaunch
if exist "{INSTALL_DIR / 'Launch_Silent.vbs'}" (
    start "" wscript.exe "{INSTALL_DIR / 'Launch_Silent.vbs'}"
) else (
    start "" "{INSTALL_DIR / 'Launch.bat'}"
)

REM Clean up staging
timeout /t 3 /nobreak >nul
rd /S /Q "{stage_dir}" >nul 2>&1
"""
    bat_path.write_text(script, encoding='utf-8')
    return bat_path


def apply_update(asset_url: str, asset_name: str) -> dict:
    """
    Download, stage, and prepare the update.
    Writes restart.bat and returns its path for the server to execute.
    The server should call this then run the bat and exit.
    """
    stage_dir  = download_and_stage(asset_url, asset_name)
    bat_path   = write_restart_script(stage_dir)
    return {
        'status':     'restart_pending',
        'bat_path':   str(bat_path),
        'stage_dir':  str(stage_dir),
    }
