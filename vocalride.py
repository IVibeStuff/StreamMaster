#!/usr/bin/env python3
"""
vocalride.py — Vocal presence automation for AI-generated music.

Suno buries the vocal in the second half of songs via two mechanisms:
  1. Gradual vocal level reduction (mix automation)
  2. Sub-bass / instrumental level increase that masks the vocal

This module detects and corrects both via:

  A. VOCAL ISOLATION — extract vocal-dominant content from the mid channel
     using a 4th-order bandpass centred on the track's vocal spectral centroid,
     adaptively estimated from the first 60 seconds.

  B. VOCAL ENVELOPE TRACKING — measure vocal RMS in 1s windows, smoothed
     with a 10s Gaussian to get the macro-level trend without reacting to
     breath gaps or phrasing.

  C. REFERENCE LEVEL ESTIMATION — use the median vocal level from the
     first 40% of the track as the target level throughout. This is what
     the vocal *should* sound like everywhere.

  D. VOCAL PRESENCE GAIN — compute per-sample gain needed to bring the
     vocal envelope up to the reference level, capped at MAX_BOOST_DB.
     Apply only to the mid channel in M/S space to avoid widening the
     instrumental content.

  E. INSTRUMENTAL MASKING DETECTION — detect sections where the sub-bass
     or full mix is rising while the vocal is dropping (Suno's mix
     automation). Apply frequency-selective attenuation to the masking
     frequencies (sub-bass heavy sections) to increase the vocal's
     perceptual clarity without boosting it further.

  F. SAFETY LIMITING — prevent over-boosting during genuine silence or
     instrumental-only passages by gating the vocal ride when the
     vocal band is more than GATE_DB below the reference.
"""

import numpy as np
import soundfile as sf
from scipy import signal
from scipy.ndimage import gaussian_filter1d
from pathlib import Path


# ── Constants ─────────────────────────────────────────────────────────────────
MAX_BOOST_DB     =  6.0    # maximum vocal gain boost (dB)
GATE_DB          = 15.0    # gate: don't boost if vocal is this far below ref
REFERENCE_PCT    =  0.40   # use first 40% of track to estimate reference level
SMOOTH_S         = 10.0    # Gaussian smoothing window for envelope (seconds)
RIDE_ATTACK_S    =  2.0    # gain ramp attack time (seconds)
RIDE_RELEASE_S   =  4.0    # gain ramp release time (seconds)
SUB_MASK_THRESH  =  3.0    # dB: how much sub-bass must exceed vocal-era level
                            # before masking attenuation is applied
SUB_MASK_MAX_DB  =  2.0    # max sub-bass attenuation (subtle, not surgical)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _rmsdb(x): return 20.0 * np.log10(np.sqrt(np.mean(x**2)) + 1e-12)

def _hop_env_db(sig, hop, sr):
    """Fast hop-based RMS envelope in dB."""
    n      = len(sig)
    n_hops = (n + hop - 1) // hop
    padded = np.pad(sig**2, (0, n_hops*hop - n))
    rms    = np.sqrt(np.mean(padded.reshape(n_hops, hop), axis=1) + 1e-24)
    return 20.0 * np.log10(rms + 1e-12)

