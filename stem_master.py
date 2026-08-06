"""
stem_master.py — Per-stem mastering using Demucs separation.

Separates a track into vocals, drums, bass, other using Demucs,
applies independent mastering settings to each stem, then recombines
and normalises the final mix.

This solves the core limitation of full-mix mastering: vocals and
instrumentals often have different optimal processing needs. A cinematic
track (e.g. The Giant) benefits from full vocal processing but loses
instrumental impact when the bass is anchored to centre or the stereo
field is narrowed.

Requires: pip install demucs
"""

import numpy as np
import soundfile as sf
import tempfile
import os
import shutil
from pathlib import Path
from scipy import signal as sg
from scipy.ndimage import gaussian_filter1d


# ── Helpers ───────────────────────────────────────────────────────────────────

def _rms_db(x):
    return 20.0 * np.log10(np.sqrt(np.mean(x**2)) + 1e-12)

def _db_to_lin(db):
    return 10 ** (db / 20.0)


def _demucs_available():
    try:
        import demucs  # noqa
        return True
    except ImportError:
        return False


# ── Stem separation ───────────────────────────────────────────────────────────

def separate_stems(input_path: str, model: str = 'htdemucs') -> dict:
    """
    Separate a WAV into stems using Demucs.

    Returns dict: {'vocals': ndarray, 'drums': ndarray, 'bass': ndarray,
                   'other': ndarray, 'sr': int}
    """
    if not _demucs_available():
        raise ImportError("Demucs not installed. Run: pip install demucs")

    import demucs.separate

    tmp_dir = tempfile.mkdtemp()
    try:
        # Save input as 24-bit for best quality
        tmp_in = os.path.join(tmp_dir, 'input.wav')
        audio, sr = sf.read(input_path, always_2d=True)
        audio = audio.astype(np.float64)
        sf.write(tmp_in, audio, sr, subtype='PCM_24')

        print(f"  Stem sep   : separating with {model}...")
        demucs.separate.main([
            '--name', model,
            '--out',  tmp_dir,
            tmp_in
        ])

        stem_dir = Path(tmp_dir) / model / 'input'
        stems = {}
        stem_sr = None
        for stem_name in ['vocals', 'drums', 'bass', 'other']:
            path = stem_dir / f'{stem_name}.wav'
            if path.exists():
                data, this_sr = sf.read(str(path), always_2d=True)
                stems[stem_name] = data.astype(np.float64)
                if stem_sr is None:
                    stem_sr = this_sr  # Demucs always outputs at same sr for all stems
                print(f"  Stem sep   : {stem_name} — "
                      f"{_rms_db(data):+.1f} dBRMS  "
                      f"{data.shape[0]/this_sr:.1f}s  {this_sr}Hz")
            else:
                raise FileNotFoundError(f"Stem not found: {path}")

        if stem_sr is None:
            stem_sr = sr  # fallback

        if stem_sr != sr:
            print(f"  Stem sep   : Demucs output {stem_sr}Hz "
                  f"(input was {sr}Hz) — using stem sr")

        stems['sr'] = stem_sr  # use actual Demucs output rate, not input rate
        return stems

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Per-stem processing ────────────────────────────────────────────────────────

def _butter_sos(freq, sr, btype, order=4):
    wn = np.atleast_1d(np.asarray(freq, dtype=float)) / (sr / 2)
    if btype in ('low', 'high'):
        wn = float(wn[0])
    return sg.butter(order, wn, btype=btype, output='sos')

def _apply_sos(sos, audio):
    return sg.sosfilt(sos, audio, axis=0)

