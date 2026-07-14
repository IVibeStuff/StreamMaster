#!/usr/bin/env python3
"""
levelbridge.py — Ride the gain across a quiet region to match surrounding levels.

Automatically detects and patches sharp seam steps at the region boundary
before applying the broader gain bridge, so both a heal artefact and a
structural level dip are fixed in one pass.

Usage (CLI):
    python levelbridge.py track.wav --start 105 --end 135 [--output out.wav]

    --start : start of the quiet region (seconds)
    --end   : end of the quiet region (seconds)
    --output: output path (default: track_bridged.wav)
"""

import argparse
import numpy as np
import soundfile as sf
from scipy.ndimage import gaussian_filter1d
from pathlib import Path


def load(path):
    audio, sr = sf.read(path, always_2d=True)
    return audio.astype(np.float64), sr


def rms_db(chunk):
    rms = np.sqrt(np.mean(chunk ** 2))
    return 20.0 * np.log10(max(rms, 1e-12))


def _build_gain_curve(audio, sr, start_s, end_s, db_target_start, db_target_end,
                      hop_ms=100, smooth_ms=250):
    """
    Build a sample-resolution gain curve (in dB) that smoothly rides the level
    from db_target_start to db_target_end across [start_s, end_s].
    """
    n = len(audio)
    region_len = end_s - start_s
    hop = int(hop_ms * 1e-3 * sr)
    hops = list(range(start_s, end_s, hop))
    hop_gains = []

    for h in hops:
        lo = max(0, h - hop)
        hi = min(n, h + hop)
        local_db = rms_db(audio[lo:hi])
        t = (h - start_s) / region_len
        t_smooth = (1 - np.cos(t * np.pi)) / 2          # S-curve 0→1
        target_db = db_target_start + (db_target_end - db_target_start) * t_smooth
        hop_gains.append(target_db - local_db)

    hop_gains = np.array(hop_gains)
    xs = np.array([h - start_s for h in hops])
    xi = np.arange(region_len)
    curve = np.interp(xi, xs, hop_gains)
    curve = gaussian_filter1d(curve, sigma=int(smooth_ms * 1e-3 * sr))
    return curve


