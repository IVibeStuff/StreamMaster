# StreamMaster v2.0.8

## What's new

### Update restart bat now visible with error reporting
The restart script that runs after downloading an update now opens a visible console window showing each step — backup, file copy, relaunch. If any step fails (xcopy error, missing files, etc.) the window pauses and shows the error rather than closing silently. This makes diagnosing update failures possible.

### Removed DETACHED_PROCESS flag from update launcher
The bat was being launched with the Windows DETACHED_PROCESS flag which in some configurations prevented it from running properly. Removed — the bat now launches normally and its window is visible during the update process.

### xcopy error checking
The restart bat now checks the xcopy exit code and halts with a visible error message if the copy fails, rather than silently proceeding to relaunch with no new files.

---

## Upgrade from any previous version

Replace `server.py` and `updater.py` with the v2.0.8 versions. Delete `.update_cache.json` from the install folder.

---

## Full changelog

- Restart bat now opens visibly with step-by-step progress output
- Restart bat pauses on error so failures are visible
- Remove DETACHED_PROCESS flag from Popen call in server.py
- Remove close_fds=True from Popen (not valid on Windows with shell)
- Add xcopy error code check — halts with message if copy fails
- Add server.py existence check before xcopy
- Increase wait before relaunch for stability
- Bump version to 2.0.8 across all files
