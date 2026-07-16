#!/usr/bin/env python3
"""
mastering_extras.py — Additional mastering stages for spotify_master.py

Stages (in chain order):
  A. air_restore       — synthesise a musical noise floor above 16 kHz to
                         replace Suno's hard spectral cutoff
  B. spectral_dehaze   — break up the uniform 8-16 kHz energy distribution
                         produced by diffusion models
  C. multiband_compress — 3-band compressor (sub / mid / air) for
                          frequency-selective dynamic control
  D. dynamic_eq        — frequency-selective compression: only cuts
                         harshness (2-4 kHz) when it exceeds a threshold
  E. transient_shape   — detect and restore attack transients that Suno's
                         internal compression has flattened
  F. reference_match   — match RMS, frequency response, peak, and stereo
                         width to a reference track via Matchering
"""

import numpy as np
import soundfile as sf
from scipy import signal
from scipy.ndimage import gaussian_filter1d
from pathlib import Path


# ── Helpers ───────────────────────────────────────────────────────────────────

def _db(x):   return 20.0 * np.log10(max(float(np.max(np.abs(x))), 1e-12))
def _rms(x):  return float(np.sqrt(np.mean(x ** 2)))
def _rmsdb(x): return 20.0 * np.log10(max(_rms(x), 1e-12))

def _butter_sos(freq, sr, btype, order=4):
    wn = np.atleast_1d(np.asarray(freq, dtype=float)) / (sr / 2)
    if btype in ('low', 'high'):
        wn = float(wn[0])   # scalar for single-edge filters
    return signal.butter(order, wn, btype=btype, output='sos')

def _apply_sos(sos, audio):
    return signal.sosfilt(sos, audio, axis=0)


# ══════════════════════════════════════════════════════════════════════════════
#  A. AIR RESTORE
#  Suno generates at 32 kHz then upsamples → hard cutoff at 16 kHz.
#  We synthesise a shaped noise floor above 16 kHz that matches the
#  spectral slope just below the cutoff so the transition sounds natural.
# ══════════════════════════════════════════════════════════════════════════════

def air_restore(audio: np.ndarray, sr: int,
                blend: float = 0.018) -> np.ndarray:
    """
    Restore high-frequency air above Suno's 16 kHz cutoff.

    blend : noise mix level (0.018 ≈ −35 dBFS relative — inaudible as noise
            but audible as "air" on revealing headphones)
    """
    if sr < 32000:
        print("  Air restore: sample rate too low — skipping")
        return audio

    n   = len(audio)
    ch  = audio.shape[1]

    # 1. Measure the spectral slope in the 12–15.9 kHz band
    sos_ref = _butter_sos([12000, 15900], sr, btype='bandpass', order=2)
    ref_band = _apply_sos(sos_ref, audio)
    ref_rms  = _rms(ref_band)

    if ref_rms < 1e-6:
        print("  Air restore: reference band silent — skipping")
        return audio

    # 2. Generate correlated white noise per channel, shaped to roll off
    #    naturally from 16 kHz upward (mimics mic/room high-end rolloff)
    rng   = np.random.default_rng(seed=42)   # deterministic
    noise = rng.standard_normal((n, ch)).astype(np.float64)

    # High-pass above 15.5 kHz so we only add content in the "dead zone"
    sos_hp = _butter_sos(15500, sr, btype='high', order=4)
    noise  = _apply_sos(sos_hp, noise)

    # Shape with gentle downward slope (natural air rolloff −3 dB/oct above 16k)
    # Approximate with a one-pole low-shelf on the noise
    sos_slope = _butter_sos(18000, sr, btype='low', order=1)
    noise     = _apply_sos(sos_slope, noise)

    # 3. Scale noise to match the reference band level × blend
    noise_rms = _rms(noise) + 1e-12
    target_rms = ref_rms * blend
    noise *= target_rms / noise_rms

    result = audio + noise
    added_db = 20 * np.log10(target_rms + 1e-12)
    print(f"  Air restore: +noise floor above 16 kHz  "
          f"level {added_db:.1f} dBFS  blend={blend:.3f}")
    return result


# ══════════════════════════════════════════════════════════════════════════════
#  B. SPECTRAL DEHAZE
#  Diffusion models produce a "haze" in 8–16 kHz with unnaturally uniform
#  energy distribution. Break it up with subtle time-varying amplitude
#  modulation — gentle enough to be inaudible but enough to make the
#  energy distribution look and sound more natural.
# ══════════════════════════════════════════════════════════════════════════════

