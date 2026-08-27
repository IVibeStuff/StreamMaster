# StreamMaster v2.0.9

## What's new

### Update window now stays open showing full progress
The restart bat is now launched with `cmd /k` in a new window, which keeps the window open after the script finishes so you can see the full output. Previously `cmd /c` was used which closes immediately on completion or error, making diagnosis impossible.

### Full path diagnostics in update window
The update window now shows the install directory, stage directory, and resolved source directory at the start of the process, making it easy to spot path issues.

### xcopy output visible
xcopy output is no longer suppressed — you can see exactly which files are being copied and any errors that occur.

---

## Upgrade from any previous version

Replace `server.py` and `updater.py` with the v2.0.9 versions. Delete `.update_cache.json` from the install folder.

---

## Full changelog

- Launch restart bat with start cmd /k so window stays open
- Show install dir, stage dir and source dir in update window
- Show xcopy output rather than suppressing it
- Bump version to 2.0.9 across all files
