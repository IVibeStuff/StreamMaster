# StreamMaster v2.0.2

## What's new

### Auto-update tag case fix
The update checker was not detecting releases tagged with a capital `V` (e.g. `V2.0.1`). Python's `str.lstrip('v')` is case-sensitive, so tags beginning with an uppercase `V` passed through unparsed and the version comparison silently failed. Fixed by using `lstrip('vV')` throughout the version parsing and display logic. Both `v2.x` and `V2.x` tags are now handled correctly.

### Update cache cleared on upgrade
The 24-hour update cache (`.update_cache.json`) could prevent the updater from detecting new releases after a period of no releases on GitHub. The fix in the tag parsing ensures the cache is correctly invalidated when a newer version is detected.

---

## Upgrade from v2.0 or v2.0.1

Replace `updater.py`, `server.py`, `index.html`, `Launch.bat`, `launch.sh`, and `Launch_Silent.vbs` with the v2.0.2 versions.

**Also delete `.update_cache.json`** from your StreamMaster install folder if upgrading from v2.0 — the stale cache from the initial release check needs to be cleared for the updater to detect v2.0.2 correctly.

---

## Full changelog

- Fix auto-update not detecting releases tagged with capital V (e.g. V2.0.1)
- Fix version display stripping capital V from tag name
- Update CURRENT_VERSION to 2.0.2 across all files
- Update version strings in index.html, server.py, launchers, and installer script
