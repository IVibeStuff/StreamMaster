# Streaming Master Tool

A local audio toolkit for mastering and repairing AI-generated music.
Runs entirely on your machine — no audio leaves your computer.

## Quick Start

1. Install **Python 3.10+** from https://www.python.org/downloads/
   Tick **"Add Python to PATH"** during installation.
2. Double-click **Launch.bat**
   First run installs packages automatically (~30 seconds).
   Browser opens to http://localhost:5051

---

## Tools

### 🎛 Master
Full mastering chain for upload to Spotify, Youtube and other platforms:
- EQ: high-shelf air boost, low-mid mud cut
- **Mid-side processing**: bass anchored to mid (mono-safe), presence widened in side channel
- **Harmonic saturation**: gentle parallel tanh for warmth
- Glue compression (2:1)
- **Macro-dynamic contrast**: section-aware gain increases verse/chorus difference
- Loudness → **−14 LUFS** (Spotify target)
- True-peak limiting → **−1 dBTP**
- Export: **44.1 kHz / 16-bit WAV**

### ✂️ Splice
Replace a section with a new clip. Waveform editor with zoom + drag handles.

### 🩹 Heal seam
Smooth join points when the replacement is already baked in (e.g. Suno).

### 📈 Level bridge
Ride gain across a quiet passage after a splice.

### ⚡ De-Jinx
Auto-detect and repair Suno synthesis dropouts across the full track.

---

## Typical workflow

1. **De-Jinx** the original WAV
2. **Heal seam** the join points
3. **Level bridge** any quiet passage
4. **Master** for Spotify

---

## Files

| File | Purpose |
|------|---------|
| `Launch.bat` | Double-click to start |
| `server.py` | Local Flask server |
| `index.html` | Browser UI |
| `spotify_master.py` | Mastering chain |
| `splice.py` | Section replacement |
| `heal.py` | Seam healer |
| `levelbridge.py` | Level/gain bridge |
| `dejinx.py` | Dropout repair |

## Requirements
- Windows 10 / 11
- Python 3.10+ (https://www.python.org)
- Internet on first run (package install)

Packages: `flask flask-cors pyloudnorm soundfile scipy numpy matchering`

---

## New in this version

### Mastering chain additions (in processing order)
- **Air restoration** — synthesises a shaped noise floor above 16 kHz to replace Suno's hard spectral cutoff (Suno generates at 32 kHz internally)
- **Spectral dehaze** — breaks up the uniform 8–16 kHz energy distribution produced by diffusion models using subtle amplitude modulation
- **Glue compression** — gentle RMS compression on the mid channel only (stereo width untouched)
- **Dynamic EQ** — threshold-driven cut in 2–4 kHz only when harshness exceeds the band's own average level
- **Transient shaping** — detects and restores attack transients flattened by Suno's internal compression

### New tab
- **🎯 Ref match** — match your track's tonal balance, loudness, and stereo width to a commercially released reference song using Matchering