def _compress(audio, sr, threshold_db=-18, ratio=2.0,
              attack_ms=20, release_ms=150, makeup_db=1.0):
    """Simple broadband compressor on mid channel."""
    n = len(audio)
    mid  = (audio[:,0] + audio[:,1]) * 0.5
    side = (audio[:,0] - audio[:,1]) * 0.5
    hop  = max(1, int(attack_ms * 0.001 * sr))
    n_h  = (n + hop - 1) // hop
    env  = np.sqrt(np.mean(
        np.pad(mid**2, (0,n_h*hop-n)).reshape(n_h,hop), axis=1) + 1e-24)
    thresh  = _db_to_lin(threshold_db)
    makeup  = _db_to_lin(makeup_db)
    a_att   = np.exp(-1/(attack_ms*0.001*sr/hop))
    a_rel   = np.exp(-1/(release_ms*0.001*sr/hop))
    e_att   = sg.lfilter([1-a_att],[1,-a_att], env)
    e_rel   = sg.lfilter([1-a_rel],[1,-a_rel], e_att)
    e       = np.maximum(e_att, e_rel)
    gain_h  = np.where(e>thresh,
        thresh*(e/(thresh+1e-24))**(1/ratio)/(e+1e-24)*makeup, makeup)
    gain_h  = gaussian_filter1d(gain_h, sigma=2)
    gain    = np.interp(np.arange(n), np.arange(n_h)*hop+hop//2, gain_h)
    mid_out = mid * gain
    return np.stack([mid_out+side, mid_out-side], axis=1)

def _eq_shelf(audio, sr, freq, gain_db):
    """High or low shelf EQ."""
    if abs(gain_db) < 0.1:
        return audio
    A  = 10**(gain_db/40)
    w0 = 2*np.pi*freq/sr
    alpha = np.sin(w0)/2 * np.sqrt((A+1/A)*(1/0.707-1)+2)
    if gain_db > 0:
        b = [A*((A+1)+(A-1)*np.cos(w0)+2*np.sqrt(A)*alpha),
             -2*A*((A-1)+(A+1)*np.cos(w0)),
             A*((A+1)+(A-1)*np.cos(w0)-2*np.sqrt(A)*alpha)]
        a = [(A+1)-(A-1)*np.cos(w0)+2*np.sqrt(A)*alpha,
             2*((A-1)-(A+1)*np.cos(w0)),
             (A+1)-(A-1)*np.cos(w0)-2*np.sqrt(A)*alpha]
    else:
        b = [A*((A+1)-(A-1)*np.cos(w0)+2*np.sqrt(A)*alpha),
             2*A*((A-1)-(A+1)*np.cos(w0)),
             A*((A+1)-(A-1)*np.cos(w0)-2*np.sqrt(A)*alpha)]
        a = [(A+1)+(A-1)*np.cos(w0)+2*np.sqrt(A)*alpha,
             -2*((A-1)+(A+1)*np.cos(w0)),
             (A+1)+(A-1)*np.cos(w0)-2*np.sqrt(A)*alpha]
    sos = sg.tf2sos(b, a)
    return sg.sosfilt(sos, audio, axis=0)

def _de_ess_stem(audio, sr, threshold_db=4.0):
    """Simplified band-split de-esser for vocal stem."""
    if threshold_db <= -1.5:
        return audio
    n = len(audio)
    sos_lo = _butter_sos(4000, sr, btype='low')
    sos_hi = _butter_sos(min(12000, sr//2-200), sr, btype='high')
    lo  = _apply_sos(sos_lo, audio)
    hi  = _apply_sos(sos_hi, audio)
    sib = audio - lo - hi  # complementary subtraction — guaranteed unity sum
    det = sib.mean(axis=1)
    hop = max(1, int(0.001*sr))
    n_h = (n+hop-1)//hop
    env = np.sqrt(np.mean(np.pad(det**2,(0,n_h*hop-n)).reshape(n_h,hop),axis=1)+1e-24)
    la  = max(1,int(0.0015*sr/hop))
    env = np.roll(env,-la); env[-la:]=env[-la-1]
    p90 = np.percentile(env,90)
    thresh = 10**((20*np.log10(p90+1e-12)+threshold_db)/20)
    a_att = np.exp(-1/max(1,0.001*sr/hop))
    a_rel = np.exp(-1/max(1,0.060*sr/hop))
    e = np.maximum(sg.lfilter([1-a_att],[1,-a_att],env),
                   sg.lfilter([1-a_rel],[1,-a_rel],env))
    gain_h = np.where(e>thresh,
        np.maximum(thresh*(e/(thresh+1e-24))**(1/8.0)/(e+1e-24), 10**(-12/20)), 1.0)
    gain_h = gaussian_filter1d(gain_h, sigma=2)
    gain   = np.interp(np.arange(n), np.arange(n_h)*hop+hop//2, gain_h)
    mid  = (audio[:,0]+audio[:,1])*0.5
    side = (audio[:,0]-audio[:,1])*0.5
    return np.stack([(mid+side)*gain+side*(1-gain),
                     (mid-side)*gain-side*(1-gain)], axis=1)

def _ms_widen(audio, sr, presence_gain=0.25, bass_side_mix=0.15):
    """M/S processing — bass anchor + presence widen."""
    mid  = (audio[:,0]+audio[:,1])*0.5
    side = (audio[:,0]-audio[:,1])*0.5
    sos_sub = _butter_sos(120, sr, btype='low')
    side_bass = _apply_sos(sos_sub, side[:,np.newaxis])[:,0]
    side_tight = (side-side_bass) + side_bass*bass_side_mix
    if presence_gain > 0:
        sos_pres = _butter_sos([2000,8000], sr, btype='bandpass')
        pres = _apply_sos(sos_pres, side_tight[:,np.newaxis])[:,0]
        side_tight = side_tight + pres*presence_gain
    return np.stack([mid+side_tight, mid-side_tight], axis=1)

def _normalise(audio, target_lufs=-14.0):
    """Simple RMS-based normalisation (pyloudnorm used if available)."""
    try:
        import pyloudnorm as pyln
        meter = pyln.Meter(44100)
        lufs  = meter.integrated_loudness(audio)
        if np.isfinite(lufs):
            gain = _db_to_lin(target_lufs - lufs)
            return audio * gain
    except Exception:
        pass
    rms = np.sqrt(np.mean(audio**2))
    if rms > 1e-8:
        target_rms = _db_to_lin(target_lufs + 14 - 20)
        audio = audio * (target_rms / rms)
    return audio

def _transient_boost(audio, sr, boost_db=2.5):
    """Simple transient shaper — boost fast attack content."""
    if boost_db <= 0:
        return audio
    mono = audio.mean(axis=1)
    hop  = max(1,int(0.005*sr))
    n_h  = (len(mono)+hop-1)//hop
    env_fast = np.sqrt(np.mean(np.pad(mono**2,(0,n_h*hop-len(mono))).reshape(n_h,hop),axis=1)+1e-24)
    env_slow = gaussian_filter1d(env_fast, sigma=20)
    trans    = np.maximum(0, 20*np.log10(env_fast+1e-12) - 20*np.log10(env_slow+1e-12))
    gain_h   = 1.0 + (_db_to_lin(boost_db)-1.0) * np.clip(trans/10,0,1)
    gain_h   = gaussian_filter1d(gain_h, sigma=2)
    gain     = np.interp(np.arange(len(mono)), np.arange(n_h)*hop+hop//2, gain_h)
    return audio * gain[:,np.newaxis]


# ── Per-stem mastering presets ─────────────────────────────────────────────────

STEM_DEFAULTS = {
    'vocals': {
        'enabled':        True,
        'eq_shelf_db':    1.5,    # Air shelf
        'eq_mud_db':     -2.0,    # Mud cut
        'compress':       True,
        'comp_threshold': -18.0,
        'comp_ratio':      2.0,
        'saturation_mix':  0.10,
        'presence_gain':   0.25,  # M/S widening
        'bass_side_mix':   0.15,
        'deess_threshold': 3.0,   # Medium de-essing
        'transient_db':    1.5,
    },
    'drums': {
        'enabled':        True,
        'eq_shelf_db':    0.5,
        'eq_mud_db':     -2.5,
        'compress':       True,
        'comp_threshold': -20.0,
        'comp_ratio':      3.0,
        'saturation_mix':  0.20,
        'presence_gain':   0.0,   # No M/S on drums
        'bass_side_mix':   0.5,   # Keep some drum width
        'deess_threshold': -2.0,  # Off
        'transient_db':    3.5,   # Strong transient restore
    },
    'bass': {
        'enabled':        True,
        'eq_shelf_db':    0.0,    # No air on bass
        'eq_mud_db':     -1.0,
        'compress':       True,
        'comp_threshold': -22.0,
        'comp_ratio':      3.0,
        'saturation_mix':  0.15,
        'presence_gain':   0.0,   # No M/S on bass
        'bass_side_mix':   1.0,   # Preserve all bass width
        'deess_threshold': -2.0,  # Off
        'transient_db':    1.0,
    },
    'other': {
        'enabled':        True,
        'eq_shelf_db':    1.0,
        'eq_mud_db':     -1.5,
        'compress':       True,
        'comp_threshold': -20.0,
        'comp_ratio':      2.0,
        'saturation_mix':  0.10,
        'presence_gain':   0.15,  # Light M/S
        'bass_side_mix':   0.80,  # Preserve most instrumental width
        'deess_threshold': -2.0,  # Off
        'transient_db':    1.5,
    },
}


def process_stem(audio: np.ndarray, sr: int, stem: str, settings: dict) -> np.ndarray:
    """
    Apply per-stem mastering to a single stem.
    settings: merged from STEM_DEFAULTS[stem] with any user overrides.
    """
    if not settings.get('enabled', True):
        print(f"  {stem:8s}: bypassed")
        return audio

    result = audio.copy()
    print(f"  {stem:8s}: processing...")

    # EQ
    if abs(settings.get('eq_shelf_db', 0)) > 0.05:
        result = _eq_shelf(result, sr, 10000, settings['eq_shelf_db'])
    if abs(settings.get('eq_mud_db', 0)) > 0.05:
        result = _eq_shelf(result, sr, 380, settings['eq_mud_db'])

    # M/S
    pg = settings.get('presence_gain', 0)
    bsm = settings.get('bass_side_mix', 1.0)
    if pg > 0 or bsm < 1.0:
        result = _ms_widen(result, sr, presence_gain=pg, bass_side_mix=bsm)

    # De-ess (vocals only in practice)
    dt = settings.get('deess_threshold', -2.0)
    if dt > -1.5:
        result = _de_ess_stem(result, sr, threshold_db=dt)

    # Compression
    if settings.get('compress', True):
        result = _compress(result, sr,
                           threshold_db=settings.get('comp_threshold', -18),
                           ratio=settings.get('comp_ratio', 2.0))

    # Saturation (parallel tanh)
    mix = settings.get('saturation_mix', 0.10)
    if mix > 0:
        sat = np.tanh(result * _db_to_lin(6))
        result = result * (1-mix) + sat * mix

    # Transient boost
    tb = settings.get('transient_db', 0)
    if tb > 0:
        result = _transient_boost(result, sr, boost_db=tb)

    rms_in  = _rms_db(audio)
    rms_out = _rms_db(result)
    print(f"  {stem:8s}: {rms_in:+.1f} → {rms_out:+.1f} dBRMS  "
          f"({rms_out-rms_in:+.1f} dB)")
    return result


# ── Main entry point ───────────────────────────────────────────────────────────

def stem_master(input_path: str, output_path: str,
                stem_settings: dict = None,
                model: str = 'htdemucs',
                target_lufs: float = -14.0,
                profile: str = 'streaming') -> dict:
    """
    Full stem mastering pipeline.

    stem_settings: dict of {stem_name: {setting: value}} overrides.
                   Missing stems use STEM_DEFAULTS.
    Returns: dict with per-stem stats and output path.
    """
    # Merge user settings with defaults
    settings = {}
    for stem in ['vocals', 'drums', 'bass', 'other']:
        settings[stem] = {**STEM_DEFAULTS[stem]}
        if stem_settings and stem in stem_settings:
            settings[stem].update(stem_settings[stem])

    # Separate stems
    stems = separate_stems(input_path, model=model)
    sr = stems['sr']

    # Resample to 44.1kHz if needed
    if sr != 44100:
        from scipy.signal import resample_poly
        import math
        def gcd(a,b): return a if b==0 else gcd(b,a%b)
        g = gcd(44100, sr)
        up, down = 44100//g, sr//g
        for name in ['vocals','drums','bass','other']:
            stems[name] = np.stack([
                resample_poly(stems[name][:,c], up, down)
                for c in range(2)], axis=1)
        sr = 44100
        print(f"  Resample   : stems → 44100 Hz")

    # Process each stem
    processed = {}
    for stem_name in ['vocals', 'drums', 'bass', 'other']:
        processed[stem_name] = process_stem(
            stems[stem_name], sr, stem_name, settings[stem_name])

    # Recombine
    print("  Recombine  : summing stems...")
    mix = sum(processed.values())

    # Peak normalise before LUFS normalise to prevent clipping
    peak = np.max(np.abs(mix))
    if peak > 0.98:
        mix = mix * (0.98 / peak)

    # Profile adjustment (local = warmer)
    if profile == 'local':
        sos_shelf = _butter_sos(10000, sr, btype='high')
        hi  = sg.sosfilt(sos_shelf, mix, axis=0)
        lo  = mix - hi
        mix = lo + hi * _db_to_lin(-1.5)
        target_lufs = -16.0

    # LUFS normalise
    mix = _normalise(mix, target_lufs=target_lufs)

    # True peak limit
    peak = np.max(np.abs(mix))
    ceil = _db_to_lin(-1.0 if profile=='streaming' else -2.0)
    if peak > ceil:
        mix = mix * (ceil / peak)

    # Export
    sf.write(output_path, mix, sr, subtype='PCM_16')
    out_rms = _rms_db(mix)
    print(f"  Export     : {output_path}  ({_rms_db(mix):+.1f} dBRMS)")

    return {
        'status': 'ok',
        'sr': sr,
        'stems': {k: {'rms_in': _rms_db(stems[k]),
                       'rms_out': _rms_db(processed[k]),
                       'enabled': settings[k]['enabled']}
                  for k in ['vocals','drums','bass','other']},
        'output_rms': out_rms,
    }


if __name__ == '__main__':
    import sys, json
    if len(sys.argv) < 3:
        print("Usage: python stem_master.py input.wav output.wav")
        sys.exit(1)
    result = stem_master(sys.argv[1], sys.argv[2])
    print(json.dumps(result, indent=2))
