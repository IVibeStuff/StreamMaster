#!/usr/bin/env python3
"""
heal.py — Heal a pre-baked splice in a single WAV file.

Given one continuous file where a section has already been replaced (e.g. from
Suno), smooths both join points with:

  1. Zero-crossing snap  — eliminate clicks at the cut edges
  2. Level match         — nudge the inserted section's gain to match context
  3. Equal-power crossfade at each seam (same algorithm as splice.py)
  4. Spectral blend      — FFT tonal morph across the blend window

Usage (CLI):
    python heal.py track.wav --in 32.5 --out 48.0 [--blend 120] [--output out.wav]
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


def rms_db(chunk: np.ndarray) -> float:
    rms = np.sqrt(np.mean(chunk ** 2))
    return 20.0 * np.log10(max(rms, 1e-12))


def nearest_zero_crossing(audio: np.ndarray, sample: int,
                           search_ms: float, sr: int) -> int:
    radius = int(search_ms * 1e-3 * sr)
    mono   = audio.mean(axis=1)
    n      = len(mono)
    lo     = max(0, sample - radius)
    hi     = min(n - 1, sample + radius)
    crossings = [i for i in range(lo, hi) if mono[i] * mono[i + 1] <= 0]
    if not crossings:
        return sample
    return min(crossings, key=lambda c: abs(c - sample))


def equal_power_fade(length: int) -> tuple[np.ndarray, np.ndarray]:
    t = np.linspace(0.0, np.pi / 2, length)
    return np.cos(t), np.sin(t)   # fade_out, fade_in


# ── Spectral blend ────────────────────────────────────────────────────────────

def spectral_blend(audio: np.ndarray, seam: int, blend_samples: int,
                   side: str) -> np.ndarray:
    """
    Softens tonal discontinuity at a seam by gently nudging the spectrum
    inside the blend window toward the character of the audio outside it.

    side='in'  — seam is where inserted section BEGINS (blend extends right)
    side='out' — seam is where inserted section ENDS   (blend extends left)
    """
    n      = len(audio)
    ch     = audio.shape[1]
    result = audio.copy()

    HOP = 256
    WIN = 1024

    if side == 'in':
        # Reference = audio just before the seam (original track)
        ref_start = max(0, seam - blend_samples)
        ref_end   = seam
        # Analysis zone = just after the seam (inserted section start)
        ana_start = seam
        ana_end   = min(n, seam + blend_samples)
        def alpha(fi, total): return fi / max(total - 1, 1)   # 0→1 inside→outside blend
    else:
        # Reference = audio just after the seam (original track resumes)
        ref_start = min(n, seam)
        ref_end   = min(n, seam + blend_samples)
        # Analysis zone = just before the seam (inserted section end)
        ana_start = max(0, seam - blend_samples)
        ana_end   = seam
        def alpha(fi, total): return 1.0 - fi / max(total - 1, 1)

    ref_len = ref_end  - ref_start
    ana_len = ana_end  - ana_start
    if ref_len < WIN or ana_len < WIN:
        return result

    window = np.hanning(WIN)

    def avg_spectrum(chunk):
        mono   = chunk.mean(axis=1)
        frames = [np.abs(np.fft.rfft(mono[i:i+WIN] * window))
                  for i in range(0, len(mono) - WIN, HOP)]
        return np.mean(frames, axis=0) + 1e-12 if frames else None

    ref_spec = avg_spectrum(audio[ref_start:ref_end])
    ana_spec = avg_spectrum(audio[ana_start:ana_end])
    if ref_spec is None or ana_spec is None:
        return result

    total_frames = max((ana_end - ana_start - WIN) // HOP, 1)

    for fi, pos in enumerate(range(ana_start, ana_end - WIN, HOP)):
        a = alpha(fi, total_frames)
        for c in range(ch):
            frame     = audio[pos:pos+WIN, c] * window
            F         = np.fft.rfft(frame)
            mag       = np.abs(F) + 1e-12
            target    = (1 - a) * ref_spec + a * ana_spec
            corr      = target / mag
            corr      = 1.0 + (corr - 1.0) * 0.35   # dampen to avoid over-EQ
            frame_out = np.fft.irfft(F * corr) * window
            result[pos:pos+WIN, c] += frame_out - audio[pos:pos+WIN, c] * (window ** 2)

    return result


# ── Core heal ─────────────────────────────────────────────────────────────────

def heal(
    input_path:  str,
    in_time:     float,
    out_time:    float,
    blend_ms:    float = 120.0,
    output_path: str | None = None,
) -> str:

    if output_path is None:
        p = Path(input_path)
        output_path = str(p.parent / (p.stem + "_healed.wav"))

    print("\n╔══════════════════════════════════════════════════════╗")
    print("║              Seam Healer                             ║")
    print("╚══════════════════════════════════════════════════════╝")

    audio, sr = load(input_path)
    n = len(audio)
    print(f"  Track    : {input_path}  ({sr} Hz, {audio.shape[1]}ch, {n/sr:.2f}s)")

    blend_samples = int(blend_ms * 1e-3 * sr)

    in_raw  = int(in_time  * sr)
    out_raw = int(out_time * sr)

    if not (0 <= in_raw < out_raw <= n):
        raise ValueError(f"in/out times out of range for track ({n/sr:.2f}s)")

    # ── Zero-crossing snap ────────────────────────────────────────────────────
    in_sample  = nearest_zero_crossing(audio, in_raw,  search_ms=20, sr=sr)
    out_sample = nearest_zero_crossing(audio, out_raw, search_ms=20, sr=sr)
    print(f"  In  seam : {in_time:.3f}s → snapped {(in_sample-in_raw)/sr*1000:+.1f}ms "
          f"@ {in_sample/sr:.3f}s")
    print(f"  Out seam : {out_time:.3f}s → snapped {(out_sample-out_raw)/sr*1000:+.1f}ms "
          f"@ {out_sample/sr:.3f}s")

    result = audio.copy()

    # ── Level match inserted section to surrounding context ───────────────────
    ctx_before = audio[max(0, in_sample - int(1.5*sr)) : in_sample]
    ctx_after  = audio[out_sample : min(n, out_sample + int(1.5*sr))]
    inserted   = audio[in_sample : out_sample]

    if len(ctx_before) > 0 and len(ctx_after) > 0 and len(inserted) > 0:
        ctx_rms  = rms_db(np.concatenate([ctx_before, ctx_after]))
        ins_rms  = rms_db(inserted)
        level_db = ctx_rms - ins_rms
        if abs(level_db) > 0.3:
            result[in_sample:out_sample] *= 10.0 ** (level_db / 20.0)
            print(f"  Level    : {ins_rms:.1f} dBRMS → context {ctx_rms:.1f} dBRMS "
                  f"({level_db:+.2f} dB)")
        else:
            print(f"  Level    : within 0.3 dB of context — no correction")

    # ── Equal-power crossfades centred on each seam ───────────────────────────
    # Each crossfade spans [seam - half : seam + half], so the blend happens
    # across the join rather than entirely on one side of it.
    half = min(blend_samples // 2,
               in_sample,
               (out_sample - in_sample) // 2,   # don't overlap the two seams
               n - out_sample)
    print(f"  Xfade    : {half*2/sr*1000:.0f}ms ({half} samples each side) centred on each seam")

    if half > 0:
        fo, fi = equal_power_fade(half * 2)
        fo = fo[:, np.newaxis]
        fi = fi[:, np.newaxis]

        # IN seam: original fades out, inserted fades in, centred on in_sample
        orig_in = audio [in_sample - half : in_sample + half]
        ins_in  = result[in_sample - half : in_sample + half]
        result  [in_sample - half : in_sample + half] = orig_in * fo + ins_in * fi

        # OUT seam: inserted fades out, original fades in, centred on out_sample
        ins_out  = result[out_sample - half : out_sample + half]
        orig_out = audio [out_sample - half : out_sample + half]
        result   [out_sample - half : out_sample + half] = ins_out * fo + orig_out * fi

    # ── Spectral blend at both seams ──────────────────────────────────────────
    spec_win = blend_samples
    print(f"  Spectral : tonal blend {spec_win/sr*1000:.0f}ms at IN seam…")
    result = spectral_blend(result, in_sample,  spec_win, side='in')
    print(f"  Spectral : tonal blend {spec_win/sr*1000:.0f}ms at OUT seam…")
    result = spectral_blend(result, out_sample, spec_win, side='out')

    # ── Export ────────────────────────────────────────────────────────────────
    result = np.clip(result, -1.0, 1.0)
    dither_amp = 1.0 / (2 ** 15)
    dither = (np.random.uniform(-1, 1, result.shape)
              + np.random.uniform(-1, 1, result.shape)) * dither_amp * 0.5
    sf.write(output_path, result + dither, sr, subtype='PCM_16')

    print(f"  Export   : {output_path}  ({Path(output_path).stat().st_size//1024} KB)")
    print("\n✓ Heal done\n")
    return output_path


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Heal a pre-baked splice in a single WAV.")
    p.add_argument("input")
    p.add_argument("--in",    dest="in_time",  type=float, required=True)
    p.add_argument("--out",   dest="out_time", type=float, required=True)
    p.add_argument("--blend", type=float, default=120.0)
    p.add_argument("--output", default=None)
    args = p.parse_args()
    heal(args.input, args.in_time, args.out_time, args.blend, args.output)


if __name__ == "__main__":
    main()
