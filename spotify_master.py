#!/usr/bin/env python3
"""
spotify_master.py — Master a WAV file for Spotify upload.

Processing chain:
  1.  Load & validate input
  2.  Resample to 44.1 kHz
  3.  EQ compensation       — high-shelf boost, low-mid mud cut
  4.  Air restoration       — synthesise noise floor above 16 kHz (Suno fix)
  5.  Spectral dehaze       — break up diffusion-model 8–16 kHz flatness
  6.  Mid-side processing   — bass anchoring + presence widening
  7.  De-essing             — adaptive mid-channel sibilance control
  8.  Harmonic saturation   — parallel tanh warmth
  9.  Glue compression      — mid-channel RMS compression
  10. Dynamic EQ            — threshold-driven presence cut (2–4 kHz)
  11. Transient shaping     — restore Suno-flattened attack transients
  12. Vocal ride            — restore vocals buried later in the track
  13. Macro-dynamic contrast — section-aware loudness shaping
  14. Stereo safety check
  15. Loudness normalisation — −14 LUFS (Spotify target)
  16. True-peak limiting    — −1 dBTP ceiling
  17. Export 44.1 kHz / 16-bit WAV

Usage:
    python spotify_master.py input.wav [output.wav]

Dependencies:
    pip install pyloudnorm soundfile scipy numpy matchering
"""

import sys
import argparse
import numpy as np
import soundfile as sf
import pyloudnorm as pyln
from scipy import signal
from scipy.ndimage import gaussian_filter1d
from pathlib import Path

# New processing stages
from mastering_extras import (
    air_restore, spectral_dehaze, multiband_compress,
    dynamic_eq, transient_shape, de_ess
)
from vocalride import vocal_ride


# ── Constants ─────────────────────────────────────────────────────────────────
TARGET_LUFS      = -14.0
TRUE_PEAK_DBTP   =  -1.0
TARGET_SR        = 44_100
TARGET_BITS      = 16

# EQ
HIGH_SHELF_FREQ  = 10_000
HIGH_SHELF_GAIN  =   1.5
LOW_MID_FREQ     =    380
LOW_MID_GAIN     =  -2.0
LOW_MID_Q        =   0.9

# Compressor
COMP_THRESHOLD   = -18.0
COMP_RATIO       =   2.0

# M/S processing
MS_BASS_FREQ     =   120   # Hz — anchor bass to mid below this
MS_BASS_SIDE_MIX =  0.15   # how much sub-bass stays in side (0=mono, 1=unchanged)
MS_PRESENCE_LOW  =  2000   # Hz — presence band start
MS_PRESENCE_HIGH =  8000   # Hz — presence band end
MS_PRESENCE_GAIN =  0.25   # linear gain added to side presence band (~+1.5 dB)

# Saturation
SAT_DRIVE_DB     =   6.0   # dB into the tanh saturator
SAT_MIX          =  0.15   # 15% wet — subtle warmth, not distortion

# Macro dynamics
MACRO_TARGET_DB  =   3.5   # target section contrast in dB
MACRO_MAX_GAIN   =   3.0   # cap gain correction at ±3 dB


# ── Helpers ───────────────────────────────────────────────────────────────────

def db_to_linear(db):  return 10.0 ** (db / 20.0)
def linear_to_db(lin): return 20.0 * np.log10(max(lin, 1e-12))
def lufs_str(val):     return f"{val:+.2f} LUFS"


# ── Step 1 — Load ─────────────────────────────────────────────────────────────

def load_audio(path):
    print(f"  Loading  : {path}")
    audio, sr = sf.read(path, always_2d=True)
    print(f"           : {sr} Hz, {audio.shape[1]}ch, "
          f"{audio.shape[0]/sr:.2f}s, {audio.dtype}")
    return audio.astype(np.float64), sr


# ── Step 2 — Resample ─────────────────────────────────────────────────────────

def resample(audio, src_sr, dst_sr):
    if src_sr == dst_sr:
        return audio
    print(f"  Resample : {src_sr} Hz → {dst_sr} Hz")
    return np.stack(
        [signal.resample_poly(audio[:, ch], dst_sr, src_sr,
                              window=('kaiser', 5.0))
         for ch in range(audio.shape[1])],
        axis=1
    )


# ── Step 3 — EQ ──────────────────────────────────────────────────────────────

