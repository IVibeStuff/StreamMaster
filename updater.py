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

CURRENT_VERSION  = "2.2"
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
    Write a Python restart script instead of a bat file.
    Python is guaranteed to be available and handles paths correctly
    on all Windows configurations without shell escaping issues.
    """
    extracted = stage_dir / 'extracted'
    script_path = stage_dir / 'restart.py'

    script = f"""
import os, sys, time, shutil, subprocess
from pathlib import Path

INSTALL_DIR = Path(r"{INSTALL_DIR}")
STAGE_DIR   = Path(r"{stage_dir}")
EXTRACTED   = Path(r"{extracted}")
CACHE_FILE  = Path(r"{CACHE_FILE}")

print("=" * 50)
print("  StreamMaster Auto-Update")
print("=" * 50)
print(f"  Install: {{INSTALL_DIR}}")
print(f"  Stage:   {{STAGE_DIR}}")
print()

# Wait for server to exit
print("  Waiting for server to exit...")
time.sleep(5)

# Backup history
hist_src = INSTALL_DIR / "history.json"
hist_bak = STAGE_DIR / "history_backup.json"
if hist_src.exists():
    shutil.copy2(str(hist_src), str(hist_bak))
    print("  History backed up.")

# Find source directory (may be flat or have one subfolder)
src = EXTRACTED
for item in EXTRACTED.iterdir():
    if item.is_dir() and (item / "server.py").exists():
        src = item
        break

print(f"  Source: {{src}}")

if not (src / "server.py").exists():
    print(f"  ERROR: server.py not found in {{src}}")
    print("  Contents of extracted:")
    for f in EXTRACTED.rglob("*"):
        print(f"    {{f}}")
    input("  Press Enter to exit...")
    sys.exit(1)

# Copy files
print("  Copying files...")
try:
    for item in src.iterdir():
        dst = INSTALL_DIR / item.name
        if item.is_file():
            shutil.copy2(str(item), str(dst))
        elif item.is_dir():
            if dst.exists():
                shutil.rmtree(str(dst))
            shutil.copytree(str(item), str(dst))
    print(f"  Files copied OK.")
except Exception as e:
    print(f"  ERROR copying files: {{e}}")
    input("  Press Enter to exit...")
    sys.exit(1)

# Restore history
if hist_bak.exists():
    shutil.copy2(str(hist_bak), str(hist_src))
    print("  History restored.")

# Clear update cache
if CACHE_FILE.exists():
    CACHE_FILE.unlink()
    print("  Cache cleared.")

# Relaunch
print()
print("  Relaunching StreamMaster...")
vbs = INSTALL_DIR / "Launch_Silent.vbs"
bat = INSTALL_DIR / "Launch.bat"

if vbs.exists():
    print(f"  Using: {{vbs}}")
    subprocess.Popen(["wscript.exe", str(vbs)])
elif bat.exists():
    print(f"  Using: {{bat}}")
    subprocess.Popen([str(bat)], shell=True)
else:
    print("  WARNING: No launcher found!")

print()
print("  Update complete. Cleaning up...")
time.sleep(3)
try:
    shutil.rmtree(str(STAGE_DIR))
except Exception:
    pass
print("  Done.")
"""
    script_path.write_text(script, encoding='utf-8')
    return script_path


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
