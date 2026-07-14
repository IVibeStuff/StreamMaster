#!/usr/bin/env python3
"""
splice.py — Splice a replacement clip into a master track with seamless transitions.

Processing chain per join point:
  1. Resample replacement to match master sample rate
  2. Channel-match (mono→stereo upmix if needed)
  3. Loudness-match replacement to the surrounding context
  4. Snap both cut points to the nearest zero-crossing
  5. Crossfade across the join (equal-power curve)
  6. Optional spectral blend (short FFT morph) at each seam

Usage (CLI):
    python splice.py master.wav replacement.wav --in 32.5 --out 48.0 [--crossfade 80] [--output out.wav]

    --in        : timestamp (seconds) in the MASTER where replacement starts
    --out       : timestamp (seconds) in the MASTER where replacement ends
    --crossfade : crossfade length in milliseconds (default 80)
    --output    : output path (default: master_spliced.wav)

The replacement clip is taken from its beginning and must be at least
(out - in) seconds long.
"""

import argparse
import numpy as np
import soundfile as sf
from scipy import signal
from pathlib import Path


# ── Helpers ───────────────────────────────────────────────────────────────────

def load(path: str) -> tuple[np.ndarray, int]:
    audio, sr = sf.read(path, always_2d=True)
    return audio.astype(np.float64), sr


