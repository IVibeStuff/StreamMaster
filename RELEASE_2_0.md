# StreamMaster v2.0

## Overview

v2.0 is a major release. The tool has been rebuilt across the UI, processing chain, and analysis engine. The version bump reflects the scope of change since v1.0 — StreamMaster is now a full AI music mastering suite rather than a basic mastering chain.

---

## What's new in v2.0

### Extended heuristics — genuinely track-specific settings
The Analyser now computes every parameter value from continuous measurements of the actual track rather than mapping from fixed threshold buckets.

- **Spectral tilt** drives EQ shelf and mud cut precisely — a track with a steep downward tilt gets a larger shelf boost; a flat track gets less
- **Sibilance crest factor** maps continuously to a specific de-esser threshold rather than a binary detected/not detected choice
- **Bass stereo spread** (side vs mid sub-bass energy) determines bass_side_mix automatically — tracks with intentionally wide low end get a higher starting value
- **Transient crest factor** determines transient boost — heavily squashed tracks get more, already punchy tracks get less
- **Vocal level variance** across the track drives the vocal ride recommendation — only activates if the vocal is actually drifting
- **High-frequency crest factor** drives the high-shelf dynamics threshold
- **Dynamic range** continues to drive macro dynamics recommendation

### Preview variant player
After analysis, four 30-second clip variants are generated automatically in the background — Raw, Optimised, Vocal Forward, and Preserve Character. A waveform scrubber shows the full track with the auto-selected preview window highlighted. Click any card to play and compare. Click "Use these settings" to apply that variant's parameters to the Master tab and export the full version. Drag the window on the waveform and regenerate clips to preview a different section.

### Export Both — single action for streaming and local
The Master tab now has Export Both as the primary action — generates the streaming (−14 LUFS) and local (−16 LUFS) versions sequentially and presents both download links. The individual Streaming only and Local only buttons remain for when only one version is needed.

### Pip-style progress bars
All 11 processing actions now show a row of square green pips on a dark background rather than a continuous fill bar. Each pip corresponds to a processing stage — the bar advances stage by stage, giving a genuine sense of how far through the chain the tool is.

### Workspace customisation
The About modal now has a Workspace section. Every optional tab can be toggled on or off. Disabled tabs are hidden from the tab bar immediately and the state is saved to localStorage. Analyse and Master are always visible. All other tabs — Stem Master, Ref Match, De-Jinx, Repair, Splice, Heal, Bridge — are individually toggleable. Reset to defaults restores all tabs.

### Panel info collapse
Every "when to use this" description block is now collapsible. Click the title bar to collapse or expand. State is saved per panel in localStorage so the layout remembers your preferences across sessions.

### Layout expansion
Maximum width increased from 1100px to 1400px. Sidebar widened from 220px to 260px. Card padding increased and content column widened from 560px to 760px. All panels have noticeably more breathing room.

### Bug fixes inherited from v1.3
- Critical de-esser crossover distortion (+3 dB peaks at 4 kHz and 12 kHz on every master) — fixed by complementary subtraction band-split
- Stem Master vocal pitch/speed shift on 96kHz input — fixed by reading actual Demucs output sample rate
- Preview clip speed shift on 48/96kHz input — fixed, all variants resampled to 44100Hz
- Preview clips regenerating from previous song — fixed by clearing stale files on new analysis
- `presenceGain` free variable in `buildMasterForm` — fixed to read from width slider
- Double `panel-info-body` div in all 9 panel info blocks — fixed

---

## Upgrade from v1.x

Replace all `.py` files, `index.html`, `Launch.bat`, and `launch.sh` with the v2.0 versions. The new `previewer.py` file must be included.

Remaster any tracks processed with v1.1 or v1.2 — the de-esser crossover bug affected every master produced by those versions.

---

## Full changelog

- Add extended heuristics — spectral tilt, sibilance crest, bass spread, transient crest, vocal variance, HF dynamics, all driving specific parameter values
- Add preview variant player — Raw, Optimised, Vocal Forward, Preserve Character clips after analysis
- Add waveform scrubber with draggable 30s preview window
- Add Export Both as primary Master tab button
- Add pip-style progress bars on all 11 processing actions
- Add workspace tab visibility toggles in About modal with localStorage persistence
- Add panel info collapse with per-panel localStorage state
- Widen layout to 1400px, sidebar to 260px, card to 760px
- Fix de-esser crossover distortion (complementary subtraction band-split)
- Fix de-esser same fix in stem_master.py
- Fix Stem Master sample rate on Demucs output
- Fix preview clip sample rate for 48/96kHz source files
- Fix preview clips regenerating from stale previous song
- Fix presenceGain undefined in buildMasterForm
- Fix double panel-info-body in all 9 panel info blocks
- Fix preview clip browser caching — stale clips from previous song no longer play after loading a new one
- Add no-cache headers to /preview_clip server route
- Add cache-busting timestamp to all preview clip URLs
- Bump version to 2.0 across all files and launchers
