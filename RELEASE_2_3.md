# StreamMaster v2.3

## What's new since v2.2

### Preview playback fully stable across multiple songs
Two bugs were causing preview clips to continue playing or interfere after loading a new song:

**Audio elements not stopped on song change** — calling `_previewAudios = {}` removed the JavaScript reference but left the `HTMLAudioElement` objects still playing in the browser. They now have `pause()` and `src = ''` called explicitly before the reference is cleared, forcing the browser to stop and release them.

**Stale event listeners** — `timeupdate` and `ended` listeners attached to old audio elements would fire against the new song's DOM elements (same IDs, different song), causing phantom progress bar updates and button label changes. A `_previewGenId` counter increments each time audio is cleared. Every listener captures its generation ID at creation and exits immediately if the current generation has moved on. Four guards across both audio creation paths.

The result: loading a new song fully discards the previous song's audio state — both in the browser and on the server (clip files deleted before new generation).

---

## Upgrade from v2.2

Replace `index.html` with the v2.3 version. No other files changed.

---

## Full changelog

- Fix preview clips continuing to play after new song is loaded
- Fix stale audio event listeners affecting new song's UI
- Add _clearPreviewAudios() helper with explicit pause + src clear
- Add _previewGenId generation counter to guard all audio event callbacks
- Bump version to 2.3 across all files and documentation
- Update manual to v2.3
