#!/usr/bin/env python3
"""
analyser.py — Analyse a WAV file and recommend mastering settings.

Measures:
  - Loudness (LUFS, dynamic range, true peak)
  - Stereo image (M/S balance, L/R sibilance balance, bass in side)
  - Spectral profile (air above 16kHz, 8-16kHz flatness, low-mid mud,
                      presence harshness, high-frequency rolloff)
  - Sibilance (peak level, frequency, L/R balance)
  - Transients (detected count, estimated compression level)
  - Dropout detection (potential jinx zones)
  - AI engine fingerprint (Suno vs other based on spectral signature)

Returns a dict of findings and recommended settings.
"""

import numpy as np
import soundfile as sf
import pyloudnorm as pyln
from scipy import signal
from scipy.ndimage import gaussian_filter1d
from pathlib import Path


# ── Helpers ───────────────────────────────────────────────────────────────────

def _rms(x):    return float(np.sqrt(np.mean(x ** 2)))
def _rmsdb(x):  return 20.0 * np.log10(max(_rms(x), 1e-12))
def _peakdb(x): return 20.0 * np.log10(max(float(np.max(np.abs(x))), 1e-12))

def _band(audio, lo, hi, sr, order=2):
    lo = max(lo, 10)
    hi = min(hi, sr // 2 - 100)
    if lo >= hi:
        return np.zeros_like(audio)
    sos = signal.butter(order, [lo / (sr/2), hi / (sr/2)],
                        btype='bandpass', output='sos')
    return signal.sosfilt(sos, audio, axis=0)

def _hop_env(sig, hop):
    n      = len(sig)
    n_hops = (n + hop - 1) // hop
    padded = np.pad(sig ** 2, (0, n_hops * hop - n))
    return np.sqrt(np.mean(padded.reshape(n_hops, hop), axis=1) + 1e-24)


# ══════════════════════════════════════════════════════════════════════════════
#  ANALYSIS FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def _analyse_loudness(audio, sr):
    meter    = pyln.Meter(sr)
    lufs     = meter.integrated_loudness(audio)
    peak_db  = _peakdb(audio)

    # Dynamic range: difference between loud and quiet sections
    hop      = int(0.5 * sr)
    n        = len(audio)
    mono     = audio.mean(axis=1)
    n_hops   = (n + hop - 1) // hop
    padded   = np.pad(mono**2, (0, n_hops*hop-n))
    rms_hops = 20*np.log10(np.sqrt(np.mean(padded.reshape(n_hops,hop),axis=1))+1e-12)
    smooth   = gaussian_filter1d(rms_hops, sigma=4)
    dyn      = float(smooth.max() - smooth.min())

    # True peak via 4x oversample chunk
    chunk_size = sr
    tp = 0.0
    for lo in range(0, n, chunk_size):
        up = signal.resample_poly(audio[lo:lo+chunk_size], 4, 1, axis=0)
        tp = max(tp, float(np.max(np.abs(up))))
    tp_db = 20*np.log10(max(tp, 1e-12))

    return dict(lufs=lufs, peak_db=peak_db, true_peak_db=tp_db,
                dynamic_range_db=dyn)


def _analyse_stereo(audio, sr):
    if audio.shape[1] == 1:
        return dict(mono=True)

    mid  = (audio[:,0] + audio[:,1]) * 0.5
    side = (audio[:,0] - audio[:,1]) * 0.5

    # Overall M/S balance
    mid_rms  = _rms(mid)
    side_rms = _rms(side)
    mid_pct  = mid_rms / (mid_rms + side_rms + 1e-12) * 100

    # Sub-bass in side (problem indicator)
    sub_mid  = _band(mid[:,np.newaxis],  20, 120, sr)
    sub_side = _band(side[:,np.newaxis], 20, 120, sr)
    sub_ratio = _rmsdb(sub_side) - _rmsdb(sub_mid)  # should be < -10dB

    # Worst M/S imbalance moment
    hop    = int(0.5 * sr)
    n      = len(audio)
    n_hops = (n + hop - 1) // hop
    mid_sq  = np.pad(mid**2,  (0, n_hops*hop-n))
    side_sq = np.pad(side**2, (0, n_hops*hop-n))
    mid_h   = np.sqrt(np.mean(mid_sq.reshape(n_hops,hop),  axis=1)+1e-24)
    side_h  = np.sqrt(np.mean(side_sq.reshape(n_hops,hop), axis=1)+1e-24)
    mid_pcts = mid_h / (mid_h + side_h + 1e-12) * 100
    worst_mid_pct = float(mid_pcts.min())

    # L/R sibilance imbalance (vocal centring)
    sib_L = _band(audio[:,0:1], 5000, 10000, sr)
    sib_R = _band(audio[:,1:2], 5000, 10000, sr)
    hop_s = max(1, int(0.05*sr))
    n_hs  = (n+hop_s-1)//hop_s
    env_L = _hop_env(sib_L[:,0], hop_s)
    env_R = _hop_env(sib_R[:,0], hop_s)
    active = env_L > np.percentile(env_L, 90)
    if active.any():
        lr_diff = float(abs(
            20*np.log10(env_L[active].mean()+1e-12) -
            20*np.log10(env_R[active].mean()+1e-12)
        ))
    else:
        lr_diff = 0.0

    return dict(mono=False, mid_pct=float(mid_pct),
                worst_mid_pct=worst_mid_pct,
                sub_side_vs_mid_db=float(sub_ratio),
                sibilance_lr_diff_db=lr_diff)


def _analyse_spectrum(audio, sr):
    mono = audio.mean(axis=1)
    n    = len(mono)

    def band_rms(lo, hi):
        return _rmsdb(_band(mono[:,np.newaxis], lo, hi, sr)[:,0])

    sub_rms      = band_rms(20,   120)
    bass_rms     = band_rms(120,  300)
    lo_mid_rms   = band_rms(300,  800)
    mid_rms      = band_rms(800,  3000)
    presence_rms = band_rms(2000, 5000)
    air_rms      = band_rms(8000, 16000)
    above16_rms  = band_rms(16000, min(20000, sr//2-100))

    # High-frequency rolloff: is there content above 16kHz?
    has_air_above_16k = above16_rms > (air_rms - 25)

    # 8-16kHz flatness (Suno diffusion haze): measure variance of spectral energy
    seg_len = min(n, int(2.0*sr))
    f, psd  = signal.welch(mono[:seg_len], sr, nperseg=min(seg_len, 2048))
    mask    = (f >= 8000) & (f < 16000)
    if mask.sum() > 4:
        psd_norm = psd[mask] / (psd[mask].mean() + 1e-12)
        spectral_variance = float(np.std(psd_norm))   # low = unnaturally flat
    else:
        spectral_variance = 1.0

    # Low-mid mud: how much energy in 300-500Hz vs 800-2kHz
    mud_rms  = band_rms(300, 500)
    ref_rms  = band_rms(800, 2000)
    mud_diff = mud_rms - ref_rms   # > 0 = muddy

    # Presence harshness: 2-4kHz vs 800Hz-2kHz
    harsh_rms  = band_rms(2000, 4000)
    harsh_diff = harsh_rms - mid_rms

    return dict(
        sub_rms=sub_rms, bass_rms=bass_rms,
        lo_mid_rms=lo_mid_rms, mid_rms=mid_rms,
        presence_rms=presence_rms, air_rms=air_rms,
        above16k_rms=above16_rms,
        has_air_above_16k=has_air_above_16k,
        spectral_variance=spectral_variance,
        mud_diff_db=float(mud_diff),
        harsh_diff_db=float(harsh_diff)
    )


def _analyse_sibilance(audio, sr):
    mono   = audio.mean(axis=1)
    sib    = _band(mono[:,np.newaxis], 5000, 10000, sr)[:,0]
    hop    = max(1, int(0.001*sr))
    env    = _hop_env(sib, hop)
    env_db = 20*np.log10(env+1e-12)
    p90_db = 20*np.log10(np.percentile(env, 90)+1e-12)
    peak   = float(env_db.max())
    headroom_above_p90 = peak - p90_db
    return dict(peak_db=peak, p90_db=float(p90_db),
                headroom_db=float(headroom_above_p90))


def _analyse_transients(audio, sr):
    mono     = audio.mean(axis=1)
    n        = len(mono)
    hop      = max(1, int(0.005*sr))
    n_hops   = (n+hop-1)//hop
    padded   = np.pad(mono**2, (0,n_hops*hop-n))
    rms_hop  = np.sqrt(np.mean(padded.reshape(n_hops,hop),axis=1)+1e-24)
    rms_slow = gaussian_filter1d(rms_hop, sigma=int(0.15*sr/hop))
    thresh   = rms_slow * 10**(10/20)
    is_tr    = rms_hop > thresh
    onsets   = int(np.sum(np.diff(is_tr.astype(int))==1))
    dur_min  = n/sr/60
    onsets_per_min = onsets / max(dur_min, 0.1)
    # Crest factor: high = punchy, low = compressed
    peak = float(np.max(np.abs(mono)))
    rms_ = _rms(mono)
    crest_db = 20*np.log10(max(peak,1e-12)) - 20*np.log10(max(rms_,1e-12))
    return dict(onset_count=onsets, onsets_per_min=float(onsets_per_min),
                crest_factor_db=float(crest_db))


def _analyse_dropouts(audio, sr):
    """
    Detect synthesis dropouts using the same parameters as dejinx.py:
    - threshold 10 dB below context (not 6 — avoids musical beat gaps)
    - minimum duration 80ms (beat gaps at 90 BPM are typically 20-70ms)
    - context window 500ms (spans a full musical phrase, not just one beat)
    """
    mono     = audio.mean(axis=1)
    n        = len(mono)
    hop      = int(0.005 * sr)    # 5ms hops
    n_hops   = (n + hop - 1) // hop
    padded   = np.pad(mono**2, (0, n_hops*hop - n))
    rms_hop  = np.sqrt(np.mean(padded.reshape(n_hops, hop), axis=1) + 1e-24)
    env_db   = 20*np.log10(rms_hop + 1e-12)

    # Context: 500ms window, 60th percentile (same as dejinx)
    ctx_frames = int(0.500 * sr / hop)
    context_db = np.zeros(n_hops)
    for i in range(n_hops):
        lo = max(0, i - ctx_frames)
        hi = min(n_hops, i + ctx_frames)
        excl_lo = max(lo, i - ctx_frames//5)
        excl_hi = min(hi, i + ctx_frames//5)
        window  = np.concatenate([env_db[lo:excl_lo], env_db[excl_hi:hi]])
        context_db[i] = np.percentile(window, 60) if len(window) > 0 else env_db[i]

    drop       = context_db - env_db
    is_dropout = drop > 10.0   # 10 dB threshold (not 6)
    min_hops   = int(0.080 * sr / hop)  # 80ms minimum duration
    max_hops   = int(0.300 * sr / hop)  # 300ms maximum duration

    n_dropouts = 0
    in_d = False; start = 0
    for i in range(n_hops):
        if is_dropout[i] and not in_d:
            in_d = True; start = i
        elif not is_dropout[i] and in_d:
            in_d = False
            dur = i - start
            if min_hops <= dur <= max_hops:
                n_dropouts += 1

    return dict(dropout_count=n_dropouts)



# ══════════════════════════════════════════════════════════════════════════════
#  RECOMMENDATIONS
# ══════════════════════════════════════════════════════════════════════════════

def _detect_engine(spectrum, stereo):
    """
    Heuristic engine detection based on spectral fingerprint.
    Suno: hard cutoff at 16kHz, flat 8-16kHz haze, narrow stereo.
    """
    score = 0
    reasons = []
    if not spectrum['has_air_above_16k']:
        score += 2; reasons.append("hard spectral cutoff at 16 kHz")
    if spectrum['spectral_variance'] < 0.5:
        score += 2; reasons.append("unusually flat 8–16 kHz energy (diffusion haze)")
    if not stereo.get('mono') and stereo.get('mid_pct', 70) > 72:
        score += 1; reasons.append("narrow stereo image")
    if not stereo.get('mono') and stereo.get('sub_side_vs_mid_db', -20) > -8:
        score += 1; reasons.append("bass leaking into side channel")
    engine = 'Suno' if score >= 3 else 'Other / Unknown'
    return dict(engine=engine, confidence_score=score, reasons=reasons)


def _recommend(loudness, stereo, spectrum, sibilance, transients,
               dropouts, engine_info):
    recs  = []   # list of (category, message, setting)
    settings = {}

    # ── Width ────────────────────────────────────────────────────────────────
    if stereo.get('mono'):
        settings['presence_gain'] = 0.0
        recs.append(('Width', 'Mono source — no stereo widening.', 'Other AI (0 dB)'))
    elif stereo.get('sibilance_lr_diff_db', 0) > 2.0:
        settings['presence_gain'] = 0.0
        settings['deess_mode']    = 'wideband'
        recs.append(('Width',
            f"Vocal sibilance is {stereo['sibilance_lr_diff_db']:.1f} dB off-centre "
            f"(left-heavy). Use Other AI preset to avoid sibilance drifting left. "
            f"De-esser set to wideband mode.",
            'Other AI (0 dB)'))
    elif engine_info['engine'] == 'Suno':
        settings['presence_gain'] = 0.25
        recs.append(('Width',
            'Suno fingerprint detected — presence widening recommended.',
            'Suno (+1.9 dB)'))
    else:
        settings['presence_gain'] = 0.0
        recs.append(('Width',
            'Non-Suno source — bass anchor only, no presence boost.',
            'Other AI (0 dB)'))

    # ── De-esser ─────────────────────────────────────────────────────────────
    # De-esser slider: -2=Off, 0=Very gentle → 7=Max (aggressiveness scale)
    # Slider comment: 0-7 where higher = more aggressive
    if sibilance['headroom_db'] > 12:
        settings['deess_threshold'] = 5   # Strong
        recs.append(('De-esser',
            f"Strong sibilance peaks detected ({sibilance['headroom_db']:.0f} dB above "
            f"typical level). Recommend Strong setting.",
            'Strong'))
    elif sibilance['headroom_db'] > 8:
        settings['deess_threshold'] = 3   # Medium
        recs.append(('De-esser',
            f"Moderate sibilance ({sibilance['headroom_db']:.0f} dB above typical). "
            f"Medium setting.",
            'Medium'))
    else:
        settings['deess_threshold'] = 1   # Gentle
        recs.append(('De-esser',
            f"Sibilance is mild ({sibilance['headroom_db']:.0f} dB above typical). "
            f"Gentle setting.",
            'Gentle'))

    # ── Air restoration ──────────────────────────────────────────────────────
    if not spectrum['has_air_above_16k']:
        recs.append(('Air restore',
            'Hard spectral cutoff at 16 kHz detected — consistent with Suno. '
            'Air restoration will run automatically.',
            'On (auto)'))
    else:
        recs.append(('Air restore',
            'High-frequency content present above 16 kHz — source already has air.',
            'On (subtle)'))

    # ── Mud ──────────────────────────────────────────────────────────────────
    if spectrum['mud_diff_db'] > 3:
        recs.append(('Low-mid EQ',
            f"Noticeable low-mid buildup at 300–500 Hz "
            f"({spectrum['mud_diff_db']:.1f} dB above mid). "
            "Low-mid cut in EQ stage will help.",
            'Auto (−2 dB @ 380 Hz)'))

    # ── Harshness ────────────────────────────────────────────────────────────
    if spectrum['harsh_diff_db'] > 2:
        recs.append(('Dynamic EQ',
            f"Presence band (2–4 kHz) is {spectrum['harsh_diff_db']:.1f} dB above "
            "mid average — dynamic EQ will catch harsh moments.",
            'Auto'))

    # ── Sub-bass in side ─────────────────────────────────────────────────────
    if not stereo.get('mono') and stereo.get('sub_side_vs_mid_db', -20) > -8:
        recs.append(('Bass anchor',
            f"Sub-bass is only {abs(stereo['sub_side_vs_mid_db']):.0f} dB quieter in "
            "side vs mid — bass leaking into side channel. Bass anchoring will help "
            "but may not fully resolve if the panning is extreme.",
            'Auto (120 Hz)'))

    # ── Dropouts ─────────────────────────────────────────────────────────────
    if dropouts['dropout_count'] > 0:
        recs.append(('De-Jinx',
            f"{dropouts['dropout_count']} potential synthesis dropout(s) detected. "
            "Run the ⚡ De-Jinx tab first before mastering.",
            f"{dropouts['dropout_count']} zone(s)"))

    # Vocal ride — always recommend
    settings['vocal_boost_db'] = 4.0
    recs.append(('Vocal ride',
        'Restores buried vocals in the second half of the track. '
        'The tool auto-detects where the vocal drops and rides it back up.',
        '+4 dB max (auto)'))

    # ── Transients ───────────────────────────────────────────────────────────
    if transients['crest_factor_db'] < 8:
        recs.append(('Transients',
            f"Low crest factor ({transients['crest_factor_db']:.1f} dB) — track has "
            "been heavily compressed internally. Transient shaping will restore snap.",
            'Auto'))

    # ── LUFS ─────────────────────────────────────────────────────────────────
    lufs_diff = abs(loudness['lufs'] - (-14.0))
    if lufs_diff > 6:
        recs.append(('Loudness',
            f"Track is at {loudness['lufs']:+.1f} LUFS — "
            f"{'very quiet' if loudness['lufs'] < -14 else 'over target'}. "
            f"Will be normalised to −14 LUFS ({lufs_diff:+.1f} dB adjustment).",
            f"{loudness['lufs']:+.1f} → −14.0 LUFS"))

    settings['notes'] = recs
    return settings


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def _sanitise(obj):
    """Recursively convert numpy scalars to Python natives for JSON serialisation."""
    if isinstance(obj, dict):
        return {k: _sanitise(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitise(v) for v in obj]
    if isinstance(obj, np.integer):  return int(obj)
    if isinstance(obj, np.floating): return float(obj)
    if isinstance(obj, np.bool_):    return bool(obj)
    if isinstance(obj, np.ndarray):  return obj.tolist()
    return obj


def analyse(input_path: str) -> dict:
    audio, sr = sf.read(input_path, always_2d=True)
    audio     = audio.astype(np.float64)
    duration  = len(audio) / sr

    loudness   = _analyse_loudness(audio, sr)
    stereo     = _analyse_stereo(audio, sr)
    spectrum   = _analyse_spectrum(audio, sr)
    sibilance  = _analyse_sibilance(audio, sr)
    transients = _analyse_transients(audio, sr)
    dropouts   = _analyse_dropouts(audio, sr)
    engine     = _detect_engine(spectrum, stereo)
    settings   = _recommend(loudness, stereo, spectrum, sibilance,
                             transients, dropouts, engine)

    return _sanitise(dict(
        file        = str(Path(input_path).name),
        duration_s  = round(duration, 1),
        sample_rate = sr,
        channels    = audio.shape[1],
        loudness    = loudness,
        stereo      = stereo,
        spectrum    = spectrum,
        sibilance   = sibilance,
        transients  = transients,
        dropouts    = dropouts,
        engine      = engine,
        recommended = settings,
    ))


if __name__ == '__main__':
    import sys, json
    if len(sys.argv) < 2:
        print("Usage: python analyser.py track.wav")
        sys.exit(1)
    result = analyse(sys.argv[1])
    rec = result['recommended']
    eng = result['engine']
    print(f"\n{'═'*54}")
    print(f"  Analysis: {result['file']}")
    print(f"{'═'*54}")
    print(f"  Duration   : {result['duration_s']:.1f}s  "
          f"| {result['sample_rate']} Hz  | {result['channels']}ch")
    print(f"  Engine     : {eng['engine']}  (score {eng['confidence_score']}/6)")
    if eng['reasons']:
        for r in eng['reasons']:
            print(f"               · {r}")
    l = result['loudness']
    print(f"  Loudness   : {l['lufs']:+.1f} LUFS  "
          f"peak {l['peak_db']:+.1f} dBFS  "
          f"true peak {l['true_peak_db']:+.1f} dBTP  "
          f"DR {l['dynamic_range_db']:.1f} dB")
    if not result['stereo'].get('mono'):
        s = result['stereo']
        print(f"  Stereo     : {s['mid_pct']:.0f}% mid  "
              f"worst {s['worst_mid_pct']:.0f}%  "
              f"sub-side {s['sub_side_vs_mid_db']:+.1f} dB  "
              f"L/R sib diff {s['sibilance_lr_diff_db']:.1f} dB")
    print(f"  Sibilance  : peak {result['sibilance']['peak_db']:+.1f} dBRMS  "
          f"+{result['sibilance']['headroom_db']:.0f} dB above typical")
    print(f"  Transients : {result['transients']['onset_count']} onsets  "
          f"crest {result['transients']['crest_factor_db']:.1f} dB")
    print(f"  Dropouts   : {result['dropouts']['dropout_count']} detected")
    print(f"\n  Recommended settings:")
    for cat, msg, setting in rec.get('notes', []):
        print(f"  [{cat}] {setting}")
        print(f"    {msg}")
