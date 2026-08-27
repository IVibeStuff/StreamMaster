# StreamMaster v2.0.5

## What's new

### Preview clips now play reliably on first click
Audio elements for all four preview variants (Raw, Optimised, Vocal Forward, Preserve Character) are now pre-loaded 500ms after generation completes, rather than being created lazily on first click. Previously, clicking play immediately after the clips appeared would sometimes fail because the server was still flushing the WAV file to disk. The 500ms delay ensures all files are fully written before playback is attempted. The same pre-loading applies after using the Regenerate button, fixing the same issue when switching songs.

---

## Upgrade from v2.0.4

Replace `index.html` with the v2.0.5 version. No other files changed.

---

## Full changelog

- Fix preview clips failing to play on first click after generation
- Fix same issue after regenerating clips for a new song
- Pre-load all four audio elements 500ms after done event
- Pre-load all four audio elements 500ms after regeneration
- Bump version to 2.0.5 across all files
