#!/usr/bin/env python3
"""
dejinx.py — Automatically detect and repair micro-dropout artefacts.

Suno (and some other AI audio models) occasionally produce brief synthesis
dropouts: zones of 20–300ms where the output level collapses 6+ dB below
the surrounding audio before snapping back to normal. These sound like a
metallic shimmer, flutter, or brief hollow silence — what you might call a
"jinx".

This tool:
  1. Scans the track for micro-dropouts (short zones significantly quieter
     than their context)
  2. For each dropout, measures the level just before and just after
  3. Applies a smooth gain curve to fill in the dip
  4. Leaves everything else completely untouched

Usage (CLI):
    python dejinx.py track.wav [--output out.wav] [--threshold 6] [--max-dur 300]

    --threshold : dB drop below context that triggers a fix (default 10)
    --max-dur   : maximum dropout duration in ms to fix (default 300)
    --min-dur   : minimum dropout duration in ms to fix (default 80)
    --output    : output path (default: track_dejinxed.wav)
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


def dejinx(
    input_path:   str,
    output_path:  str | None = None,
    threshold_db: float = 10.0,  # was 6 — needs to be high enough to skip beat gaps
    min_dur_ms:   float = 80.0,  # was 20 — beat gaps are typically 20-70ms, skip them
    max_dur_ms:   float = 300.0,
    context_ms:   float = 500.0, # was 150 — needs to span a full musical phrase
) -> str:

    if output_path is None:
        p = Path(input_path)
        output_path = str(p.parent / (p.stem + "_dejinxed.wav"))

    print("\n╔══════════════════════════════════════════════════════╗")
    print("║              De-Jinx                                 ║")
    print("╚══════════════════════════════════════════════════════╝")

    audio, sr = load(input_path)
    n = len(audio)
    print(f"  Track    : {input_path}")
    print(f"  Duration : {n/sr:.2f}s  |  {sr}Hz  |  {audio.shape[1]}ch")
    print(f"  Settings : threshold={threshold_db}dB  "
          f"min={min_dur_ms}ms  max={max_dur_ms}ms")

    ctx_samples = int(context_ms * 1e-3 * sr)
    min_samples = int(min_dur_ms  * 1e-3 * sr)
    max_samples = int(max_dur_ms  * 1e-3 * sr)

    # ── Step 1: Build a short-term RMS envelope ───────────────────────────────
    # 5ms hop, 20ms window — fine enough to catch 20ms dropouts
    hop = int(0.005 * sr)
    win = int(0.020 * sr)
    n_frames = (n - win) // hop

    envelope_db = np.zeros(n_frames)
    for i in range(n_frames):
        pos = i * hop
        envelope_db[i] = rms_db(audio[pos : pos + win])

    # ── Step 2: Smooth the envelope to get a "expected level" reference ───────
    # Use a wide median-like filter: for each frame, the context level is the
    # median of the surrounding 500ms, which ignores the dropout itself
    ctx_frames = int(context_ms * 1e-3 * sr / hop)
    context_db = np.zeros(n_frames)
    for i in range(n_frames):
        lo = max(0, i - ctx_frames)
        hi = min(n_frames, i + ctx_frames)
        # Exclude the central 20% to avoid the dropout influencing its own context
        window = np.concatenate([envelope_db[lo : max(lo, i - ctx_frames//5)],
                                  envelope_db[min(hi, i + ctx_frames//5) : hi]])
        if len(window) > 0:
            context_db[i] = np.percentile(window, 60)  # 60th percentile = typical level
        else:
            context_db[i] = envelope_db[i]

    # ── Step 3: Find dropout zones ────────────────────────────────────────────
    drop = context_db - envelope_db   # positive = quieter than context
    is_dropout = drop > threshold_db

    # Find contiguous dropout runs
    dropouts = []
    in_dropout = False
    start_frame = 0
    for i in range(n_frames):
        if is_dropout[i] and not in_dropout:
            in_dropout = True
            start_frame = i
        elif not is_dropout[i] and in_dropout:
            in_dropout = False
            dur_samples = (i - start_frame) * hop
            if min_samples <= dur_samples <= max_samples:
                dropouts.append((start_frame * hop, i * hop, dur_samples))

    print(f"  Found    : {len(dropouts)} dropout(s) to repair")

    if not dropouts:
        print("  Nothing to fix — exporting unchanged")
        sf.write(output_path, audio, sr, subtype='PCM_16')
        return output_path

    # ── Step 4: Repair each dropout ───────────────────────────────────────────
    result = audio.copy()
    repairs = 0

    for start_s, end_s, dur_s in dropouts:
        # Measure level in context windows either side
        before_lo = max(0, start_s - ctx_samples)
        after_hi  = min(n, end_s   + ctx_samples)

        before_chunk = audio[before_lo : start_s]
        after_chunk  = audio[end_s     : after_hi]

        # Skip if context is also quiet (silence is intentional)
        if len(before_chunk) == 0 or len(after_chunk) == 0:
            continue

        db_before = rms_db(before_chunk)
        db_after  = rms_db(after_chunk)
        db_inside = rms_db(audio[start_s : end_s])

        # Skip if surrounding context is also quiet
        ctx_level = max(db_before, db_after)
        if ctx_level < -35:
            continue

        actual_drop = ctx_level - db_inside
        if actual_drop < threshold_db * 0.8:
            continue

        t_start = start_s / sr
        m, sec  = divmod(t_start, 60)
        print(f"  Repairing {int(m)}:{sec:05.2f}  "
              f"dur={dur_s/sr*1000:.0f}ms  "
              f"drop={actual_drop:.1f}dB  "
              f"({db_inside:.1f}→{ctx_level:.1f} dBRMS)")

        # ── Transient smoothing ───────────────────────────────────────────────
        # Check if there's a loud transient in the 300ms before the dropout
        # that's disproportionate vs the broader 1.5s context.
        # Use short-window peak RMS to catch brief transients that avg out.
        pre_window   = int(0.300 * sr)
        broad_window = int(1.500 * sr)
        short_hop    = max(1, int(0.020 * sr))  # 20ms hops to catch brief peaks

        pre_start  = max(0, start_s - pre_window)
        broad_start= max(0, start_s - broad_window)
        pre_audio  = result[pre_start:start_s]
        broad_audio= result[broad_start:start_s]

        if len(pre_audio) >= short_hop * 2 and len(broad_audio) >= short_hop * 4:
            # Peak short-window RMS in the pre-window
            pre_n = len(pre_audio)
            pre_hops = (pre_n + short_hop - 1) // short_hop
            pre_pad = np.pad(pre_audio.mean(axis=1)**2, (0, pre_hops*short_hop - pre_n))
            pre_rms_hops = np.sqrt(np.mean(pre_pad.reshape(pre_hops, short_hop), axis=1)+1e-24)
            pre_peak_rms = 20*np.log10(pre_rms_hops.max()+1e-12)

            # Median short-window RMS across the broad window (robust context)
            brd_n = len(broad_audio)
            brd_hops = (brd_n + short_hop - 1) // short_hop
            brd_pad = np.pad(broad_audio.mean(axis=1)**2, (0, brd_hops*short_hop - brd_n))
            brd_rms_hops = np.sqrt(np.mean(brd_pad.reshape(brd_hops, short_hop), axis=1)+1e-24)
            broad_median_rms = 20*np.log10(np.median(brd_rms_hops)+1e-12)

            transient_excess = pre_peak_rms - broad_median_rms

            if transient_excess > 4.0:
                # Find the loudest short window in the pre-zone and taper it down
                reduction_db  = min((transient_excess - 4.0) * 0.6, 5.0)
                reduction_lin = 10.0 ** (-reduction_db / 20.0)

                # Find which hop is the peak and apply a centred Gaussian taper
                peak_hop_idx = int(np.argmax(pre_rms_hops))
                peak_sample  = pre_start + peak_hop_idx * short_hop
                taper_width  = int(0.080 * sr)  # 80ms taper width
                taper_lo     = max(0, peak_sample - taper_width)
                taper_hi     = min(n, peak_sample + taper_width)
                taper_len    = taper_hi - taper_lo

                # Gaussian-shaped gain dip centred on the peak
                x = np.linspace(-3, 3, taper_len)
                taper = 1.0 - (1.0 - reduction_lin) * np.exp(-0.5 * x**2)
                result[taper_lo:taper_hi] *= taper[:, np.newaxis]

                print(f"             transient -{reduction_db:.1f}dB at "
                      f"{peak_sample/sr:.2f}s  "
                      f"(peak {pre_peak_rms:.1f} vs context {broad_median_rms:.1f} dBRMS)")

        # Build gain curve: S-curve from db_before to db_after
        region_len = end_s - start_s
        if region_len < 2:
            continue

        hop2 = max(1, int(0.005 * sr))
        hops = list(range(start_s, end_s, hop2))
        gains = []
        for h in hops:
            lo = max(0, h - hop2); hi = min(n, h + hop2)
            local = rms_db(result[lo:hi])
            t = (h - start_s) / region_len
            t_s = (1 - np.cos(t * np.pi)) / 2
            target = db_before + (db_after - db_before) * t_s
            gains.append(target - local)

        gains = np.array(gains)
        xs = np.array([h - start_s for h in hops])
        xi = np.arange(region_len)
        gain_curve = np.interp(xi, xs, gains)
        gain_curve = gaussian_filter1d(gain_curve, sigma=max(1, int(0.01 * sr)))

        # Short ramp in/out at edges to avoid clicks
        ramp = min(int(0.015 * sr), region_len // 4)
        gain_curve[:ramp]  *= np.linspace(0, 1, ramp)
        gain_curve[-ramp:] *= np.linspace(1, 0, ramp)

        result[start_s:end_s] *= 10.0 ** (gain_curve[:, np.newaxis] / 20.0)
        repairs += 1

    print(f"  Repaired : {repairs} dropout(s)")

    # ── Export ────────────────────────────────────────────────────────────────
    result = np.clip(result, -1.0, 1.0)
    dither_amp = 1.0 / (2 ** 15)
    dither = (np.random.uniform(-1, 1, result.shape)
              + np.random.uniform(-1, 1, result.shape)) * dither_amp * 0.5
    sf.write(output_path, result + dither, sr, subtype='PCM_16')
    size_kb = Path(output_path).stat().st_size / 1024
    print(f"  Export   : {output_path}  ({size_kb:.0f} KB)")
    print("\n✓ De-jinx done\n")
    return output_path


def main():
    p = argparse.ArgumentParser(description="Auto-repair micro-dropout artefacts.")
    p.add_argument("input")
    p.add_argument("--output",    default=None)
    p.add_argument("--threshold", type=float, default=10.0)
    p.add_argument("--min-dur",   type=float, default=80.0)
    p.add_argument("--max-dur",   type=float, default=300.0)
    args = p.parse_args()
    dejinx(args.input, args.output, args.threshold, args.min_dur, args.max_dur)


if __name__ == "__main__":
    main()
