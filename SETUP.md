# StreamMaster v2.0 — Setup Guide

## Requirements

- Python 3.10 or later
- Windows 10/11, macOS, or Linux
- ~500 MB disk space for Python packages
- ~4 GB additional disk if installing Demucs (optional)
- GPU recommended for Demucs (CPU works but is slower)

---

## Step 1 — Install Python

Download from https://www.python.org/downloads/

**Windows:** tick **"Add Python to PATH"** before clicking Install. Use Python 3.10, 3.11, or 3.12 — not 3.13.

**macOS/Linux:** Python 3 is often pre-installed. Check with `python3 --version`.

---

## Step 2 — Run the launcher

**Windows:** double-click `Launch.bat`

**macOS/Linux:**
```bash
chmod +x launch.sh
./launch.sh
```

First run installs all required packages automatically (~30 seconds). The browser opens to `http://localhost:5051` when ready. Close the console window (or press Ctrl+C in terminal) to stop the server.

---

## Step 3 — Optional: install Demucs

Demucs enables two additional features:

- **🎚 Stem Master** — masters vocals, drums, bass, and melody independently before recombining
- **🔧 Repair (stem mode)** — uses source separation for more precise phase corruption repair

```bash
pip install demucs
```

Demucs downloads model weights (~320 MB) on first use. A GPU is recommended but not required. On CPU, stem separation takes 2–5 minutes per track.

---

## Upgrading from a previous version

Replace all `.py` files, `index.html`, `Launch.bat`, and `launch.sh` with the v2.0 versions.

The following new files must be added to the install folder:
- `previewer.py` — preview variant generator
- `history.py` — mastering history store

**Important:** if you used v1.1 or v1.2, remaster any previously exported tracks. Those versions had a de-esser crossover bug that introduced +3 dB resonance peaks at 4 kHz and 12 kHz on every master.

---

## Troubleshooting

**Python not found**
Re-run the Python installer, tick "Add Python to PATH", restart your terminal or PC.

**Package install fails on Windows**
Right-click `Launch.bat` → Run as Administrator.

**Port 5051 already in use**
Edit `server.py` and change `port=5051` to any free port (e.g. `port=5052`). Update the browser URL accordingly.

**Browser shows old version after update**
Hard refresh: `Ctrl + Shift + R` (Windows/Linux) or `Cmd + Shift + R` (macOS). If that doesn't work, open DevTools (F12) → Network tab → tick "Disable cache" → refresh.

**Demucs not detected in Stem Master or Repair tabs**
The tab shows a status indicator when you open it. If it shows "not installed", run `pip install demucs` in a terminal and restart the server.

**Preview clips play at wrong speed**
This is a sample rate mismatch. Ensure you are on v2.0 — this was fixed in the v1.3 release for 96kHz files and in v2.0 for all files.

**Preview clips play audio from a previous song**
Hard refresh the browser (Ctrl+Shift+R). This was fixed in v2.0 with cache-busting on all clip URLs.

---

## File locations

| Path | Contents |
|------|----------|
| Install folder | All `.py` files, `index.html`, launchers, `history.json` |
| `%TEMP%\streammaster_uploads\` | Temporary uploaded and processed files (Windows) |
| `/tmp/streammaster_uploads/` | Temporary files (macOS/Linux) |
| `docs/` | Hero image for README |

Temporary files are cleared automatically when Windows runs its Temp cleanup. No audio is permanently stored by the tool.

---

## History file

Every master export is recorded to `history.json` in the install folder. This file is human-readable JSON and can be backed up or deleted manually. The History tab in the UI provides a clear all button if you prefer to manage it there.

---

## Port and network

The server only listens on `127.0.0.1` (localhost) — it is not accessible from other devices on the network. No audio or data is sent anywhere externally.
