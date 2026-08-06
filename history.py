"""
history.py — Mastering history store for StreamMaster.

Reads and writes history.json in the tool's install directory.
Each entry records the full parameter set used, input/output filenames,
timestamps, LUFS, QC result, and engine detection.

Entries are grouped by source filename in the UI but stored flat
chronologically in the JSON file. Maximum 100 entries — oldest dropped.
"""

import json
import os
from pathlib import Path
from datetime import datetime, timezone

MAX_ENTRIES = 100
HISTORY_FILE = Path(__file__).parent / 'history.json'


def _load() -> list:
    """Load history from disk. Returns empty list if file missing or corrupt."""
    try:
        if HISTORY_FILE.exists():
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
    except Exception:
        pass
    return []


def _save(entries: list) -> None:
    """Write history to disk."""
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)


def add_entry(
    source_file: str,
    output_files: list,       # list of output filenames (streaming, local, or both)
    settings: dict,           # full parameter dict sent to master()
    analysis: dict = None,    # analyser result (optional)
    qc: dict = None,          # QC result (optional)
) -> dict:
    """
    Add a mastering entry to history.

    Returns the new entry dict.
    """
    entry = {
        'id':           _make_id(),
        'timestamp':    datetime.now(timezone.utc).isoformat(),
        'source_file':  os.path.basename(source_file),
        'output_files': [os.path.basename(f) for f in output_files],
        'settings':     _clean_settings(settings),
        'analysis':     _summarise_analysis(analysis) if analysis else None,
        'qc_passed':    _qc_passed(qc),
        'qc_issues':    (qc or {}).get('issues', []),
    }

    entries = _load()
    entries.insert(0, entry)          # newest first
    entries = entries[:MAX_ENTRIES]   # trim to limit
    _save(entries)
    return entry


def get_all() -> list:
    """Return all history entries, newest first."""
    return _load()


def get_grouped() -> dict:
    """
    Return entries grouped by source filename.
    Returns: dict of {source_file: [entry, ...]} ordered by most recent.
    """
    entries = _load()
    groups = {}
    for e in entries:
        key = e.get('source_file', 'Unknown')
        if key not in groups:
            groups[key] = []
        groups[key].append(e)
    return groups


def clear_all() -> None:
    """Delete all history entries."""
    _save([])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_id() -> str:
    import uuid
    return str(uuid.uuid4())[:8]


def _clean_settings(s: dict) -> dict:
    """Keep only the mastering parameters, cast to reasonable precision."""
    keys = [
        'presence_gain', 'deess_threshold', 'vocal_boost_db', 'macro_target_db',
        'eq_shelf_db', 'eq_mud_db', 'air_blend', 'dehaze_depth',
        'sat_drive_db', 'sat_mix', 'comp_threshold', 'comp_ratio',
        'transient_boost', 'dyneq_max_cut', 'bass_side_mix',
        'hishelf_threshold', 'profile',
    ]
    return {k: _round(s[k]) for k in keys if k in s}


def _round(v):
    if isinstance(v, float):
        return round(v, 3)
    return v


def _summarise_analysis(a: dict) -> dict:
    """Extract the key facts from an analysis result for display."""
    if not a:
        return None
    loudness = a.get('loudness', {})
    engine   = a.get('engine', {})
    return {
        'lufs':         round(loudness.get('lufs', 0), 1),
        'dr':           round(loudness.get('dynamic_range_db', 0), 1),
        'engine':       engine.get('engine', 'Unknown'),
        'sample_rate':  a.get('sample_rate', 0),
    }


def _qc_passed(qc: dict) -> bool:
    if not qc:
        return True
    return len(qc.get('issues', [])) == 0
