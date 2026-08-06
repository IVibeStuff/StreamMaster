# StreamMaster v2.0.3

## What's new

### Manual update check in About modal
A **Check for updates** button now appears in the About modal alongside the Workspace section. Clicking it immediately polls the GitHub API and shows the result inline — either the new version number in green with the banner appearing, or a confirmation that you're already on the latest version. This supplements the automatic check that runs 3 and 10 seconds after launch.

### Double browser window fix
When launching via `Launch_Silent.vbs`, two browser windows were opening — one from the VBScript and one from `server.py`'s `webbrowser.open()` call. Fixed by passing `--no-browser` from the VBScript to suppress the server-side open. `Launch.bat` is unaffected and continues to open the browser normally.

### Version display fix
The version shown in the About modal and tab bar now correctly reflects the installed version. Previous installer builds could deploy an older `index.html` if the source files weren't fully updated before building the `.exe`. All version strings are now consistently set to 2.0.3 across every file.

---

## Upgrade from any previous version

Replace all `.py` files, `index.html`, `Launch.bat`, `launch.sh`, and `Launch_Silent.vbs` with the v2.0.3 versions. Delete `.update_cache.json` from the install folder if present.

---

## Full changelog

- Add manual Check for updates button to About modal
- Fix duplicate browser window when launching via Launch_Silent.vbs
- Remove duplicate checkForUpdate function definition
- Fix version display inconsistency across installer builds
- Bump CURRENT_VERSION to 2.0.3 in updater.py
- Update all version strings to v2.0.3