def _high_shelf_coeffs(freq, gain_db, sr):
    A  = 10 ** (gain_db / 40.0)
    w0 = 2 * np.pi * freq / sr
    S  = 1.0
    alpha = (np.sin(w0) / 2) * np.sqrt((A + 1/A) * (1/S - 1) + 2)
    b0 =       A * ((A+1) + (A-1)*np.cos(w0) + 2*np.sqrt(A)*alpha)
    b1 = -2 * A * ((A-1) + (A+1)*np.cos(w0))
    b2 =       A * ((A+1) + (A-1)*np.cos(w0) - 2*np.sqrt(A)*alpha)
    a0 =             (A+1) - (A-1)*np.cos(w0) + 2*np.sqrt(A)*alpha
    a1 =   2 *      ((A-1) - (A+1)*np.cos(w0))
    a2 =             (A+1) - (A-1)*np.cos(w0) - 2*np.sqrt(A)*alpha
    return np.array([b0,b1,b2])/a0, np.array([1.0,a1/a0,a2/a0])


def _peaking_coeffs(freq, gain_db, Q, sr):
    A  = 10 ** (gain_db / 40.0)
    w0 = 2 * np.pi * freq / sr
    alpha = np.sin(w0) / (2 * Q)
    b0 =  1 + alpha * A;  b1 = -2*np.cos(w0);  b2 = 1 - alpha * A
    a0 =  1 + alpha / A;  a1 = -2*np.cos(w0);  a2 = 1 - alpha / A
    return np.array([b0,b1,b2])/a0, np.array([1.0,a1/a0,a2/a0])


def apply_eq(audio, sr, shelf_db=HIGH_SHELF_GAIN, mud_db=LOW_MID_GAIN):
    print(f"  EQ       : +{shelf_db} dB shelf @ {HIGH_SHELF_FREQ} Hz, "
          f"{mud_db} dB peak @ {LOW_MID_FREQ} Hz")
    b, a = _high_shelf_coeffs(HIGH_SHELF_FREQ, shelf_db, sr)
    audio = signal.sosfilt(signal.tf2sos(b, a), audio, axis=0)
    b, a = _peaking_coeffs(LOW_MID_FREQ, mud_db, LOW_MID_Q, sr)
    audio = signal.sosfilt(signal.tf2sos(b, a), audio, axis=0)
    return audio


# ── Step 4 — Mid-Side Processing ──────────────────────────────────────────────

def apply_ms_processing(audio, sr, presence_gain=MS_PRESENCE_GAIN):
    """
    Bass tightening: sub-120 Hz content rolled off in the side channel.
    Presence widening: 2–8 kHz side channel boosted by presence_gain
    (linear scale: 0.0 = no boost, 0.25 = ~+1.9 dB, 0.5 = ~+3.5 dB).
    """
    if audio.shape[1] == 1:
        print("  M/S proc : mono source — skipping")
        return audio

    mid  = (audio[:, 0] + audio[:, 1]) * 0.5
    side = (audio[:, 0] - audio[:, 1]) * 0.5

    # Bass tightening — low-pass the side and reduce it
    sos_lp = signal.butter(4, MS_BASS_FREQ / (sr / 2),
                           btype='low', output='sos')
    side_bass = signal.sosfilt(sos_lp, side)
    side_tight = (side - side_bass) + side_bass * MS_BASS_SIDE_MIX

    # Presence widening — band-pass and blend back
    sos_bp = signal.butter(2,
                           [MS_PRESENCE_LOW  / (sr / 2),
                            MS_PRESENCE_HIGH / (sr / 2)],
                           btype='band', output='sos')
    side_presence = signal.sosfilt(sos_bp, side_tight)
    side_wide = side_tight + side_presence * presence_gain

    gain_db = 20 * np.log10(presence_gain + 1)
    print(f"  M/S proc : bass anchored (sub-{MS_BASS_FREQ}Hz side → "
          f"{MS_BASS_SIDE_MIX*100:.0f}%)  "
          f"presence +{gain_db:.1f} dB @ {MS_PRESENCE_LOW//1000}–"
          f"{MS_PRESENCE_HIGH//1000} kHz side")

    return np.stack([mid + side_wide, mid - side_wide], axis=1)


# ── Step 5 — Harmonic Saturation ─────────────────────────────────────────────

def apply_saturation(audio, drive_db=SAT_DRIVE_DB, mix=SAT_MIX):
    """
    Parallel tanh saturation.  The saturated signal is normalised so gain
    at unity input = unity output, then blended at low mix ratio.
    Adds 2nd and 3rd harmonics for warmth without audible distortion.
    """
    drive = db_to_linear(drive_db)
    norm  = np.tanh(drive)           # normalisation factor
    wet   = np.tanh(audio * drive) / norm
    result = audio * (1.0 - mix) + wet * mix

    dry_rms = np.sqrt(np.mean(audio ** 2)) + 1e-12
    thd_pct = np.sqrt(np.mean((wet - audio) ** 2)) / dry_rms * 100
    print(f"  Saturate : drive +{drive_db} dB  mix {mix*100:.0f}%  "
          f"harmonic content ~{thd_pct:.1f}%")
    return result


# ── Step 7 — Macro-Dynamic Contrast ──────────────────────────────────────────

