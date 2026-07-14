# Spotify Master Tool — Setup Guide

## Requirements

| | |
|---|---|
| **OS** | Windows 10 or Windows 11 (64-bit) |
| **Python** | 3.10 or later |
| **RAM** | 4 GB minimum, 8 GB recommended |
| **Disk** | ~500 MB (Python packages) |
| **Internet** | Required on first run only (package download) |

---

## Step 1 — Install Python

1. Go to **https://www.python.org/downloads/**
2. Download the latest Python 3.x release
3. Run the installer
4. **Important:** tick **"Add Python to PATH"** before clicking Install

To verify: open Command Prompt and type `python --version`

---

## Step 2 — Install the Tool

1. Unzip `SpotifyMaster.zip` to any folder  
   e.g. `C:\Users\YourName\SpotifyMaster\`

2. The folder should contain:

```
SpotifyMaster\
├── Launch.bat              ← start here
├── index.html
├── server.py
├── spotify_master.py
├── mastering_extras.py
├── vocalride.py
├── analyser.py
├── dejinx.py
├── qc.py
├── splice.py
├── heal.py
├── levelbridge.py
└── README.md
```

---

## Step 3 — First Launch

1. Double-click **Launch.bat**
2. A terminal window opens and installs packages (one-time, ~30 seconds):
   ```
   Installing: flask, flask-cors, pyloudnorm, soundfile, scipy, numpy, matchering
   ```
3. Your browser opens automatically to **http://localhost:5051**

> If the browser does not open, navigate to http://localhost:5051 manually.

---

## Step 4 — Stopping the Tool

Close the terminal window that opened with Launch.bat.

---

## Troubleshooting

**"Python not found"**  
Re-run the Python installer and make sure "Add Python to PATH" is ticked.  
Then restart the terminal.

**"Failed to install packages"**  
Right-click Launch.bat → Run as Administrator.

**Browser shows "This site can't be reached"**  
The server may still be starting. Wait 5 seconds and refresh.  
If it persists, check the terminal window for error messages.

**Port 5051 already in use**  
Another application is using the port. Open `server.py` in Notepad,  
find `port=5051` near the bottom, and change it to `5052` (or any free port).  
Update the URL in your browser to match.

---

## Updating

To update to a newer version:

1. Stop the tool (close the terminal)
2. Replace all `.py` files and `index.html` with the new versions
3. Keep your existing `Launch.bat` — it does not need updating

---

## Packages Installed

| Package | Purpose |
|---|---|
| `flask` | Local web server |
| `flask-cors` | Browser security |
| `pyloudnorm` | LUFS measurement |
| `soundfile` | WAV read/write |
| `scipy` | Signal processing |
| `numpy` | Audio math |
| `matchering` | Reference track matching |
