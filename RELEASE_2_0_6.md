# StreamMaster v2.0.6

## What's new

### Auto-update restart now works reliably
The update restart script has been rewritten to handle the zip extraction structure correctly. Previously, the bat file used a Python-resolved subfolder path that could be wrong if the zip extracted to a flat structure. The new script uses a Windows `for /D` loop to locate the correct source directory at runtime — it finds the folder containing `server.py` regardless of whether the zip has a top-level subfolder or extracts flat.

Additional robustness improvements:
- Wait time before file copy increased from 3s to 4s to ensure the Python process has fully exited
- Wait time before relaunch increased from 1s to 2s
- Browser reload delay increased from 12s to 20s to give the server enough time to restart before the page reloads
- xcopy errors are now suppressed gracefully

---

## Upgrade from v2.0.5

Replace `updater.py` and `index.html` with the v2.0.6 versions.

---

## Full changelog

- Rewrite restart.bat generation to locate source directory at runtime
- Fix xcopy failing when zip extracts to flat structure
- Increase server exit wait from 3s to 4s
- Increase relaunch wait from 1s to 2s  
- Increase browser reload delay from 12s to 20s
- Bump version to 2.0.6 across all files
