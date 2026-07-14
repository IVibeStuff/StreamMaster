#!/usr/bin/env python3
"""
qc.py — Quality control check on a processed WAV file.

Checks for:
  1. File integrity    — WAV header valid, file not truncated
  2. Clipping          — samples at or above 0 dBFS
  3. DC offset         — sustained DC bias that causes thumps
  4. Dropout artifacts — sudden level collapses (buffer underruns, copy errors)
  5. Click/pop artifacts — sample-level discontinuities from file write errors
  6. Silence           — unexpected silent sections mid-track
  7. Phase coherence   — L/R correlation anomalies
  8. LUFS verification — output matches expected target
  9. True peak verify  — output stays within ceiling

Returns a dict of findings. Pass = all clear, Warn = worth noting, Fail = audible problem.
"""

import numpy as np
import soundfile as sf
from scipy import signal
from scipy.ndimage import gaussian_filter1d
from pathlib import Path


def _rms_db(x):  return 20.0 * np.log10(np.sqrt(np.mean(x**2)) + 1e-12)
def _peak_db(x): return 20.0 * np.log10(np.max(np.abs(x)) + 1e-12)


def qc_check(path: str, expected_lufs: float = -14.0,
             expected_peak_db: float = -1.0) -> dict:
    """
    Run all QC checks on the output WAV.
    Returns dict with keys: pass (bool), issues (list), warnings (list), stats (dict)
    """
    issues   = []   # audible problems → fail
    warnings = []   # worth noting → warn
    stats    = {}

    # ── 1. File integrity ────────────────────────────────────────────────────
    p = Path(path)
    if not p.exists():
        return dict(passed=False, issues=["File does not exist"], warnings=[], stats={})
    if p.stat().st_size < 1024:
        return dict(passed=False, issues=["File too small — likely corrupt"], warnings=[], stats={})

    try:
        audio, sr = sf.read(path, always_2d=True)
        audio = audio.astype(np.float64)
    except Exception as e:
        return dict(passed=False, issues=[f"Cannot read WAV: {e}"], warnings=[], stats={})

    n  = len(audio)
    ch = audio.shape[1]
    dur = n / sr
    stats['duration_s']  = round(dur, 2)
    stats['sample_rate'] = sr
    stats['channels']    = ch
    stats['file_size_mb'] = round(p.stat().st_size / (1024*1024), 2)

    if dur < 1.0:
        issues.append("Duration under 1 second — likely truncated")

    # ── 2. Clipping ──────────────────────────────────────────────────────────
    peak = float(np.max(np.abs(audio)))
    peak_db = 20 * np.log10(peak + 1e-12)
    stats['peak_db'] = round(peak_db, 2)
    clipped_samples = int(np.sum(np.abs(audio) >= 0.9999))
    if clipped_samples > 0:
        issues.append(f"Clipping: {clipped_samples} samples at or above 0 dBFS")
    elif peak_db > expected_peak_db + 0.5:
        warnings.append(f"Peak {peak_db:.1f} dBFS exceeds target {expected_peak_db} dBTP")

    # ── 3. DC offset ─────────────────────────────────────────────────────────
    dc = float(np.abs(audio.mean()))
    stats['dc_offset'] = round(dc, 6)
    if dc > 0.01:
        issues.append(f"DC offset {dc:.4f} — may cause thump on playback")
    elif dc > 0.003:
        warnings.append(f"Slight DC offset {dc:.4f}")

    # ── 4. Dropout artifacts (buffer underruns / copy errors) ────────────────
    # A real copy-error dropout is near-silent (< -60 dBRMS) in the middle
    # of active audio. Musical quiet passages are typically -25 to -45 dBRMS.
    # We require the dropout floor to be < -55 dBRMS AND at least 18 dB below
    # a wide context window to avoid flagging musical dynamics.
    mono    = audio.mean(axis=1)
    hop     = max(1, int(0.005 * sr))   # 5ms hops (less sensitive than 2ms)
    n_hops  = (n + hop - 1) // hop
    padded  = np.pad(mono**2, (0, n_hops*hop - n))
    rms_hop = np.sqrt(np.mean(padded.reshape(n_hops, hop), axis=1) + 1e-24)
    rms_db  = 20 * np.log10(rms_hop + 1e-12)

    # Context: 500ms window (wider = less false positives)
    ctx_frames = int(0.500 * sr / hop)
    dropouts   = []
    for i in range(ctx_frames, n_hops - ctx_frames):
        if rms_db[i] > -55:          # not silent enough to be a dropout
            continue
        lo  = max(0, i - ctx_frames)
        hi  = min(n_hops, i + ctx_frames)
        ctx = np.percentile(rms_db[lo:hi], 60)
        if ctx - rms_db[i] > 18:    # 18 dB below context (was 12)
            t = i * hop / sr
            # Skip first and last 1s (fade in/out)
            if t > 1.0 and t < (n/sr - 1.0):
                dropouts.append(round(t, 2))

    # Deduplicate nearby dropouts (within 100ms)
    deduped = []
    for t in dropouts:
        if not deduped or t - deduped[-1] > 0.1:
            deduped.append(t)

    stats['dropout_count'] = len(deduped)
    if deduped:
        times = ', '.join(f'{int(t//60)}:{t%60:.1f}s' for t in deduped[:5])
        issues.append(f"Buffer dropout artifact(s) at: {times}"
                      + (' (+more)' if len(deduped) > 5 else ''))

    # ── 5. Click/pop artifacts (sample-level discontinuities) ────────────────
    # Sudden large sample-to-sample jumps that aren't part of the signal
    diff   = np.abs(np.diff(mono))
    # A click is a jump > 0.1 linear where the surrounding signal is quiet
    threshold = 0.1
    jump_idx  = np.where(diff > threshold)[0]
    clicks    = []
    for idx in jump_idx:
        # Only flag if surrounding 10ms context is much quieter
        ctx_s = max(0, idx - int(0.010*sr))
        ctx_e = min(n, idx + int(0.010*sr))
        ctx_rms = np.sqrt(np.mean(mono[ctx_s:ctx_e]**2) + 1e-24)
        if diff[idx] > ctx_rms * 10:
            t = idx / sr
            clicks.append(round(t, 3))

    # Deduplicate within 50ms
    deduped_clicks = []
    for t in clicks:
        if not deduped_clicks or t - deduped_clicks[-1] > 0.05:
            deduped_clicks.append(t)

    stats['click_count'] = len(deduped_clicks)
    if deduped_clicks:
        times = ', '.join(f'{int(t//60)}:{t%60:.2f}s' for t in deduped_clicks[:5])
        issues.append(f"Click/pop artifact(s) at: {times}"
                      + (' (+more)' if len(deduped_clicks) > 5 else ''))

    # ── 6. Unexpected silence ────────────────────────────────────────────────
    # Flag silence blocks > 2s that aren't at the start/end
    silence_thresh_db = -60
    silent_hops = rms_db < silence_thresh_db
    in_silence  = False
    sil_start   = 0
    long_silences = []
    for i in range(n_hops):
        if silent_hops[i] and not in_silence:
            in_silence = True; sil_start = i
        elif not silent_hops[i] and in_silence:
            in_silence = False
            dur_s = (i - sil_start) * hop / sr
            t_s   = sil_start * hop / sr
            # Skip silence in first/last 2s
            if dur_s > 2.0 and t_s > 2.0 and (t_s + dur_s) < (n/sr - 2.0):
                long_silences.append((round(t_s,1), round(dur_s,1)))

    stats['mid_track_silences'] = len(long_silences)
    if long_silences:
        desc = ', '.join(f'{int(t//60)}:{t%60:.0f}s ({d:.1f}s)'
                         for t,d in long_silences[:3])
        warnings.append(f"Unexpected mid-track silence: {desc}")

    # ── 7. Phase coherence ───────────────────────────────────────────────────
    if ch == 2:
        # Sample correlation in 500ms blocks — flag sustained anti-phase
        block = int(0.5 * sr)
        anti_phase_blocks = 0
        for i in range(0, n - block, block):
            L = audio[i:i+block, 0]; R = audio[i:i+block, 1]
            if np.std(L) > 1e-6 and np.std(R) > 1e-6:
                corr = np.corrcoef(L, R)[0, 1]
                if corr < -0.5:
                    anti_phase_blocks += 1
        stats['anti_phase_blocks'] = anti_phase_blocks
        if anti_phase_blocks > 2:
            warnings.append(f"Sustained anti-phase content in {anti_phase_blocks} blocks "
                            f"(may cancel in mono)")

    # ── 8. LUFS verification ─────────────────────────────────────────────────
    try:
        import pyloudnorm as pyln
        meter = pyln.Meter(sr)
        lufs  = meter.integrated_loudness(audio)
        stats['lufs'] = round(lufs, 2)
        if abs(lufs - expected_lufs) > 1.0:
            warnings.append(f"LUFS {lufs:.1f} — expected {expected_lufs} "
                            f"(diff {lufs-expected_lufs:+.1f} dB)")
    except Exception:
        stats['lufs'] = None

    # ── 9. True peak verify ──────────────────────────────────────────────────
    # Oversample 4× in chunks to verify true peak
    chunk = sr
    tp = 0.0
    for lo in range(0, n, chunk):
        up = signal.resample_poly(audio[lo:lo+chunk], 4, 1, axis=0)
        tp = max(tp, float(np.max(np.abs(up))))
    tp_db = 20 * np.log10(tp + 1e-12)
    stats['true_peak_db'] = round(tp_db, 2)
    if tp_db > expected_peak_db + 0.3:
        warnings.append(f"True peak {tp_db:.1f} dBTP exceeds target {expected_peak_db} dBTP")

    # ── Summary ──────────────────────────────────────────────────────────────
    passed = len(issues) == 0
    return dict(passed=passed, issues=issues, warnings=warnings, stats=stats)


if __name__ == '__main__':
    import sys, json
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path:
        print("Usage: python qc.py output.wav"); sys.exit(1)
    result = qc_check(path)
    status = '✓ PASS' if result['passed'] else '✗ FAIL'
    print(f"\n{status}  —  {path}")
    if result['issues']:
        print("  ISSUES (audible):")
        for i in result['issues']: print(f"    ✗ {i}")
    if result['warnings']:
        print("  WARNINGS:")
        for w in result['warnings']: print(f"    ⚠ {w}")
    s = result['stats']
    print(f"  Stats: {s.get('duration_s')}s  "
          f"{s.get('lufs')} LUFS  "
          f"peak {s.get('peak_db')} dBFS  "
          f"true peak {s.get('true_peak_db')} dBTP")
