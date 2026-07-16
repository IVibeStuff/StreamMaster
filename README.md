# StreamMaster

**AI Music Mastering Suite — v1.1**

A local, open-source mastering toolkit for Suno and other AI-generated music. Prepares WAV files for professional streaming upload or personal listening. Runs entirely on your machine — no audio leaves your computer, no subscription required.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)

---

## What it does

AI music generators introduce specific technical flaws that standard mastering tools aren't calibrated for — hard frequency cutoffs, synthesis dropouts, diffusion haze, buried vocals. StreamMaster corrects these while normalising to the exact loudness targets used by Spotify, Apple Music, Tidal, and YouTube Music.

Two output profiles:
- **Streaming** — −14 LUFS · −1 dBTP · bright and forward, calibrated to survive platform encoding
- **Local listening** — −16 LUFS · −2 dBTP · warmer, for personal use where no platform normalisation is applied

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

| Tab | What it does |
|-----|-------------|
| 🔬 **Analyse** | Full diagnostic report — loudness, stereo image, spectrum, sibilance, dropouts, AI engine detection. Stores recommended settings for one-click transfer to the Master tab. |
| 🎛 **Master** | 15-stage mastering chain with Streaming and Local export buttons. Advanced panel for de-esser, vocal ride, and macro dynamics. Expert panel for chain internals. Automatic QC on every export. |
| ⚡ **De-Jinx** | Detects and repairs Suno synthesis dropouts across the full track. Shows timestamped list of every repair. |
| ✂️ **Splice** | Replace any section with regenerated audio. Handles level-matching and crossfading automatically. |
| 🩹 **Heal** | Smooth join points from an internal Suno replacement. No replacement clip needed. |
| 📈 **Level Bridge** | Ride gain across quiet passages that follow a splice. |
| 🎯 **Ref Match** | Match tonal balance and loudness to a commercial reference track via [Matchering](https://github.com/sergree/matchering). |

---

## Mastering chain

All 15 stages run automatically. The four user controls (stereo width, de-esser, vocal ride, macro dynamics) handle track-to-track variation; everything else is calibrated for AI-generated audio.

1. Resample → 44.1 kHz
2. EQ: +1.5 dB air shelf @ 10 kHz, −2 dB mud cut @ 380 Hz
3. Air restoration — fills Suno's 16 kHz hard cutoff
4. Spectral dehaze — breaks up diffusion model flatness in 8–16 kHz
5. M/S processing — bass anchored to centre, presence widened in side channel
6. De-esser — band-split architecture: compresses 5–10 kHz only, voice body untouched
7. Harmonic saturation — 15% parallel tanh
8. Glue compression — 2:1 on mid channel only
9. Dynamic EQ — threshold-driven 2–4 kHz cut
10. Transient shaping — restores attack transients
11. Vocal ride — mid-channel gain automation (optional)
12. Macro dynamics — section-aware contrast shaping (optional)
13. Profile adjustment — Streaming or Local warmth curve
14. Loudness normalisation — −14 or −16 LUFS
15. True-peak limiting — −1 or −2 dBTP
16. Export — 44.1 kHz / 16-bit WAV
17. QC — automatic check: clipping, dropouts, clicks, LUFS, true peak, phase

---

## Recommended workflow

**Standard track**
```
Analyse → Master (Apply analysis settings) → Streaming and/or Local
```

**Track with synthesis dropouts**
```
De-Jinx → Use in tool → Master
```

**Track with a replaced section**
```
De-Jinx → Splice → Heal → Level Bridge → Master
```

**Matching a commercial release**
```
Master → Use in tool → Ref Match
```

---

## Output file naming

```
TrackName_remaster_w1.9dB_d-2_v0_m3.5_streaming.wav
```

| Token | Meaning |
|-------|---------|
| `w1.9dB` | Stereo presence width applied |
| `d-2` | De-esser setting (−2 = Off) |
| `v0` | Vocal ride max boost (0 = Off) |
| `m3.5` | Macro dynamics target dB |
| `_streaming` / `_local` | Output profile |

---

## Files

| File | Purpose |
|------|---------|
| `Launch.bat` | Windows launcher |
| `launch.sh` | macOS / Linux launcher |
| `Install.bat` | Windows installer (Desktop + Start Menu shortcuts) |
| `server.py` | Local Flask server (port 5051) |
| `index.html` | Browser UI |
| `spotify_master.py` | 15-stage mastering chain |
| `mastering_extras.py` | EQ, de-esser, compressor, transient, dehaze |
| `vocalride.py` | Vocal presence automation |
| `analyser.py` | Track analysis and recommendations |
| `dejinx.py` | Synthesis dropout repair |
| `qc.py` | Quality control checks |
| `splice.py` | Section replacement |
| `heal.py` | Seam healer |
| `levelbridge.py` | Level/gain bridge |
| `requirements.txt` | Python dependencies |

---

## Requirements

- Python 3.10+
- Windows 10/11, macOS, or Linux
- ~500 MB disk space (Python packages)
- Internet on first run only

```
pip install -r requirements.txt
```

Packages: `flask` `flask-cors` `pyloudnorm` `soundfile` `scipy` `numpy` `matchering`

---

## License

MIT — see [LICENSE](LICENSE)
