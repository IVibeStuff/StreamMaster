# StreamMaster — Setup Guide

## Requirements
- Python 3.10 or later
- Windows 10/11, macOS, or Linux
- ~500 MB disk (packages) + ~4 GB if installing Demucs (optional)

## Step 1 — Install Python
Download from https://www.python.org/downloads/
**Tick "Add Python to PATH"** before clicking Install.

## Step 2 — Run the launcher
**Windows:** double-click `Launch.bat`
**macOS/Linux:** `chmod +x launch.sh && ./launch.sh`

First run installs packages automatically (~30 seconds).
Browser opens to http://localhost:5051

## Optional — Stem repair (Demucs)
Unlocks the Stem Repair mode in the Repair tab.
Requires ~4 GB disk and a GPU for fast processing (CPU works but is slow).
```
pip install demucs
```

## Troubleshooting
**Python not found:** re-run installer, tick "Add Python to PATH", restart terminal.
**Package install fails:** right-click launcher → Run as Administrator.
**Port 5051 in use:** edit server.py, change port=5051 to port=5052.