def _butter(lo, hi, sr, order=4):
    lo = max(lo, 10); hi = min(hi, sr//2 - 100)
    return signal.butter(order, [lo/(sr/2), hi/(sr/2)], btype='bandpass', output='sos')

def _apply(sos, sig):
    return signal.sosfilt(sos, sig)

def _smooth_db_to_gain(db_curve, sr, hop):
    """Convert a dB gain curve at hop resolution to linear sample-resolution."""
    n_hops = len(db_curve)
    n      = n_hops * hop
    lin    = 10.0 ** (db_curve / 20.0)
    # Smooth with ballistics at hop level — much faster than sample-level
    a_att = np.exp(-1.0 / max(1, RIDE_ATTACK_S   * sr / hop))
    a_rel = np.exp(-1.0 / max(1, RIDE_RELEASE_S  * sr / hop))
    smoothed = np.zeros(n_hops)
    s = lin[0]
    for i in range(n_hops):
        coef = a_att if lin[i] > s else a_rel
        s    = coef * s + (1 - coef) * lin[i]
        smoothed[i] = s
    return smoothed


# ── Core vocal centroid estimation ────────────────────────────────────────────

def _estimate_vocal_band(audio, sr):
    """
    Estimate the vocal's dominant frequency range from the first 60s.
    Returns (lo_hz, hi_hz, centroid_hz).

    Uses spectral centroid of the mid channel in the 200–4000 Hz range.
    Widens the band by ±1 octave around the centroid, clamped to 200–4000 Hz.
    """
    mid    = (audio[:,0] + audio[:,1]) * 0.5
    ref_s  = min(int(60 * sr), len(mid))
    seg    = mid[:ref_s]

    # Welch PSD in the vocal range
    f, psd = signal.welch(seg, sr, nperseg=min(len(seg), 4096))
    mask   = (f >= 200) & (f < 4000)
    if not mask.any():
        return 300, 3000, 1000

    centroid = float(np.sum(f[mask] * psd[mask]) / (np.sum(psd[mask]) + 1e-12))
    centroid = np.clip(centroid, 300, 2500)

    # Band: centroid ÷2 to centroid ×2.5, clamped
    lo = max(200,  centroid * 0.5)
    hi = min(4000, centroid * 2.5)
    return float(lo), float(hi), float(centroid)


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN FUNCTION
# ══════════════════════════════════════════════════════════════════════════════

def vocal_ride(
    audio:          np.ndarray,
    sr:             int,
    max_boost_db:   float = MAX_BOOST_DB,
    gate_db:        float = GATE_DB,
    sub_mask:       bool  = True,
) -> np.ndarray:
    """
    Apply vocal presence automation to restore buried vocals.

    Parameters
    ----------
    audio        : stereo float64 array (n_samples, 2)
    sr           : sample rate
    max_boost_db : maximum gain applied to the vocal mid channel (default 6 dB)
    gate_db      : don't boost if vocal is more than this below ref (default 15 dB)
    sub_mask     : also attenuate masking sub-bass when it rises (default True)

    Returns
    -------
    Processed audio array (same shape as input)
    """
    if audio.shape[1] == 1:
        print("  Vocal ride : mono — skipping M/S processing")
        return audio

    if max_boost_db <= 0:
        print("  Vocal ride : Off (bypassed)")
        return audio

    n   = len(audio)
    mid = (audio[:,0] + audio[:,1]) * 0.5
    side= (audio[:,0] - audio[:,1]) * 0.5

    # ── A. Estimate vocal band ────────────────────────────────────────────────
    vox_lo, vox_hi, centroid = _estimate_vocal_band(audio, sr)
    print(f"  Vocal ride : vocal band {vox_lo:.0f}–{vox_hi:.0f} Hz  "
          f"centroid {centroid:.0f} Hz")

    sos_vox = _butter(vox_lo, vox_hi, sr, order=4)
    vox_mid = _apply(sos_vox, mid)

    # ── B. Vocal envelope (1s hops) ───────────────────────────────────────────
    hop    = int(1.0 * sr)
    n_hops = (n + hop - 1) // hop
    vox_db = _hop_env_db(vox_mid, hop, sr)

    # Smooth envelope — removes breath gaps, keeps macro trend
    smooth_sigma = int(SMOOTH_S)   # sigma in hop units (1s hops → sigma in seconds)
    vox_smooth   = gaussian_filter1d(vox_db, sigma=smooth_sigma)

    # ── C. Reference level — median of first 40% ──────────────────────────────
    ref_hops = max(1, int(n_hops * REFERENCE_PCT))
    ref_db   = float(np.median(vox_smooth[:ref_hops]))
    print(f"             reference level {ref_db:.1f} dBRMS  "
          f"(median of first {REFERENCE_PCT*100:.0f}%)")

    # ── D. Gain curve ─────────────────────────────────────────────────────────
    # How much do we need to add at each hop to reach ref_db?
    raw_gain_db = ref_db - vox_smooth   # positive = boost needed

    # Gate: if vocal is more than gate_db below ref, it's probably a
    # genuine instrumental section — don't boost (would lift noise / reverb)
    gate_mask      = vox_smooth < (ref_db - gate_db)
    raw_gain_db[gate_mask] = 0.0

    # Cap boost
    raw_gain_db = np.clip(raw_gain_db, 0.0, max_boost_db)

    # Only apply to second half of track (don't alter the reference section)
    first_half_hops = ref_hops
    raw_gain_db[:first_half_hops] *= np.linspace(0, 1, first_half_hops)

    # Apply ballistic smoothing at hop level
    gain_lin_hops = _smooth_db_to_gain(raw_gain_db, sr, hop)

    # Interpolate to sample resolution
    hop_centres = np.arange(n_hops) * hop + hop // 2
    gain_lin    = np.interp(np.arange(n), hop_centres, gain_lin_hops)

    # Stats
    active = raw_gain_db > 0.1
    avg_boost = raw_gain_db[active].mean() if active.any() else 0.0
    max_boost = raw_gain_db.max()
    print(f"             boosting {active.mean()*100:.0f}% of track  "
          f"avg +{avg_boost:.1f} dB  max +{max_boost:.1f} dB  "
          f"gated {gate_mask.mean()*100:.0f}%")

    # ── E. Sub-bass masking attenuation ───────────────────────────────────────
    sub_gain_lin = np.ones(n)
    if sub_mask:
        sos_sub  = _butter(40, 200, sr, order=2)
        sub_mid  = _apply(sos_sub, mid)
        sub_db   = _hop_env_db(sub_mid, hop, sr)
        sub_smooth = gaussian_filter1d(sub_db, sigma=smooth_sigma)

        # Reference sub level from first 40%
        sub_ref_db = float(np.median(sub_smooth[:ref_hops]))
        sub_excess = sub_smooth - sub_ref_db - SUB_MASK_THRESH
        sub_excess = np.clip(sub_excess, 0.0, SUB_MASK_MAX_DB)

        # Only attenuate when sub is rising AND vocal needs boosting
        sub_excess[~active] = 0.0
        sub_gain_hops = 10.0 ** (-sub_excess / 20.0)
        sub_gain_lin  = np.interp(np.arange(n), hop_centres, sub_gain_hops)

        if sub_excess.max() > 0.01:
            print(f"             sub-bass masking: attenuating up to "
                  f"{sub_excess.max():.1f} dB in {(sub_excess>0.01).mean()*100:.0f}% of track")

    # ── F. Apply to mid channel only ──────────────────────────────────────────
    # Ride the vocal by boosting mid, simultaneously attenuate sub masking
    sos_sub_full = _butter(40, 200, sr, order=2)
    sub_full     = _apply(sos_sub_full, mid)
    mid_rest     = mid - sub_full

    mid_out = (mid_rest * gain_lin + sub_full * gain_lin * sub_gain_lin)

    # Re-encode L/R
    result = np.stack([mid_out + side, mid_out - side], axis=1)
    return np.clip(result, -1.0, 1.0)


# ── Convenience wrapper ───────────────────────────────────────────────────────

def process(input_path: str, output_path: str | None = None,
            max_boost_db: float = MAX_BOOST_DB,
            gate_db: float = GATE_DB,
            sub_mask: bool = True) -> str:

    if output_path is None:
        p = Path(input_path)
        output_path = str(p.parent / (p.stem + "_vocalrode.wav"))

    print("\n╔══════════════════════════════════════════════════════╗")
    print("║              Vocal Ride                              ║")
    print("╚══════════════════════════════════════════════════════╝")

    audio, sr = sf.read(input_path, always_2d=True)
    audio = audio.astype(np.float64)
    print(f"  Track    : {Path(input_path).name}  "
          f"({sr}Hz  {audio.shape[0]/sr:.1f}s)")

    result = vocal_ride(audio, sr, max_boost_db, gate_db, sub_mask)

    dither_amp = 1.0 / (2**15)
    dither = (np.random.uniform(-1,1,result.shape) +
              np.random.uniform(-1,1,result.shape)) * dither_amp * 0.5
    sf.write(output_path, result + dither, sr, subtype='PCM_16')
    print(f"  Export   : {output_path}  "
          f"({Path(output_path).stat().st_size//1024} KB)")
    print("\n✓ Vocal ride done\n")
    return output_path


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: python vocalride.py input.wav [output.wav] [max_boost_db]")
        sys.exit(1)
    inp  = sys.argv[1]
    outp = sys.argv[2] if len(sys.argv) > 2 else None
    mb   = float(sys.argv[3]) if len(sys.argv) > 3 else MAX_BOOST_DB
    process(inp, outp, max_boost_db=mb)