def _patch_seam(audio, result, sr, seam_s, window_s=2.0,
                step_threshold_db=2.0, patch_width_s=2.0):
    """
    Detect a sharp level step at seam_s and apply a localised gain patch
    to smooth it out.  Returns the patched result and whether a patch was applied.
    """
    n = len(audio)
    win = int(window_s * sr)
    ctx_before = audio[max(0, seam_s - win) : seam_s]
    ctx_after  = audio[seam_s : min(n, seam_s + win)]

    if len(ctx_before) == 0 or len(ctx_after) == 0:
        return result, False

    db_bef = rms_db(ctx_before)
    db_aft = rms_db(ctx_after)
    step   = db_aft - db_bef

    if abs(step) < step_threshold_db:
        print(f"  Seam check @ {seam_s/sr:.1f}s : step {step:+.1f} dB — no patch needed")
        return result, False

    print(f"  Seam patch @ {seam_s/sr:.1f}s : {step:+.1f} dB step detected — patching")

    # Patch region: seam ± half the patch width
    patch_half  = int(patch_width_s / 2 * sr)
    patch_start = max(0, seam_s - patch_half)
    patch_end   = min(n, seam_s + patch_half)
    patch_len   = patch_end - patch_start

    # Target = split the difference so both sides meet in the middle
    target_db = (db_bef + db_aft) / 2

    hop = int(0.05 * sr)   # 50ms hops — finer than the main bridge
    hops = list(range(patch_start, patch_end, hop))
    gains = []
    for h in hops:
        lo = max(0, h - hop); hi = min(n, h + hop)
        local = rms_db(result[lo:hi])
        gains.append(target_db - local)

    gains = np.array(gains)
    xs = np.array([h - patch_start for h in hops])
    xi = np.arange(patch_len)
    gc = np.interp(xi, xs, gains)
    gc = gaussian_filter1d(gc, sigma=int(0.05 * sr))

    # Ramp in and out so the patch doesn't itself create a click
    ramp = min(int(0.15 * sr), patch_len // 4)
    gc[:ramp]  *= np.linspace(0, 1, ramp)
    gc[-ramp:] *= np.linspace(1, 0, ramp)

    patched = result.copy()
    patched[patch_start:patch_end] *= 10.0 ** (gc[:, np.newaxis] / 20.0)
    return patched, True


def level_bridge(
    input_path:  str,
    start_time:  float,
    end_time:    float,
    output_path: str | None = None,
) -> str:

    if output_path is None:
        p = Path(input_path)
        output_path = str(p.parent / (p.stem + "_bridged.wav"))

    print("\n╔══════════════════════════════════════════════════════╗")
    print("║              Level Bridge                            ║")
    print("╚══════════════════════════════════════════════════════╝")

    audio, sr = load(input_path)
    n = len(audio)
    print(f"  Track    : {input_path}  ({sr} Hz, {audio.shape[1]}ch, {n/sr:.2f}s)")

    start_s = int(start_time * sr)
    end_s   = int(end_time   * sr)

    if not (0 < start_s < end_s < n):
        raise ValueError(f"start/end out of range for track ({n/sr:.2f}s)")

    ctx_win   = int(3.0 * sr)
    db_before = rms_db(audio[max(0, start_s - ctx_win) : start_s])
    db_after  = rms_db(audio[end_s : min(n, end_s + ctx_win)])
    db_inside = rms_db(audio[start_s : end_s])

    print(f"  Before   : {db_before:+.2f} dBRMS")
    print(f"  Inside   : {db_inside:+.2f} dBRMS")
    print(f"  After    : {db_after:+.2f} dBRMS")

    result = audio.copy()

    # ── Step 1: Seam patch at start boundary ─────────────────────────────────
    # Check for a sharp step at start_s and patch if found.
    # The patch straddles the boundary so it smooths both sides.
    result, patched_start = _patch_seam(
        audio, result, sr,
        seam_s=start_s,
        window_s=1.5,
        step_threshold_db=2.0,
        patch_width_s=2.0,
    )

    # ── Step 2: Seam patch at end boundary ───────────────────────────────────
    result, patched_end = _patch_seam(
        audio, result, sr,
        seam_s=end_s,
        window_s=1.5,
        step_threshold_db=2.0,
        patch_width_s=2.0,
    )

    # ── Step 3: Broad gain bridge across the full region ─────────────────────
    # Re-measure levels after patching so the bridge uses accurate context.
    db_before_now = rms_db(result[max(0, start_s - ctx_win) : start_s])
    db_after_now  = rms_db(result[end_s : min(n, end_s + ctx_win)])

    region_len  = end_s - start_s
    gain_curve  = _build_gain_curve(
        result, sr, start_s, end_s,
        db_before_now, db_after_now,
        hop_ms=100, smooth_ms=250,
    )

    # Ramp-in only — the S-curve handles the tail naturally
    ramp_len = min(int(0.2 * sr), region_len // 8)
    gain_curve[:ramp_len] *= np.linspace(0, 1, ramp_len)

    print(f"  Gain ride: {gain_curve.min():+.2f} to {gain_curve.max():+.2f} dB "
          f"across {end_time - start_time:.1f}s")

    result[start_s:end_s] *= 10.0 ** (gain_curve[:, np.newaxis] / 20.0)

    # ── Export ────────────────────────────────────────────────────────────────
    result = np.clip(result, -1.0, 1.0)
    dither_amp = 1.0 / (2 ** 15)
    dither = (np.random.uniform(-1, 1, result.shape)
              + np.random.uniform(-1, 1, result.shape)) * dither_amp * 0.5
    sf.write(output_path, result + dither, sr, subtype='PCM_16')

    size_kb = Path(output_path).stat().st_size / 1024
    print(f"  Export   : {output_path}  ({size_kb:.0f} KB)")
    print("\n✓ Level bridge done\n")
    return output_path


def main():
    p = argparse.ArgumentParser(description="Ride gain across a quiet region.")
    p.add_argument("input")
    p.add_argument("--start",  type=float, required=True)
    p.add_argument("--end",    type=float, required=True)
    p.add_argument("--output", default=None)
    args = p.parse_args()
    level_bridge(args.input, args.start, args.end, args.output)


if __name__ == "__main__":
    main()
