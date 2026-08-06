# StreamMaster — Changelog

All notable changes to StreamMaster are documented here, newest first.

---

## v2.0

**Major release.** Full UI rebuild, extended heuristics, preview variant player, History tab, workspace customisation, and pip-style progress bars. See [RELEASE_2_0.md](RELEASE_2_0.md) for full details.

### Highlights
- Extended heuristics — every parameter derived from continuous track measurements (spectral tilt, sibilance crest, bass spread, transient crest, vocal variance)
- Preview variant player — Raw, Optimised, Vocal Forward, Preserve Character clips generated after analysis; waveform scrubber with draggable 30s window
- Export Both — single button generates streaming and local versions sequentially
- History tab — full record of every export with Import settings to reload any previous session
- Workspace customisation — toggle optional tabs on/off in About modal, state saved to localStorage
- Panel info collapse — every description block collapsible, state remembered per panel
- Layout expanded to 1400px wide with more breathing room throughout
- Pip-style progress bars on all 11 processing actions
- Critical de-esser crossover fix — +3 dB resonance peaks at 4 kHz and 12 kHz removed

### Bug fixes
- De-esser crossover distortion (+3 dB at 4 kHz and 12 kHz on every master) — complementary subtraction band-split
- Stem Master pitch shift on 96kHz source — reads actual Demucs output sample rate
- Preview clip speed on 48/96kHz source — all variants correctly resampled to 44100 Hz
- Preview clips caching stale audio from previous song — cache-busting timestamps and no-cache headers
- presenceGain undefined in buildMasterForm — reads from width slider correctly

---

## v1.3

**Significant release.** Stem Master tab, contextual help system, critical de-esser fix, sample rate fixes. See [RELEASE_1_3.md](RELEASE_1_3.md) for full details.

### Highlights
- Stem Master tab — per-stem mastering with Demucs (vocals, drums, bass, other)
- Contextual ? help panels on all 12 Expert panel parameters
- Contextual ? help panels on all 4 Stem Master stem cards with per-scenario guidance
- Private track name references removed from all user-facing text

### Bug fixes
- Critical de-esser crossover distortion (+3 dB at crossover frequencies on every master)
- Same crossover fix in stem_master.py de-esser stage
- Stem Master vocal pitch/speed on Demucs output at wrong sample rate
- Stem Master vocal pitch/speed on 96kHz source files

---

## v1.2

**Feature release.** High-frequency dynamics, adaptive vocal ride, macro dynamics defaults, analyser improvements, UI overhaul. See [RELEASE_1_2.md](RELEASE_1_2.md) for full details.

### Highlights
- High-freq dynamics — dynamic high-shelf compressor above 5 kHz (Expert panel)
- Adaptive vocal ride — ±30s context window replaces fixed first-40% reference
- Macro dynamics defaults to Off — tracks opt in rather than having it applied blindly
- Analyser recommends macro dynamics based on measured dynamic range
- Tab reset on new file load — all results cleared when a new song is dropped in
- Two grouped tab sections — Mastering and Repair & Restoration
- Panel descriptions on every tab

### Bug fixes
- Apply analysis settings reading from wrong level of analyser response
- Use in tool failing on Master and Repair tabs (missing dataset.filename)
- Repair tab not receiving shared file propagation
- async keyword missing from useInTool function
- Stale filename in Apply analysis confirmation banner
- Macro dynamics default changed from 3.5 dB to Off

---

## v1.1

**Feature release.** Streaming/Local output profiles, band-split de-esser, Expert panel, About modal, macOS/Linux support.

### Highlights
- Streaming (−14 LUFS) and Local (−16 LUFS) output profiles
- Band-split de-esser — compresses sibilance band only, voice body untouched
- Expert panel — 12 chain parameters exposed for advanced users
- About modal with version information
- macOS and Linux launcher support

---

## v1.0

**Initial release.** Windows-only. Basic mastering chain — EQ, M/S processing, saturation, compression, transient shaping, LUFS normalisation, true-peak limiting. De-Jinx, Repair, Splice, Heal, Level Bridge, Ref Match tabs.
