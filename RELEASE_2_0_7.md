# StreamMaster v2.0.7

## What's new

### Update cache cleared before and after every update attempt
The update system was caching the GitHub API result for 24 hours. If a previous update attempt failed (e.g. wrong asset URL, network error), the stale cached result — pointing at the old release — would be used on the next attempt, causing a 404 when trying to download an asset that no longer existed on GitHub. The cache is now cleared before every download attempt and after every failure, ensuring the true latest release is always fetched.

### Force-refresh on manual update check
The "Check for updates" button in the About modal now bypasses the cache entirely and fetches live from GitHub, so clicking it always reflects the true current state rather than a cached result.

### Force-refresh before applying update
The apply_update route now clears the cache and fetches live before downloading, guaranteeing the asset URL is current regardless of what the background check cached earlier.

---

## Upgrade from any previous version

Delete `.update_cache.json` from your StreamMaster install folder, then replace `server.py` and `index.html` with the v2.0.7 versions.

---

## Full changelog

- Clear update cache before every download attempt
- Clear update cache after every failed download attempt  
- Manual Check for updates button uses force-refresh (bypasses cache)
- apply_update route force-refreshes before downloading
- Bump version to 2.0.7 across all files
