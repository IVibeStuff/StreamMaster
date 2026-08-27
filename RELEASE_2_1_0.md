# StreamMaster v2.1.0

## Critical fix — auto-update path handling

All previous auto-update attempts since v2.0.4 were failing because the restart bat file was generated with mixed path separators. Python's `Path` object uses forward slashes on Linux/macOS but the bat file needs Windows backslashes. The sandbox where this tool is developed runs on Linux, so every path written into the bat was using forward slashes — completely invalid on Windows, causing the bat to exit immediately without doing anything.

All paths in the restart bat are now explicitly normalised to Windows backslashes using `str(path).replace('/', '\\')` before being written into the bat script.

## What this means

Auto-update should now work correctly end-to-end:
1. Update banner appears
2. Click "Update now" — downloads zip, stages files, writes bat
3. A console window opens showing progress
4. Files are copied to install directory
5. StreamMaster relaunches automatically
6. Browser reloads after 20 seconds

## Upgrade from any previous version

Because auto-update was broken since v2.0.4, you'll need to install v2.1.0 manually. After that, all future auto-updates should work correctly.

Replace all files with the v2.1.0 versions. Delete `.update_cache.json` from the install folder.

---

## Full changelog

- Fix bat file path separators — all paths now use Windows backslashes
- Fix mixed slash/backslash paths in xcopy, if exist, copy, del, start commands
- Use quoted set syntax (set "VAR=value") for safer variable assignment in bat
- Bump to v2.1.0 to signal this is a significant fix after multiple patch attempts
