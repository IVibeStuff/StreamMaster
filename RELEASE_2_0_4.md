# StreamMaster v2.0.4

## What's new

### Server shuts down when browser tab is closed
The Python server now monitors browser presence via a heartbeat. Every 5 seconds while the tab is open, the browser sends a lightweight signal to the server. If no signal arrives for 15 seconds (tab closed, browser crashed, or browser exited), the server shuts itself down automatically.

This means you no longer need to manually kill `python.exe` in Task Manager when you're done — simply closing the browser tab is sufficient. Page refreshes are safe: the browser resumes heartbeats within ~1 second, well within the 15-second grace period.

### Auto-update os import fix
The update restart thread was failing with `NameError: name 'os' is not defined` because Python thread functions require their own local imports. The `_restart` and `_stop` threads now both import `os` locally, resolving the silent failure that prevented the server from exiting after downloading an update.

### Quit StreamMaster button
A red **⏹ Quit StreamMaster** button is now available in the About modal. Clicking it sends an immediate shutdown signal to the server and replaces the page with a confirmation message.

### Port conflict detection
If you launch StreamMaster when it is already running, the new instance detects that port 5051 is occupied, opens the existing browser tab, and exits rather than competing for the port or showing a confusing error.

### Manual Check for updates button
The About modal now includes a **↺ Check for updates** button that immediately polls GitHub and shows the result inline, without waiting for the automatic check.

---

## Upgrade from any previous version

Replace all `.py` files, `index.html`, `Launch.bat`, `launch.sh`, and `Launch_Silent.vbs` with the v2.0.4 versions. Delete `.update_cache.json` from the install folder if present.

---

## Full changelog

- Add heartbeat-based server shutdown when browser tab is closed (15s grace period)
- Fix NameError: os not defined in update _restart thread
- Fix NameError: os not defined in shutdown _stop thread
- Remove duplicate sys import in server.py
- Add Quit StreamMaster button to About modal
- Add port 5051 conflict detection on startup
- Add manual Check for updates button to About modal
- Fix double browser window when using Launch_Silent.vbs (--no-browser flag)
- Bump version to 2.0.4 across all files
