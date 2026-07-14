**SPOTIFY MASTER TOOL**  v1.0

*AI Music Mastering Suite for Suno and other AI-generated audio*

Runs entirely locally on your machine  ·  No audio leaves your computer  ·  No subscription required

**What It Does**

Spotify Master Tool takes raw WAV files from Suno (or other AI music generators) and prepares them for professional streaming upload. It corrects the specific technical flaws AI generators introduce — hard frequency cutoffs, synthesis dropouts, buried vocals, diffusion haze — while normalising to Spotify's exact loudness target of −14 LUFS.

**Quick Start**

- Double-click  Launch.bat  (installs dependencies on first run, ~30 seconds)

- Browser opens to http://localhost:5051

- Drop your raw Suno WAV into the  🔬 Analyse  tab

- Click  Analyse Track  →  Apply Recommended Settings

- Switch to  🎛 Master  →  click  Master for Spotify

- Download your finished 44.1 kHz / 16-bit / −14 LUFS WAV

**The Tools**

| **🔬  Analyse** | Scans the file and produces a full diagnostic report — loudness, stereo image, spectrum, sibilance, dropouts, AI engine detection. Recommends all settings and transfers them to the Master tab with one click. |
| --- | --- |
| **🎛  Master** | Full mastering chain. Produces a Spotify-ready WAV. All controls are adjustable; defaults work well for most Suno tracks. |
| **⚡  De-Jinx** | Automatically detects and repairs Suno synthesis dropouts — moments where the generator briefly loses coherence and the audio collapses. Shows exact timestamps of every repair. |
| **✂️  Splice** | Replace a section with regenerated audio from Suno. Drag handles set in/out points; tool handles level-matching and crossfading. |
| **🩹  Heal** | Smooth the join points of a section Suno has already replaced internally. No replacement clip needed. |
| **📈  Level Bridge** | Ride gain across a quiet passage that follows a splice. Detects and fills the level step automatically. |
| **🎯  Ref Match** | Match your track's tonal balance and loudness to a commercially released reference track using Matchering. |

**Master Tab — Controls**

| **Setting** | **Range** | **Default** | **Notes** |
| --- | --- | --- | --- |
| **Stereo Width** | 0 – +4.2 dB | **+1.9 dB** | Suno preset boosts side presence 2–8 kHz. Use Other AI (0 dB) for non-Suno tracks. Wide (+3.5 dB) for more spacious sound. |
| **De-esser** | Off – Max | **Off** | Reduces harsh "s" sounds. Start at Medium; increase if sibilance is still present. Auto-detects vocal centring. |
| **Vocal Ride** | 0 – 8 dB | **Off** | Lifts buried vocals in the second half of the track. 4 dB is a good starting point for Suno tracks with vocal dropout. |
| **Macro Dynamics** | 0 – 6 dB | **3.5 dB** | Increases contrast between quiet and loud sections. Set to 0 for tracks with naturally strong dynamics (choral, orchestral). |

**
Presets: **Other AI = 0 dB width (bass anchor only)   ·   Suno = +1.9 dB   ·   Wide = +3.5 dB

**What Mastering Does (in order)**

- EQ — +1.5 dB air shelf at 10 kHz, −2 dB mud cut at 380 Hz

- Air restoration — synthesises a noise floor above 16 kHz (Suno generates at 32 kHz internally; this fills the gap)

- Spectral dehaze — breaks up Suno's unnaturally flat 8–16 kHz diffusion haze

- M/S processing — anchors sub-bass to centre; widens presence band in side channel

- De-esser — mid-channel detection; wideband for off-centre vocals (auto-detected)

- Harmonic saturation — 15% parallel tanh for warmth and density

- Glue compression — gentle 2:1 on mid channel only (preserves stereo image)

- Dynamic EQ — cuts 2–4 kHz harshness only when it exceeds its own average level

- Transient shaping — restores attack transients flattened by Suno's internal compression

- Vocal ride — mid-channel gain automation for the second half of the track

- Macro dynamics — section-aware gain shaping

- Loudness normalisation — target −14 LUFS integrated (Spotify specification)

- True-peak limiting — ceiling −1 dBTP (Spotify specification)

- Export — 44.1 kHz / 16-bit WAV

- QC check — automatic verification: clipping, dropouts, clicks, LUFS, true peak, phase

**Recommended Workflow**

**Standard track (no edits needed)**

- Analyse → Apply → Master

**Track with synthesis dropouts (jinx)**

- De-Jinx → Use in tool → Master

- Note timestamps shown in De-Jinx tab for reference

**Track with a replaced section**

- De-Jinx (if needed) → Heal → Level Bridge → Master

**Matching a commercial release**

- Master → Use in tool → Ref Match (drop a reference WAV)

**Output File Naming**

**TrackName_remaster_w1.9dB_d-2_v0_m3.5.wav**

- w1.9dB — stereo presence width applied

- d-2 — de-esser setting (-2 = Off)

- v0 — vocal ride max boost (0 = Off)

- m3.5 — macro dynamics target in dB (0 = Off)

**Tips**

- Drop a WAV anywhere — it propagates to all tabs automatically

- After any result, click "Use in tool" to load it into all tabs without downloading first

- The Analyse tab switches automatically when a new file is loaded

- Change any slider after mastering and the Master button re-activates for another run

- The right-hand console panel shows a live checklist of each processing stage

- The Analyse tab detects Suno vs Other AI and sets the width preset accordingly

- For non-Suno tracks, use Other AI preset — all other processing still applies

- A/B testing: run multiple times with different settings; filenames encode the parameters

Spotify Master Tool  ·  Runs locally on Windows 10/11  ·  Python 3.10+  ·  No internet required after setup

Packages: flask  flask-cors  pyloudnorm  soundfile  scipy  numpy  matchering