def spectral_dehaze(audio: np.ndarray, sr: int,
                    depth: float = 0.04) -> np.ndarray:
    """
    Break up diffusion-model spectral haze in 8–16 kHz.

    depth : modulation depth (0.04 = ±4% amplitude variation — inaudible
            as modulation, effective at breaking up flatness)
    """
    n  = len(audio)
    ch = audio.shape[1]

    # Isolate the haze band
    sos_bp = _butter_sos([8000, min(15900, sr // 2 - 100)],
                         sr, btype='bandpass', order=2)
    haze_band = _apply_sos(sos_bp, audio)
    rest      = audio - haze_band

    # Generate a very slow, organic amplitude modulation envelope
    # Use sum of incommensurable sinusoids so it never repeats
    t   = np.arange(n) / sr
    mod = (  np.sin(2 * np.pi * 0.31 * t)
           + np.sin(2 * np.pi * 0.57 * t) * 0.7
           + np.sin(2 * np.pi * 1.13 * t) * 0.4
           + np.sin(2 * np.pi * 2.71 * t) * 0.2 )
    # Normalise to [-1, 1], then scale to depth and offset to [1-depth, 1+depth]
    mod /= (np.max(np.abs(mod)) + 1e-12)
    mod  = 1.0 + mod * depth

    result = rest + haze_band * mod[:, np.newaxis]
    print(f"  Spectral dehaze: 8–16 kHz AM modulation  "
          f"depth ±{depth*100:.1f}%")
    return result


# ══════════════════════════════════════════════════════════════════════════════
#  C. MULTIBAND COMPRESSION
#  3-band compressor: sub (< 200 Hz), mid (200 Hz – 8 kHz), air (> 8 kHz).
#  Each band has its own threshold, ratio, and makeup.  Bands are split with
#  Linkwitz-Riley crossovers (2× Butterworth in series) for phase accuracy.
# ══════════════════════════════════════════════════════════════════════════════

def _lr_crossover(audio, freq, sr, order=2):
    """Linkwitz-Riley crossover: returns (low, high) that sum to unity."""
    sos = signal.butter(order, freq / (sr / 2), btype='low', output='sos')
    low  = signal.sosfilt(sos, audio, axis=0)
    high = audio - low
    return low, high


def _compress_band(audio, sr, threshold_db, ratio, attack_ms, release_ms,
                   makeup_db, hop=None):
    """Fast vectorised compressor — accepts pre-computed hop size."""
    thresh = 10 ** (threshold_db / 20)
    makeup = 10 ** (makeup_db   / 20)
    n      = len(audio)
    if hop is None:
        hop = max(1, int(0.005 * sr))
    n_hops = (n + hop - 1) // hop
    mono_sq = audio.mean(axis=1) ** 2
    padded  = np.pad(mono_sq, (0, n_hops * hop - n))
    rms_env = np.sqrt(np.mean(padded.reshape(n_hops, hop), axis=1) + 1e-24)

    a_att = np.exp(-1.0 / max(1, attack_ms  * 1e-3 * sr / hop))
    a_rel = np.exp(-1.0 / max(1, release_ms * 1e-3 * sr / hop))
    env   = np.maximum(signal.lfilter([1-a_att],[1,-a_att], rms_env),
                       signal.lfilter([1-a_rel],[1,-a_rel], rms_env))

    gain_hops = np.where(env > thresh,
        thresh * (env / (thresh + 1e-24)) ** (1 / ratio) / (env + 1e-24) * makeup,
        makeup)
    gain_hops = gaussian_filter1d(gain_hops, sigma=3)
    gain = np.interp(np.arange(n),
                     np.arange(n_hops) * hop + hop // 2,
                     gain_hops)
    return audio * gain[:, np.newaxis]


def multiband_compress(audio: np.ndarray, sr: int,
                       threshold_db: float = -18.0,
                       ratio: float = 2.0) -> np.ndarray:
    """
    Gentle glue compression applied to the mid channel only.

    Applying compression to L and R independently causes slight
    decorrelation when L and R have different content, which
    audibly affects vocal character. Processing only the mid channel
    (L+R)/2 and leaving the side channel untouched avoids this entirely.

    Threshold: -18 dBRMS  Ratio: 2:1  Attack: 20ms  Release: 150ms
    """
    if audio.shape[1] == 1:
        return _compress_band(audio, sr, threshold_db, ratio, 20.0, 150.0, 1.0)

    mid  = (audio[:,0] + audio[:,1]) * 0.5
    side = (audio[:,0] - audio[:,1]) * 0.5
    mid_2d   = mid[:,np.newaxis]
    mid_comp = _compress_band(mid_2d, sr, threshold_db, ratio, 20.0, 150.0, 1.0)[:,0]
    result = np.stack([mid_comp + side, mid_comp - side], axis=1)
    gr = _rmsdb(mid_comp) - _rmsdb(mid)
    print(f"  Compress   : mid-channel  {ratio:.1f}:1  {threshold_db}dBRMS  {gr:+.1f} dB gain change")
    return result


# ══════════════════════════════════════════════════════════════════════════════
#  D2. DE-ESSER  (M/S mid-only architecture)
#
#  Suno vocal sibilance is almost entirely in the mid channel (typically
#  30+ dB stronger in mid than side). The previous wideband de-esser
#  detected on the full stereo mix and applied gain to both channels,
#  which diluted the detection and unnecessarily touched the side channel.
#
#  This version:
#    1. Decodes the signal to M/S
#    2. Detects sibilance ONLY in the mid channel 5–10 kHz band
#    3. Applies gain reduction ONLY to the mid channel
#    4. Re-encodes to L/R — side channel (stereo width) is untouched
#
#  The threshold adapts per-track using the 90th percentile of the mid
#  band level, so it self-calibrates regardless of overall track loudness.
# ══════════════════════════════════════════════════════════════════════════════

def de_ess(audio: np.ndarray, sr: int,
           freq_lo: float = 5000,
           freq_hi: float = 10000,
           threshold_db: float = 4.0,
           ratio: float = 8.0,
           max_cut_db: float = 12.0,
           attack_ms: float = 1.0,
           release_ms: float = 60.0,
           mode: str = 'auto') -> np.ndarray:
    """
    Band-split de-esser.

    Isolates the sibilance band (default 5–10 kHz), compresses only that
    extracted band, then re-mixes it with the remainder of the signal.
    Everything outside the sibilance band is completely untouched — vowels,
    body, consonants below 5 kHz all pass through unmodified.

    threshold_db: offset above p90 of the sibilance band.
      LOWER = more aggressive (0 = catches anything above typical level).
      UI slider maps 0→8 (Very gentle) to 7→1 (Max), inverted in server.

    threshold_db <= -1.5 = complete bypass.
    """
    if threshold_db <= -1.5:
        print(f"  De-esser   : Off (bypassed)")
        return audio

    freq_hi = min(freq_hi, sr / 2 - 200)
    n = len(audio)

    # ── Auto-detect mode ─────────────────────────────────────────────────────
    if mode == 'auto':
        sos_det = _butter_sos([freq_lo, freq_hi], sr, btype='bandpass', order=2)
        L_sib = _apply_sos(sos_det, audio[:, 0:1])[:,0]
        R_sib = _apply_sos(sos_det, audio[:, 1:2])[:,0]
        hop_a = max(1, int(0.05 * sr))
        n_h   = (n + hop_a - 1) // hop_a
        env_L = np.sqrt(np.mean(
            np.pad(L_sib**2,(0,n_h*hop_a-n)).reshape(n_h,hop_a),axis=1)+1e-24)
        active = env_L > np.percentile(env_L, 90)
        if active.any():
            l_sq = np.pad(L_sib**2,(0,n_h*hop_a-n)).reshape(n_h,hop_a).mean(axis=1)
            r_sq = np.pad(R_sib**2,(0,n_h*hop_a-n)).reshape(n_h,hop_a).mean(axis=1)
            l_rms = np.sqrt(np.mean(l_sq[active])+1e-24)
            r_rms = np.sqrt(np.mean(r_sq[active])+1e-24)
            lr_diff = abs(20*np.log10(l_rms+1e-12) - 20*np.log10(r_rms+1e-12))
        else:
            lr_diff = 0.0
        mode = 'mid' if lr_diff <= 2.0 else 'wideband'
        print(f"  De-esser   : auto→{mode} (L/R sibilance imbalance {lr_diff:.1f} dB)")

    # ── Band split ───────────────────────────────────────────────────────────
    # Use 4th-order Butterworth — steep enough to isolate sibilance cleanly
    # while remaining linear-phase enough not to smear transients
    sos_bp = _butter_sos([freq_lo, freq_hi], sr, btype='bandpass', order=4)
    sos_lo = _butter_sos(freq_lo,             sr, btype='low',      order=4)
    sos_hi = _butter_sos(freq_hi,             sr, btype='high',     order=4)

    # Split into three bands: below, sibilance, above
    sib  = _apply_sos(sos_bp, audio)   # 5–10 kHz — this is what we compress
    low  = _apply_sos(sos_lo, audio)   # <5 kHz — completely untouched
    high = _apply_sos(sos_hi, audio)   # >10 kHz — completely untouched

    # ── Detection on sibilance band ──────────────────────────────────────────
    if mode == 'mid':
        det_sig = (sib[:,0] + sib[:,1]) * 0.5
    else:
        det_sig = sib.mean(axis=1)

    hop    = max(1, int(attack_ms * 1e-3 * sr))
    n_hops = (n + hop - 1) // hop
    padded = np.pad(det_sig**2, (0, n_hops*hop - n))
    env    = np.sqrt(np.mean(padded.reshape(n_hops, hop), axis=1) + 1e-24)

    p90_db        = 20 * np.log10(np.percentile(env, 90) + 1e-12)
    abs_thresh_db = p90_db + threshold_db
    thresh        = 10 ** (abs_thresh_db / 20)
    max_cut       = 10 ** (-max_cut_db   / 20)

    a_att = np.exp(-1.0 / max(1, attack_ms  * 1e-3 * sr / hop))
    a_rel = np.exp(-1.0 / max(1, release_ms * 1e-3 * sr / hop))
    e_smooth = signal.lfilter([1-a_att],[1,-a_att], env)
    e_rel    = signal.lfilter([1-a_rel],[1,-a_rel], e_smooth)
    e        = np.maximum(e_smooth, e_rel)

    gain_hops = np.where(
        e > thresh,
        np.maximum(
            thresh * (e / (thresh + 1e-24)) ** (1.0 / ratio) / (e + 1e-24),
            max_cut
        ),
        1.0
    )
    gain_hops = gaussian_filter1d(gain_hops, sigma=2)
    gain = np.interp(np.arange(n), np.arange(n_hops)*hop + hop//2, gain_hops)

    active_pct = float((gain_hops < 0.99).mean() * 100)
    avg_cut_db = float(20*np.log10(gain_hops[gain_hops < 0.99].mean()+1e-12)) \
                 if (gain_hops < 0.99).any() else 0.0

    print(f"  De-esser   : {mode}  band-split {freq_lo//1000}–{freq_hi//1000} kHz  "
          f"thresh {abs_thresh_db:.1f} dBRMS  "
          f"active {active_pct:.1f}%  avg {avg_cut_db:.1f} dB")

    # ── Apply gain to sibilance band only, then recombine ────────────────────
    if mode == 'mid':
        # Compress only the mid component of the sibilance band
        sib_mid  = (sib[:,0] + sib[:,1]) * 0.5
        sib_side = (sib[:,0] - sib[:,1]) * 0.5
        sib_mid_compressed = sib_mid * gain
        sib_compressed = np.stack([
            sib_mid_compressed + sib_side,
            sib_mid_compressed - sib_side
        ], axis=1)
    else:
        sib_compressed = sib * gain[:, np.newaxis]

    # Recombine: compressed sibilance band + untouched low + untouched high
    return low + sib_compressed + high

    if audio.shape[1] == 1:
        return _de_ess_mono(audio, sr, freq_lo, freq_hi, threshold_db,
                            ratio, max_cut_db, attack_ms, release_ms)

    freq_hi = min(freq_hi, sr / 2 - 200)
    n = len(audio)

    # ── Auto-detect mode ─────────────────────────────────────────────────────
    if mode == 'auto':
        sos_det = _butter_sos([freq_lo, freq_hi], sr, btype='bandpass', order=2)
        L_sib = _apply_sos(sos_det, audio[:, 0:1])[:,0]
        R_sib = _apply_sos(sos_det, audio[:, 1:2])[:,0]
        # Sample active sibilance windows (top 10% of L band level)
        hop = max(1, int(0.05 * sr))
        n_h = (n + hop - 1) // hop
        pad = np.pad(L_sib**2, (0, n_h*hop-n))
        env_L = np.sqrt(np.mean(pad.reshape(n_h,hop),axis=1)+1e-24)
        thresh_active = np.percentile(env_L, 90)
        active = env_L > thresh_active
        if active.any():
            l_sq_pad = np.pad(L_sib**2, (0, n_h*hop-n))
            l_rms = np.sqrt(np.mean(
                l_sq_pad.reshape(n_h, hop).mean(axis=1)[active[:n_h]]
            ) + 1e-24)
            r_env = np.sqrt(np.mean(np.pad(R_sib**2,(0,n_h*hop-n)).reshape(n_h,hop),axis=1)+1e-24)
            r_rms = np.sqrt(np.mean(r_env[active[:n_h]])+1e-24)
            lr_diff = abs(20*np.log10(l_rms+1e-12) - 20*np.log10(r_rms+1e-12))
        else:
            lr_diff = 0.0
        mode = 'mid' if lr_diff <= 2.0 else 'wideband'
        print(f"  De-esser   : auto→{mode} (L/R sibilance imbalance {lr_diff:.1f} dB)")

    # ── Detection signal ─────────────────────────────────────────────────────
    mid = (audio[:,0] + audio[:,1]) * 0.5
    sos_det = _butter_sos([freq_lo, freq_hi], sr, btype='bandpass', order=4)

    if mode == 'mid':
        det_sig = _apply_sos(sos_det, mid[:,np.newaxis])[:,0]
    else:
        det_sig = _apply_sos(sos_det, audio).mean(axis=1)

    # ── Envelope follower ────────────────────────────────────────────────────
    hop    = max(1, int(attack_ms * 1e-3 * sr))
    n_hops = (n + hop - 1) // hop
    padded = np.pad(det_sig ** 2, (0, n_hops * hop - n))
    env    = np.sqrt(np.mean(padded.reshape(n_hops, hop), axis=1) + 1e-24)

    p90_db        = 20 * np.log10(np.percentile(env, 90) + 1e-12)
    abs_thresh_db = p90_db + threshold_db
    thresh        = 10 ** (abs_thresh_db / 20)
    max_cut       = 10 ** (-max_cut_db   / 20)

    a_att = np.exp(-1.0 / max(1, attack_ms  * 1e-3 * sr / hop))
    a_rel = np.exp(-1.0 / max(1, release_ms * 1e-3 * sr / hop))
    e_att = signal.lfilter([1-a_att],[1,-a_att], env)
    e_rel = signal.lfilter([1-a_rel],[1,-a_rel], e_att)
    e     = np.maximum(e_att, e_rel)

    gain_hops = np.where(
        e > thresh,
        np.maximum(thresh*(e/(thresh+1e-24))**(1/ratio)/(e+1e-24), max_cut),
        1.0)
    gain_hops = gaussian_filter1d(gain_hops, sigma=2)
    gain = np.interp(np.arange(n),
                     np.arange(n_hops)*hop+hop//2,
                     gain_hops)

    active_pct = (gain_hops < 0.99).mean() * 100
    avg_cut_db = 20*np.log10(gain_hops[gain_hops<0.99].mean()+1e-12) \
                 if (gain_hops<0.99).any() else 0.0
    print(f"  De-esser   : {mode}  {freq_lo//1000}–{freq_hi//1000} kHz  "
          f"thresh {abs_thresh_db:.1f} dBRMS  "
          f"{ratio:.0f}:1  max -{max_cut_db:.0f}dB  "
          f"active {active_pct:.1f}%  avg {avg_cut_db:.1f} dB")

    # ── Apply gain ───────────────────────────────────────────────────────────
    if mode == 'mid':
        # Reduce mid only — preserves side channel and stereo width
        side    = (audio[:,0] - audio[:,1]) * 0.5
        mid_out = mid * gain
        return np.stack([mid_out + side, mid_out - side], axis=1)
    else:
        # Wideband — reduce L and R equally, preserves L/R balance
        return audio * gain[:, np.newaxis]


def _de_ess_mono(audio, sr, freq_lo, freq_hi, threshold_db, ratio,
                 max_cut_db, attack_ms, release_ms):
    """Fallback wideband de-esser for mono signals."""
    freq_hi = min(freq_hi, sr / 2 - 200)
    n       = len(audio)
    sos_bp  = _butter_sos([freq_lo, freq_hi], sr, btype='bandpass', order=2)
    band    = _apply_sos(sos_bp, audio)
    rest    = audio - band

    hop    = max(1, int(attack_ms * 1e-3 * sr))
    n_hops = (n + hop - 1) // hop
    padded = np.pad(band.mean(axis=1) ** 2, (0, n_hops * hop - n))
    env    = np.sqrt(np.mean(padded.reshape(n_hops, hop), axis=1) + 1e-24)

    p90_db        = 20 * np.log10(np.percentile(env, 90) + 1e-12)
    abs_thresh_db = p90_db + threshold_db
    thresh        = 10 ** (abs_thresh_db / 20)
    max_cut       = 10 ** (-max_cut_db   / 20)

    a_att = np.exp(-1.0 / max(1, attack_ms  * 1e-3 * sr / hop))
    a_rel = np.exp(-1.0 / max(1, release_ms * 1e-3 * sr / hop))
    e_att = signal.lfilter([1-a_att],[1,-a_att], env)
    e_rel = signal.lfilter([1-a_rel],[1,-a_rel], e_att)
    e     = np.maximum(e_att, e_rel)

    gain_hops = np.where(e > thresh,
        np.maximum(thresh*(e/(thresh+1e-24))**(1/ratio)/(e+1e-24), max_cut), 1.0)
    gain_hops = gaussian_filter1d(gain_hops, sigma=2)
    gain = np.interp(np.arange(n), np.arange(n_hops)*hop+hop//2, gain_hops)

    active_pct = (gain_hops < 0.99).mean() * 100
    print(f"  De-esser   : mono wideband  active {active_pct:.1f}%")
    return audio * gain[:, np.newaxis]


#  Frequency-selective compressor: only attenuates 2–4 kHz when that band
#  exceeds a threshold.  Leaves the band alone in quieter passages so the
#  cut doesn't dull the track globally.
# ══════════════════════════════════════════════════════════════════════════════

def dynamic_eq(audio: np.ndarray, sr: int,
               freq_lo: float = 2000, freq_hi: float = 4000,
               threshold_db: float = -24, ratio: float = 3.0,
               max_cut_db: float = 3.0) -> np.ndarray:
    """
    Dynamic EQ: threshold-driven cut in the presence/harshness band.
    threshold_db is relative to the band's own median RMS level so it
    adapts to the track's overall brightness — louder tracks still get
    the cut when the band peaks above its own average.
    """
    sos_bp = _butter_sos([freq_lo, freq_hi], sr, btype='bandpass', order=2)
    band   = _apply_sos(sos_bp, audio)
    rest   = audio - band

    hop    = max(1, int(0.005 * sr))
    n      = len(audio)
    n_hops = (n + hop - 1) // hop
    band_sq = band.mean(axis=1) ** 2
    padded  = np.pad(band_sq, (0, n_hops * hop - n))
    rms_env = np.sqrt(np.mean(padded.reshape(n_hops, hop), axis=1) + 1e-24)

    # Make threshold relative: median band level + threshold_db offset
    band_median_db = 20 * np.log10(np.median(rms_env) + 1e-12)
    abs_thresh_db  = band_median_db - threshold_db   # e.g. median-24 → peaks 24dB above median
    thresh = 10 ** (abs_thresh_db / 20)
    max_cut = 10 ** (-max_cut_db / 20)

    a_att = np.exp(-1.0 / max(1, 10e-3 * sr / hop))
    a_rel = np.exp(-1.0 / max(1, 80e-3 * sr / hop))
    env   = np.maximum(signal.lfilter([1-a_att],[1,-a_att], rms_env),
                       signal.lfilter([1-a_rel],[1,-a_rel], rms_env))

    gain_hops = np.where(env > thresh,
        np.maximum(thresh * (env/(thresh+1e-24))**(1/ratio)/(env+1e-24), max_cut),
        1.0)
    gain_hops = gaussian_filter1d(gain_hops, sigma=3)
    gain = np.interp(np.arange(n),
                     np.arange(n_hops) * hop + hop // 2,
                     gain_hops)

    active_pct = (gain_hops < 0.99).mean() * 100
    avg_cut_db = 20 * np.log10(gain_hops[gain_hops < 0.99].mean() + 1e-12) \
                 if (gain_hops < 0.99).any() else 0.0
    print(f"  Dynamic EQ : {freq_lo//1000}–{freq_hi//1000} kHz  "
          f"thresh {abs_thresh_db:.1f} dBRMS  "
          f"active {active_pct:.0f}% of track  "
          f"avg cut {avg_cut_db:.1f} dB")

    return rest + band * gain[:, np.newaxis]


def transient_shape(audio: np.ndarray, sr: int,
                    attack_boost_db: float = 2.5,
                    attack_ms: float = 6.0,
                    sensitivity: float = 10.0,
                    min_interval_ms: float = 50.0) -> np.ndarray:
    """
    Restore transient attack flattened by Suno's internal compression.

    sensitivity     : dB above slow RMS to qualify as transient (higher = fewer)
    min_interval_ms : minimum gap between detected onsets (prevents bass cycles
                      being detected as transients)
    """
    n          = len(audio)
    attack_win = int(attack_ms * 1e-3 * sr)
    min_gap    = int(min_interval_ms * 1e-3 * sr)
    mono       = audio.mean(axis=1)

    hop     = max(1, int(0.005 * sr))
    n_hops  = (n + hop - 1) // hop
    padded  = np.pad(mono ** 2, (0, n_hops * hop - n))
    rms_hop = np.sqrt(np.mean(padded.reshape(n_hops, hop), axis=1) + 1e-24)
    rms_slow = gaussian_filter1d(rms_hop, sigma=int(0.15 * sr / hop))
    rms_slow_s = np.interp(np.arange(n),
                            np.arange(n_hops) * hop + hop // 2,
                            rms_slow)

    thresh_lin   = rms_slow_s * 10 ** (sensitivity / 20)
    is_transient = np.abs(mono) > thresh_lin
    raw_onsets   = np.where(np.diff(is_transient.astype(int)) == 1)[0]

    # Enforce minimum interval between onsets
    onsets = []
    last   = -min_gap
    for o in raw_onsets:
        if o - last >= min_gap:
            onsets.append(o)
            last = o

    if not onsets:
        print(f"  Transient  : no transients detected — skipping")
        return audio

    boost_lin = 10 ** (attack_boost_db / 20)
    gain_env  = np.ones(n)
    ramp_up   = np.linspace(1.0, boost_lin, max(1, attack_win // 4))
    ramp_down = np.linspace(boost_lin, 1.0, attack_win)

    for onset in onsets:
        u_end = min(onset + len(ramp_up), n)
        gain_env[onset:u_end] = np.maximum(
            gain_env[onset:u_end], ramp_up[:u_end - onset])
        d_start = onset + len(ramp_up)
        d_end   = min(d_start + len(ramp_down), n)
        if d_start < n:
            gain_env[d_start:d_end] = np.maximum(
                gain_env[d_start:d_end], ramp_down[:d_end - d_start])

    gain_env = gaussian_filter1d(gain_env, sigma=max(1, attack_win // 8))

    print(f"  Transient  : {len(onsets)} onsets  "
          f"+{attack_boost_db} dB  {attack_ms:.0f}ms  "
          f"sensitivity {sensitivity} dB  min gap {min_interval_ms:.0f}ms")
    return audio * gain_env[:, np.newaxis]


# ══════════════════════════════════════════════════════════════════════════════
#  F. REFERENCE MATCH
#  Uses Matchering to align the target's RMS, frequency response, peak
#  amplitude and stereo width to a reference track.
# ══════════════════════════════════════════════════════════════════════════════

def reference_match(input_path: str, reference_path: str,
                    output_path: str) -> str:
    """
    Match input_path to reference_path and write to output_path.
    Returns output_path.
    Raises ImportError if matchering is not installed.
    """
    try:
        import matchering as mg
    except ImportError:
        raise ImportError(
            "matchering is not installed. Run: pip install matchering"
        )

    print(f"  Ref match  : matching to {Path(reference_path).name}")
    mg.process(
        target    = input_path,
        reference = reference_path,
        results   = [mg.Result(output_path,
                               subtype='PCM_16',
                               use_limiter=False,
                               normalize=False)]
    )

    a, sr = sf.read(output_path, always_2d=True)
    print(f"  Ref match  : done  peak {_db(a):+.1f} dBFS  "
          f"RMS {_rmsdb(a):+.1f} dBRMS")
    return output_path