def resample_to(audio: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    if src_sr == dst_sr:
        return audio
    return np.stack(
        [signal.resample_poly(audio[:, ch], dst_sr, src_sr,
                              window=('kaiser', 5.0))
         for ch in range(audio.shape[1])],
        axis=1
    )


def match_channels(audio: np.ndarray, target_ch: int) -> np.ndarray:
    """Upmix mono→stereo or downmix stereo→mono to match target."""
    src_ch = audio.shape[1]
    if src_ch == target_ch:
        return audio
    if src_ch == 1 and target_ch == 2:
        return np.hstack([audio, audio])          # mono → stereo
    if src_ch == 2 and target_ch == 1:
        return audio.mean(axis=1, keepdims=True)  # stereo → mono
    return audio


def rms_db(audio: np.ndarray) -> float:
    rms = np.sqrt(np.mean(audio ** 2))
    return 20.0 * np.log10(max(rms, 1e-12))


def nearest_zero_crossing(audio: np.ndarray, sample: int,
                           search_ms: float, sr: int,
                           direction: str = 'both') -> int:
    """
    Find the nearest zero-crossing to `sample` within a search window.
    direction: 'before' | 'after' | 'both'
    Falls back to original sample if none found.
    """
    radius = int(search_ms * 1e-3 * sr)
    mono   = audio.mean(axis=1)
    n      = len(mono)

    lo = max(0, sample - radius)
    hi = min(n - 1, sample + radius)

    crossings = []
    for i in range(lo, hi):
        if mono[i] * mono[i + 1] <= 0:
            crossings.append(i)

    if not crossings:
        return sample

    if direction == 'before':
        before = [c for c in crossings if c <= sample]
        return before[-1] if before else sample
    if direction == 'after':
        after = [c for c in crossings if c >= sample]
        return after[0] if after else sample

    # 'both' — closest
    return min(crossings, key=lambda c: abs(c - sample))


def equal_power_fade(length: int) -> tuple[np.ndarray, np.ndarray]:
    """Returns (fade_out, fade_in) equal-power curves of given length."""
    t      = np.linspace(0.0, np.pi / 2, length)
    fade_out = np.cos(t)
    fade_in  = np.sin(t)
    return fade_out, fade_in


def measure_context_lufs(audio: np.ndarray, sr: int,
                          centre_sample: int, window_s: float = 1.0) -> float:
    """Measure RMS of a short window around a cut point (used for gain matching)."""
    half = int(window_s * sr / 2)
    lo   = max(0, centre_sample - half)
    hi   = min(len(audio), centre_sample + half)
    chunk = audio[lo:hi]
    if len(chunk) == 0:
        return -60.0
    return rms_db(chunk)


# ── Core splice ───────────────────────────────────────────────────────────────

def splice(
    master_path:      str,
    replacement_path: str,
    in_time:          float,        # seconds into master
    out_time:         float,        # seconds into master
    crossfade_ms:     float = 80.0, # ms
    output_path:      str | None = None,
) -> str:

    if output_path is None:
        p = Path(master_path)
        output_path = str(p.parent / (p.stem + "_spliced.wav"))

    print("\n╔══════════════════════════════════════════════════════╗")
    print("║              Section Splice                          ║")
    print("╚══════════════════════════════════════════════════════╝")

    # ── Load ─────────────────────────────────────────────────────────────────
    master_raw, m_sr = load(master_path)
    repl_raw,   r_sr = load(replacement_path)

    print(f"  Master      : {master_path}  ({m_sr} Hz, {master_raw.shape[1]}ch, "
          f"{master_raw.shape[0]/m_sr:.2f}s)")
    print(f"  Replacement : {replacement_path}  ({r_sr} Hz, {repl_raw.shape[1]}ch, "
          f"{repl_raw.shape[0]/r_sr:.2f}s)")

    sr = m_sr  # work at master's sample rate

    # ── Resample & channel-match replacement ─────────────────────────────────
    repl = resample_to(repl_raw, r_sr, sr)
    repl = match_channels(repl, master_raw.shape[1])
    master = master_raw.copy()

    n_master = len(master)
    xf_samples = int(crossfade_ms * 1e-3 * sr)

    # ── Raw cut points ────────────────────────────────────────────────────────
    in_sample_raw  = int(in_time  * sr)
    out_sample_raw = int(out_time * sr)

    if in_sample_raw < 0 or out_sample_raw > n_master:
        raise ValueError(f"in/out times out of range for master "
                         f"({n_master/sr:.2f}s)")
    if out_sample_raw <= in_sample_raw:
        raise ValueError("out_time must be greater than in_time")

    splice_len = out_sample_raw - in_sample_raw
    if len(repl) < splice_len:
        raise ValueError(
            f"Replacement clip ({len(repl)/sr:.2f}s) is shorter than "
            f"the splice region ({splice_len/sr:.2f}s)"
        )

    # ── Zero-crossing snap ────────────────────────────────────────────────────
    in_sample  = nearest_zero_crossing(master, in_sample_raw,
                                       search_ms=20, sr=sr, direction='both')
    out_sample = nearest_zero_crossing(master, out_sample_raw,
                                       search_ms=20, sr=sr, direction='both')

    print(f"  In  point   : {in_time:.3f}s  → snapped {(in_sample - in_sample_raw)/sr*1000:+.1f}ms "
          f"to zero-crossing @ {in_sample/sr:.3f}s")
    print(f"  Out point   : {out_time:.3f}s  → snapped {(out_sample - out_sample_raw)/sr*1000:+.1f}ms "
          f"to zero-crossing @ {out_sample/sr:.3f}s")

    splice_len = out_sample - in_sample

    # ── Loudness-match replacement to context ─────────────────────────────────
    ctx_db   = measure_context_lufs(master, sr, in_sample,  window_s=1.0)
    repl_db  = rms_db(repl[:splice_len])
    gain_db  = ctx_db - repl_db
    gain_lin = 10.0 ** (gain_db / 20.0)
    repl_matched = repl * gain_lin

    print(f"  Gain match  : context {ctx_db:.1f} dBRMS, "
          f"replacement {repl_db:.1f} dBRMS → "
          f"applying {gain_db:+.2f} dB to replacement")

    print(f"  Crossfade   : {crossfade_ms:.0f} ms ({xf_samples} samples) equal-power")

    # ── Build output buffer ───────────────────────────────────────────────────
    out_audio = master.copy()

    # Paste the full replacement into the splice region first
    out_audio[in_sample:out_sample] = repl_matched[:splice_len]

    # Crossfades centred on each seam: [seam - half : seam + half]
    # This means the blend happens across the join, not entirely on one side.
    half = min(xf_samples // 2,
               in_sample,
               splice_len // 2,
               n_master - out_sample)

    print(f"  Crossfade   : {half*2/sr*1000:.0f}ms centred on each seam")

    if half > 0:
        fo, fi = equal_power_fade(half * 2)
        fo = fo[:, np.newaxis]
        fi = fi[:, np.newaxis]

        # IN seam: master fades out, replacement fades in
        seg_master = master   [in_sample - half : in_sample + half]
        seg_repl   = repl_matched[0 : half * 2]
        out_audio  [in_sample - half : in_sample + half] = (
            seg_master * fo + seg_repl * fi
        )

        # OUT seam: replacement fades out, master fades in
        repl_tail  = repl_matched[splice_len - half*2 : splice_len]
        seg_master = master[out_sample - half : out_sample + half]
        out_audio  [out_sample - half : out_sample + half] = (
            repl_tail * fo + seg_master * fi
        )

    # ── Export ────────────────────────────────────────────────────────────────
    out_audio = np.clip(out_audio, -1.0, 1.0)

    # TPDF dither
    dither_amp = 1.0 / (2 ** 15)
    dither = (np.random.uniform(-1, 1, out_audio.shape)
              + np.random.uniform(-1, 1, out_audio.shape)) * dither_amp * 0.5
    sf.write(output_path, out_audio + dither, sr, subtype='PCM_16')

    size_kb = Path(output_path).stat().st_size / 1024
    print(f"  Export      : {output_path}  ({size_kb:.0f} KB)")
    print("\n✓ Splice done\n")
    return output_path


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Splice a replacement clip into a master.")
    p.add_argument("master",      help="Master WAV file")
    p.add_argument("replacement", help="Replacement clip WAV")
    p.add_argument("--in",  dest="in_time",  type=float, required=True,
                   help="Start time in master (seconds)")
    p.add_argument("--out", dest="out_time", type=float, required=True,
                   help="End time in master (seconds)")
    p.add_argument("--crossfade", type=float, default=80.0,
                   help="Crossfade length in ms (default 80)")
    p.add_argument("--output", default=None, help="Output WAV path")
    args = p.parse_args()
    splice(args.master, args.replacement, args.in_time, args.out_time,
           args.crossfade, args.output)


if __name__ == "__main__":
    main()
