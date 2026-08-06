# StreamMaster

<p align="center">
  <img src="docs/logo_hero.png" alt="StreamMaster" width="640"/>
</p>

**AI Music Mastering Suite — v2.0.3**

A local, open-source mastering toolkit for Suno and other AI-generated music. Prepares WAV files for professional streaming upload or personal listening. Runs entirely on your machine — no audio leaves your computer, no subscription required.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Version](https://img.shields.io/badge/version-2.0.2-1DB954)

---

## What it does

AI music generators introduce specific technical flaws that standard mastering tools aren't calibrated for — hard frequency cutoffs, synthesis dropouts, diffusion haze, buried vocals, phase corruption at generation boundaries. StreamMaster corrects these while normalising to the exact loudness targets used by Spotify, Apple Music, Tidal, and YouTube Music.

Two output profiles:
- **Streaming** — −14 LUFS · −1 dBTP · bright and forward, calibrated to survive platform encoding
- **Local listening** — −16 LUFS · −2 dBTP · warmer, for personal use without platform normalisation

---

## Quick start

**Windows**
1. Install [Python 3.10+](https://www.python.org/downloads/) — tick **"Add Python to PATH"**
2. Double-click `Launch.bat`
3. Browser opens to `http://localhost:5051`

**macOS / Linux**
```bash
chmod +x launch.sh
./launch.sh
```

First run installs dependencies automatically (~30 seconds). No internet required after that.

---

## Tools

### Mastering

| Tab | What it does |
|-----|-------------|
| 🔬 **Analyse** | Full diagnostic — loudness, stereo image, spectrum, sibilance, dropouts, dynamic range, AI engine detection. Extended heuristics compute track-specific parameter recommendations. After analysis, four 30-second preview variants are generated automatically (Raw, Optimised, Vocal Forward, Preserve Character) for side-by-side comparison before committing to a full export. |
| 🎛 **Master** | 15-stage mastering chain. **Export Both** (primary) generates streaming and local versions in one action. Individual Streaming only / Local only buttons also available. Advanced panel for de-esser, vocal ride, macro dynamics. Expert panel for all 12 chain parameters with contextual help. Automatic QC on every export. Every export recorded to history. |
| 🎚 **Stem Master** | Separates the track into vocals, drums, bass, and melody using Demucs, then masters each stem independently before recombining. Solves the core limitation of full-mix mastering — vocals and instrumentals can have different optimal settings. Requires `pip install demucs`. |
| 🎯 **Ref Match** | Match tonal balance and loudness to a commercial reference track via [Matchering](https://github.com/sergree/matchering). |

### Repair & Restoration

| Tab | What it does |
|-----|-------------|
| ⚡ **De-Jinx** | Detects and repairs Suno synthesis dropouts — moments where the generator collapses to near-silence. Shows a timestamped list of every repair zone. |
| 🔧 **Repair** | Detects and repairs generation boundary phase corruption — the hollow or "anti-phase" artefact that appears at Suno section joins. Phase repair always available; stem-based repair requires Demucs. |
| ✂️ **Splice** | Replace any section of the track with a clip from a regenerated version. Handles level-matching and crossfading automatically. |
| 🩹 **Heal** | Smooth the join points left by a Suno internal replacement. No replacement clip needed. |
| 📈 **Bridge** | Ride gain across quiet passages that follow a splice or level mismatch. |

### Session

| Tab | What it does |
|-----|-------------|
| 📋 **History** | Full record of every master export — source file, output filenames, all settings used, QC result, and engine detection. Grouped by source file. One-click import of any previous session's settings back into the Master tab. |

---

## Recommended workflows

**Standard track — everyday use**
```
Analyse → Master (Apply analysis settings) → Export Both
```

**Tracks where raw Suno sounds better than the remaster**
```
De-Jinx → Repair → Export (skipping the mastering chain)
```
Some tracks have perceptually valuable spectral characteristics that the mastering chain removes. Use De-Jinx and Repair to fix genuine faults without altering the sonic character.

**Tracks with vocals that need work but strong raw instrumentals**
```
Analyse → Stem Master (full chain on vocals, minimal on other stems)
```

**Track with synthesis dropouts**
```
De-Jinx → Use in tool → Master → Export Both
```

**Track with a replaced section**
```
De-Jinx → Splice → Heal → Bridge → Master → Export Both
```

**Matching a commercial release**
```
Master → Use in tool → Ref Match
```

**Re-mastering with previous settings**
```
History tab → find entry → Import settings → Master → Export Both
```

---

## Preview variant player

After analysis, StreamMaster automatically generates four 30-second clips in the background — one per variant — while you read the analysis report. A waveform scrubber shows the full track with the auto-selected preview window highlighted. The window is placed on the most musically representative section (highest vocal + full-mix energy, avoiding intros and outros).

| Variant | What it does |
|---------|-------------|
| **Raw** | Unprocessed — LUFS normalised only. The reference point. |
| **Optimised** | Full chain with analyser-recommended settings derived from the track's actual measurements. |
| **Vocal Forward** | Same as Optimised but with more presence widening, tighter de-essing, and brighter air. Vocal sits further forward. |
| **Preserve Character** | Minimal processing — LUFS normalised only, no EQ, no M/S, no saturation. For when the raw Suno file sounds better and you just need it streaming-ready. |

Click any variant card to play. Click **Use these settings** to apply that variant's parameters to the Master tab. Drag the waveform window to preview a different section and click Regenerate — clips are re-extracted from the already-processed full variants, so regeneration is near-instant.

---

## Mastering chain

All 15 stages run automatically. The Analyser computes track-specific recommended values for each parameter from continuous measurements rather than fixed thresholds.

1. Resample → 44.1 kHz
2. EQ: air shelf @ 10 kHz, mud cut @ 380 Hz (both derived from spectral tilt measurement)
3. Air restoration — fills Suno's 16 kHz hard cutoff with shaped noise
4. Spectral dehaze — breaks up diffusion model flatness in 8–16 kHz
5. M/S processing — bass anchored to centre, presence widened in side channel
6. De-esser — complementary band-split (unity sum guaranteed): compresses 4–12 kHz only
7. High-freq dynamics — broad dynamic shelf above 5 kHz (Expert panel, Off by default)
8. Harmonic saturation — parallel tanh (depth derived from engine and crest factor)
9. Glue compression — 2:1 on mid channel only
10. Dynamic EQ — threshold-driven 2–4 kHz cut
11. Transient shaping — restores attack transients (boost derived from crest factor measurement)
12. Vocal ride — adaptive reference, corrects short-term drops only (Off by default)
13. Macro dynamics — section-aware contrast shaping (Off by default)
14. Profile adjustment — Streaming or Local warmth curve
15. Loudness normalisation — −14 or −16 LUFS
16. True-peak limiting — −1 or −2 dBTP
17. Export — 44.1 kHz / 16-bit WAV
18. QC — automatic: clipping, dropouts, clicks, LUFS, true peak, phase

---

## Expert panel parameters

All 12 parameters in the Expert panel have contextual **?** help buttons explaining what each does and when to change it from the default.

| Parameter | Default | Notes |
|-----------|---------|-------|
| EQ air shelf | +1.5 dB | High shelf @ 10 kHz. Derived from spectral tilt. |
| EQ mud cut | −2.0 dB | Peak cut @ 380 Hz. Derived from low-mid excess. |
| Air restore blend | 0.018 | Noise floor above 16 kHz. 0 = disable. |
| Dehaze depth | ±4% | AM modulation 8–16 kHz. 0 = disable. |
| Saturation drive | +6 dB | Parallel tanh drive level. |
| Saturation mix | 15% | Wet/dry blend. |
| Comp threshold | −18 dBRMS | Mid-channel glue compression threshold. |
| Comp ratio | 2.0 : 1 | Glue compression ratio. |
| Transient boost | +2.5 dB | Derived from crest factor. 0 = disable. |
| Dyn EQ max cut | 3 dB | Max cut from 2–4 kHz dynamic EQ. |
| Sub-bass side mix | 15% | How much sub-bass stays in the side channel. 100% for wide bass sound design. |
| High-freq dynamics | Off | Dynamic high-shelf above 5 kHz. Set −28 dBRMS for cutting high-end tracks. |

---

## Stem Master — per-stem defaults

Each stem card has a **?** button with guidance including recommended settings for Pop/vocal, Orchestral/cinematic, Electronic/EDM, and Raw Suno preferred scenarios.

| Stem | Key defaults |
|------|-------------|
| 🎤 Vocals | Air +1.5 dB, mud −2 dB, M/S +1.9 dB, de-esser Medium, 2:1 compression |
| 🥁 Drums | Transient +3.5 dB, 3:1 compression, 20% saturation, 50% side mix |
| 🎸 Bass | 3:1 compression, 15% saturation, 100% side mix (preserve all bass width) |
| 🎹 Other/Melody | Air +1 dB, 80% side mix (preserves instrumental character) |

For orchestral/cinematic tracks: set **M/S Width to 0** and **Side mix to 100%** on the Other stem to preserve the full original stereo character while still giving the vocal stem full processing.

---

## Output file naming

```
TrackName_remaster_w1.9dB_d-2_v0_m0.0_streaming.wav
```

| Token | Meaning |
|-------|---------|
| `w1.9dB` | Stereo presence width applied |
| `d-2` | De-esser setting (−2 = Off) |
| `v0` | Vocal ride max boost (0 = Off) |
| `m0.0` | Macro dynamics target (0 = Off) |
| `_streaming` / `_local` | Output profile |

---

## Workspace customisation

Open the **About** modal (top-right) to toggle which tabs are visible. Analyse and Master are always shown. All other tabs — Stem Master, Ref Match, De-Jinx, Repair, Splice, Heal, Bridge — can be hidden individually. State is saved to localStorage. Reset to defaults restores everything.

---

## Files

| File | Purpose |
|------|---------|
| `Launch.bat` | Windows launcher |
| `launch.sh` | macOS / Linux launcher |
| `server.py` | Local Flask server (port 5051) |
| `index.html` | Browser UI |
| `spotify_master.py` | 15-stage mastering chain |
| `mastering_extras.py` | EQ, de-esser, compressor, transient, dehaze, dynamic high-shelf |
| `vocalride.py` | Adaptive vocal presence automation |
| `analyser.py` | Track analysis and extended heuristic recommendations |
| `previewer.py` | Preview variant generator — four 30-second clips after analysis |
| `history.py` | Mastering history store (history.json) |
| `dejinx.py` | Synthesis dropout repair |
| `qc.py` | Quality control checks |
| `splice.py` | Section replacement |
| `heal.py` | Seam healer |
| `levelbridge.py` | Level/gain bridge |
| `repair.py` | Phase boundary corruption repair |
| `stem_master.py` | Per-stem mastering (requires Demucs) |
| `requirements.txt` | Python dependencies |
| `logo.svg` | App icon / scalable logo mark |
| `docs/logo_hero.png` | Hero image for README |

---

## Requirements

- Python 3.10+
- Windows 10/11, macOS, or Linux
- ~500 MB disk space (Python packages)
- ~4 GB additional disk if installing Demucs (optional, for Stem Master and Repair)
- Internet on first run only

```
pip install -r requirements.txt
```

Core packages: `flask` `flask-cors` `pyloudnorm` `soundfile` `scipy` `numpy` `matchering`

Optional: `pip install demucs` — enables Stem Master and stem-based Repair

---

## Known behaviours

**Some tracks sound better without full mastering**
The mastering chain removes spectral artifacts that are technically incorrect but perceptually contribute to a track's character — Suno's upsampling imaging creates spaciousness, the 8–16 kHz diffusion haze adds texture, wide sub-bass creates physical presence. Removing these makes the mix more accurate but sometimes less compelling. Use De-Jinx and Repair to fix genuine faults without altering the sonic character. The **Preserve Character** preview variant gives you a streaming-ready version with minimal processing for exactly this case.

**Vocals and instrumentals may need different processing**
On tracks with strong orchestral or cinematic instrumental beds, the vocal benefits from the mastering chain while the instrumental loses impact from bass anchoring and spectral cleanup. Use the **Stem Master** tab — set M/S Width to 0 and Side Mix to 100% on the Other stem to preserve the original instrumental character while fully processing the vocal.

**Stereo width narrowing on wide sub-bass tracks**
The chain anchors sub-bass to centre by default (15% side mix). For tracks with intentionally wide low-frequency effects, increase **Sub-bass side mix** in the Expert panel towards 100%.

**Streaming master sounds brighter than local**
Intentional — the streaming version is calibrated to survive Ogg Vorbis encoding. If it sounds sharp in your local player, that is expected and correct. Use the local version for personal listening.

**De-esser at high settings affects voice character**
The de-esser's band-split architecture preserves vocal body below 4 kHz, but at Strong/Aggressive/Max settings perceived voice character can still shift. Default is Off — the Analyser recommends a setting based on the measured sibilance crest factor.

---

## License

MIT — see [LICENSE](LICENSE)
