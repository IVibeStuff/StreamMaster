# StreamMaster v2.2

## Overview

v2.2 is a stability and usability release, consolidating all changes since v2.0. The most significant user-facing improvements are the redesigned preview system and the auto-update reliability fixes.

---

## What's new since v2.0

### Preview system redesigned (v2.1.4+)
The four preview variants (Raw, Optimised, Vocal Forward, Preserve Character) are now generated on demand rather than automatically after analysis. A **🎧 Generate preview clips** button appears after analysis completes. Clicking it generates all four variants, then immediately calls the regen endpoint to serve clean closed files — resolving the playback issue that affected automatic generation.

### Timeline scrubber replaces canvas waveform (v2.1.7)
The canvas waveform has been replaced with a simple CSS bar scrubber — a track bar with a highlighted 30-second window and a draggable handle. Click anywhere on the bar to reposition the window, or drag the green handle. Regenerate to get new clips from the new position. The bar-based approach renders instantly and reliably without canvas layout timing issues.

### Auto-update restart mechanism rewritten (v2.1.1+)
The bat-file restart approach has been replaced with a Python script (`restart.py`). Python is guaranteed to be installed for any StreamMaster instance, handles file paths correctly on all Windows configurations, and uses `shutil` for reliable file copying. The restart window opens visibly so progress is shown.

### Server shuts down when browser tab is closed (v2.0.4)
Heartbeat-based shutdown — JS sends POST /heartbeat every 5 seconds. If no heartbeat for 15 seconds, the server exits automatically. Page refreshes are safe. The Quit button in About modal provides immediate shutdown.

### Update cache force-refresh (v2.0.7)
The manual Check for updates button and the apply_update route both force-refresh the GitHub API cache before acting, preventing stale cached asset URLs from causing 404 errors.

### Quit StreamMaster button (v2.0.4)
Red ⏹ Quit StreamMaster button in the About modal sends an immediate shutdown signal.

### Port conflict detection (v2.0.4)
If StreamMaster is already running on port 5051, a new launch attempt opens the existing browser tab and exits rather than competing for the port.

### Silent launcher double-window fix (v2.0.3)
`Launch_Silent.vbs` passes `--no-browser` to suppress the server's own `webbrowser.open()` call, preventing two browser tabs from opening.

---

## Full changelog since v2.0

- Preview clips generated on demand via Generate button (not automatic)
- Canvas waveform replaced with CSS bar scrubber
- Auto-update restart rewritten as restart.py (Python, not bat)
- Heartbeat-based server shutdown when browser tab closes
- Update cache force-refreshed before manual check and before applying update
- Quit StreamMaster button in About modal
- Port conflict detection on startup
- Double browser window fix for Launch_Silent.vbs
- Preview clip playback fixed — regen endpoint used after generation
- Waveform ResizeObserver approach removed (replaced with scrubber)
- All version strings updated to v2.2