def apply_macro_dynamics(audio, sr, target_db=MACRO_TARGET_DB):
    """
    Section-aware gain to increase dynamic contrast. All smoothing happens
    at frame level (tiny array) — no large-sigma gaussian_filter1d on
    millions of samples.
    """
    n   = len(audio)
    hop = int(0.5 * sr)
    win = int(2.0 * sr)

    # O(n) sliding window RMS via cumsum — no per-frame Python loop
    mono    = audio.mean(axis=1)
    cs      = np.concatenate([[0.0], np.cumsum(mono ** 2)])
    starts  = np.arange(0, n - win // 2, hop)
    ends    = np.minimum(starts + win, n)
    rms_db  = 20 * np.log10(
        np.sqrt((cs[ends] - cs[starts]) / (ends - starts) + 1e-24) + 1e-12
    )

    smooth   = gaussian_filter1d(rms_db, sigma=int(8.0 / 0.5))
    contrast = smooth.max() - smooth.min()

    if contrast < 0.5 or target_db <= 0:
        if target_db <= 0:
            print(f"  Macro dyn: Off (bypassed)")
        else:
            print(f"  Macro dyn: dynamically flat — skipping")
        return audio

    stretch = min(target_db / contrast, 1.8)
    if stretch <= 1.0:
        print(f"  Macro dyn: contrast {contrast:.1f} dB already at/above "
              f"target {target_db:.1f} dB — skipping")
        return audio
    mean    = smooth.mean()

    # Gain computed and smoothed at frame level — fast
    gain_frames = np.clip((smooth - mean) * (stretch - 1.0),
                          -MACRO_MAX_GAIN, MACRO_MAX_GAIN)
    gain_frames = gaussian_filter1d(gain_frames, sigma=int(8.0 / 0.5))

    # Linear interpolation from frames to samples — O(n) in C
    frame_centres = starts + win // 2
    gain_db       = np.interp(np.arange(n), frame_centres, gain_frames)

    new_contrast = min(contrast * stretch, MACRO_TARGET_DB)
    print(f"  Macro dyn: contrast {contrast:.1f} → {new_contrast:.1f} dB  "
          f"(stretch {stretch:.2f}×  max ±{np.abs(gain_db).max():.1f} dB)")

    return audio * (10.0 ** (gain_db / 20.0))[:, np.newaxis]


# ── Step 8 — Stereo safety ───────────────────────────────────────────────────

def check_stereo(audio):
    if audio.shape[1] == 1:
        print("  Stereo   : mono — skipping")
        return audio

    mid  = (audio[:, 0] + audio[:, 1]) * 0.5
    side = (audio[:, 0] - audio[:, 1]) * 0.5
    mid_rms  = np.sqrt(np.mean(mid  ** 2)) + 1e-12
    side_rms = np.sqrt(np.mean(side ** 2)) + 1e-12
    corr = np.clip(mid_rms / (mid_rms + side_rms), 0, 1)

    print(f"  Stereo   : M/S balance {corr*100:.0f}% mid — ", end="")
    if corr < 0.5:
        scale = 0.5 + corr * 0.5
        side *= scale
        audio = np.stack([mid + side, mid - side], axis=1)
        print(f"width reduced (sides scaled to {scale:.2f}×)")
    else:
        print("OK")
    return audio


# ── Step 9 — Loudness normalisation ──────────────────────────────────────────

def normalise_loudness(audio, sr):
    meter   = pyln.Meter(sr)
    lufs_in = meter.integrated_loudness(audio)
    print(f"  Loudness : input  {lufs_str(lufs_in)}")

    if np.isinf(lufs_in) or np.isnan(lufs_in):
        print("           : WARNING — silence? skipping gain")
        return audio, lufs_in, lufs_in

    gain_db  = TARGET_LUFS - lufs_in
    audio    = audio * db_to_linear(gain_db)
    lufs_out = meter.integrated_loudness(audio)
    print(f"           : output {lufs_str(lufs_out)}  (gain {gain_db:+.2f} dB)")
    return audio, lufs_in, lufs_out


# ── Step 10 — True-peak limiting ─────────────────────────────────────────────

def true_peak_limit(audio, sr):
    """
    True-peak detection via chunked 4× oversampling.
    Processes in 1-second chunks to avoid allocating a massive upsampled buffer,
    then applies a single scalar gain reduction if needed — no second upsample pass.
    """
    OVERSAMPLE  = 4
    ceiling_lin = db_to_linear(TRUE_PEAK_DBTP)

    # Find true peak by upsampling chunks and tracking the max
    chunk_size = sr  # 1 second at a time
    n          = len(audio)
    peak       = 0.0

    for lo in range(0, n, chunk_size):
        hi    = min(lo + chunk_size, n)
        chunk = audio[lo:hi]
        up    = signal.resample_poly(chunk, OVERSAMPLE, 1, axis=0)
        peak  = max(peak, np.max(np.abs(up)))

    peak_dbtp = linear_to_db(peak)
    print(f"  True peak: {peak_dbtp:+.2f} dBTP → ceiling {TRUE_PEAK_DBTP} dBTP")

    if peak > ceiling_lin:
        # Simple scalar reduction — no need to re-upsample the whole track
        reduction = ceiling_lin / peak
        audio     = audio * reduction
        print(f"           : reduced {linear_to_db(reduction):+.2f} dB  "
              f"(peak now ~{TRUE_PEAK_DBTP:.1f} dBTP)")
    else:
        print("           : within ceiling — no limiting needed")

    return np.clip(audio, -1.0, 1.0)


# ── Step 11 — Export ──────────────────────────────────────────────────────────

def export(audio, sr, path):
    dither_amp = 1.0 / (2 ** 15)
    dither = (np.random.uniform(-1, 1, audio.shape)
              + np.random.uniform(-1, 1, audio.shape)) * dither_amp * 0.5
    sf.write(path, audio + dither, sr, subtype='PCM_16')
    size_kb = Path(path).stat().st_size / 1024
    print(f"  Export   : {path}  ({size_kb:.0f} KB, {sr} Hz / 16-bit WAV)")


# ── Main ──────────────────────────────────────────────────────────────────────

def master(input_path, output_path=None,
           # ── User-facing controls ───────────────────────────────────────
           presence_gain   = MS_PRESENCE_GAIN,
           deess_threshold = 2.0,
           vocal_boost_db  = 4.0,
           macro_target_db = MACRO_TARGET_DB,
           # ── Expert controls (locked by default) ───────────────────────
           eq_shelf_db     =  1.5,   # high shelf gain at 10 kHz
           eq_mud_db       = -2.0,   # peak cut at 380 Hz
           air_blend       =  0.018, # air restore blend (0 = off)
           dehaze_depth    =  0.04,  # spectral dehaze AM depth (0 = off)
           sat_drive_db    =  SAT_DRIVE_DB,
           sat_mix         =  SAT_MIX,
           comp_threshold  =  COMP_THRESHOLD,
           comp_ratio      =  COMP_RATIO,
           transient_boost =  2.5,   # dB boost on attack transients (0 = off)
           dyneq_threshold = -24.0,  # dynamic EQ threshold relative to band median
           dyneq_max_cut   =  3.0,   # max dB cut from dynamic EQ
           ):
    if output_path is None:
        p = Path(input_path)
        output_path = str(p.parent / (p.stem + "_remaster.wav"))

    print("\n╔══════════════════════════════════════════════════════╗")
    print("║         Spotify Mastering Chain                      ║")
    print("╚══════════════════════════════════════════════════════╝")
    print(f"\n► Input  : {input_path}")
    print(f"► Output : {output_path}\n")

    audio, sr = load_audio(input_path)
    audio = resample(audio, sr, TARGET_SR);  sr = TARGET_SR
    audio = apply_eq(audio, sr, shelf_db=eq_shelf_db, mud_db=eq_mud_db)
    audio = air_restore(audio, sr, blend=air_blend)
    audio = spectral_dehaze(audio, sr, depth=dehaze_depth)
    audio = apply_ms_processing(audio, sr, presence_gain)
    audio = de_ess(audio, sr, threshold_db=deess_threshold)
    audio = apply_saturation(audio, drive_db=sat_drive_db, mix=sat_mix)
    audio = multiband_compress(audio, sr,
                               threshold_db=comp_threshold, ratio=comp_ratio)
    audio = dynamic_eq(audio, sr,
                       threshold_db=dyneq_threshold, max_cut_db=dyneq_max_cut)
    audio = transient_shape(audio, sr, attack_boost_db=transient_boost)
    audio = vocal_ride(audio, sr, max_boost_db=vocal_boost_db)
    audio = apply_macro_dynamics(audio, sr, target_db=macro_target_db)
    audio = check_stereo(audio)
    audio, lufs_in, lufs_out = normalise_loudness(audio, sr)
    audio = true_peak_limit(audio, sr)
    export(audio, sr, output_path)

    print("\n✓ Done")
    print(f"  Input LUFS  : {lufs_str(lufs_in)}")
    print(f"  Output LUFS : {lufs_str(lufs_out)}")
    print(f"  Target      : {TARGET_LUFS} LUFS  /  {TRUE_PEAK_DBTP} dBTP  "
          f"/  {TARGET_SR} Hz  /  16-bit\n")
    return output_path


def main():
    p = argparse.ArgumentParser(description="Master a WAV file for Spotify upload.")
    p.add_argument("input",  help="Input WAV file")
    p.add_argument("output", nargs="?", help="Output WAV file (optional)")
    args = p.parse_args()
    master(args.input, args.output)


if __name__ == "__main__":
    main()
