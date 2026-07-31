# StreamMaster v1.2

## What's new

### High-frequency dynamics (dynamic high-shelf)
A new processing stage in the Expert panel — **High-freq dynamics** — applies a dynamic compressor to all audio above 5 kHz. Unlike the de-esser, which targets a narrow sibilance band with precise detection, this is a broad shelf that fires when the entire high-frequency region becomes too energetic. It is the right tool for tracks where harshness is spread across a wide frequency range (4–12 kHz) rather than concentrated at a single sibilance frequency. Bypassed by default; set to −28 dBRMS threshold for tracks with cutting or sharp high-end character. Includes 1.5ms lookahead so gain reduction anticipates peaks before they arrive.

### Adaptive vocal ride reference
The Vocal Ride feature previously used the median of the first 40% of the track as a fixed reference level. This caused it to fight natural gradual fades — lifting the second half of the track towards the level of the intro, which manifested as an unnatural volume push on consumer earphones. The reference is now adaptive: at each point in the track it is calculated from a ±30 second context window, so gradual dynamic shapes are tracked and left alone. Only short-term buried-vocal events within an otherwise consistent section are corrected.

### Macro dynamics defaults to Off
The Macro dynamics stage previously defaulted to 3.5 dB for all tracks. This was causing audible volume riding — starts loud, dips in the middle, pushes at the end — on tracks with naturally good dynamic range. The default is now Off (0 dB). Tracks should opt into macro dynamics rather than have it applied blindly.

### Analyser recommends macro dynamics based on dynamic range
The Analyse tab now outputs a macro dynamics recommendation based on the track's measured dynamic range. Tracks with DR above 14 dB receive a recommendation of Off — their natural shape is already well-formed. Tracks with DR 10–14 dB receive 1.5 dB. Tracks below 10 dB (dynamically flat Suno output) receive the full 3.5 dB. Clicking Apply analysis settings on the Master tab transfers this recommendation correctly.

### De-esser improvements
The de-esser detection band has been widened from 5–10 kHz to 4–12 kHz to better capture sibilance that peaks at the lower edge of the original band. Attack time reduced to 0.5ms and a 1.5ms lookahead added so gain reduction is applied before the transient peak rather than after it.

### Tab reset on new file load
Dropping a new file into any drop zone now clears all result states across all tabs — download rows, status bars, repair lists, the analysis report, the console panel. Stale output from the previous song is no longer visible when starting work on a new track.

### Apply analysis settings bug fixed
`applyRecommendations` was reading from the wrong level of the analyser response object, causing every field to fall back to its default value. Stereo width, de-esser, vocal ride, macro dynamics, and sub-bass side mix now all import correctly from the analysis.

### Sub-bass side mix added to analysis output
The analyser now includes `bass_side_mix` in its recommendations (defaulting to 15%), so Apply analysis settings correctly resets the Expert panel slider rather than leaving it at whatever value it was previously set to.

### Repair tab file propagation
The Repair tab was not receiving files propagated by the shared file system. Dropping a file on any other tab, or clicking Use in tool from any result, now correctly populates the Repair tab's drop zone and enables its button.

### Use in tool fixed for Master and Repair tabs
The Use in tool button on the Master (streaming and local) and Repair tabs was silently failing because these tabs set the download button's onclick directly without storing the filename in `dataset.filename`. Both tabs now store the filename correctly, so Use in tool works as expected.

### Two grouped tab sections
The tab bar is now split into two labelled groups — **Mastering** (Analyse, Master, Ref Match) and **Repair & Restoration** (De-Jinx, Repair, Splice, Heal, Bridge) — making the tool's two distinct purposes immediately clear.

### Panel descriptions
Every tab now opens with a description block explaining what the tool does, when to use it, and the most important practical tip. The Repair tab in particular now explains the distinction between phase corruption (which it handles) and dropout artifacts (which De-Jinx handles), and notes that Suno's own Remaster feature inherits boundary corruption from the original.

---

## Upgrade from v1.1

Replace all `.py` files and `index.html` with the v1.2 versions. `Launch.bat`, `launch.sh`, and `Install.bat` should also be replaced to show the correct version number in the console window.

Run `pip install -r requirements.txt` if upgrading on a fresh machine.

No database or configuration migration required.

---

## Full changelog

- Add High-freq dynamics (dynamic high-shelf compressor above 5 kHz) to Expert panel
- Add 1.5ms lookahead to both de-esser and high-freq dynamics
- Widen de-esser detection band from 5–10 kHz to 4–12 kHz
- Reduce de-esser attack time from 1ms to 0.5ms
- Replace vocal ride fixed reference with adaptive ±30s context window reference
- Change macro dynamics default from 3.5 dB to Off (0)
- Add macro dynamics recommendation to analyser based on dynamic range
- Add `bass_side_mix` to analyser recommended output
- Fix `applyRecommendations` reading from wrong level of analyser response
- Fix Use in tool silently failing on Master and Repair tabs (missing `dataset.filename`)
- Fix Repair tab not receiving shared file propagation
- Fix `async` keyword missing from `useInTool` function
- Fix stray `vb` undefined variable in `applyRecommendations` status text
- Add `resetAllTabs()` — clears all result states when new file is loaded
- Split tab bar into Mastering and Repair & Restoration groups
- Add descriptive info block to every panel with when-to-use guidance
- Update version to v1.2 across all files and launchers
