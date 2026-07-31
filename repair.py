"""
repair.py — Suno generation boundary corruption repair

Detects and repairs phase corruption at Suno generation boundaries using
sub-bass L/R correlation analysis. Two strategies available:
  1. Phase repair (scipy only, always available)
  2. Stem repair (requires: pip install demucs)
"""

import numpy as np
from scipy import signal
from scipy.ndimage import gaussian_filter1d
from pathlib import Path
import soundfile as sf
import tempfile, os


def _rms_db(x):
    return 20.0 * np.log10(np.sqrt(np.mean(x**2)) + 1e-12)

def _cosine_fade(n, direction='in'):
    t = np.linspace(0, np.pi, n)
    return (1 - np.cos(t)) / 2 if direction == 'in' else (1 + np.cos(t)) / 2


def find_corruption_zones(audio, sr, threshold=0.45, min_dur_ms=80.0, context_ms=50.0):
    if audio.shape[1] == 1:
        return []
    n   = len(audio)
    hop = int(0.010 * sr)
    n_h = (n - hop) // hop
    sos = signal.butter(4, [20/(sr/2), min(200, sr//2-100)/(sr/2)], btype='bandpass', output='sos')
    sub = signal.sosfilt(sos, audio, axis=0)
    corrs, rmss = [], []
    for i in range(n_h):
        seg  = sub[i*hop:(i+1)*hop]
        full = audio[i*hop:(i+1)*hop]
        c = np.corrcoef(seg[:,0], seg[:,1])[0,1]
        corrs.append(float(c) if np.isfinite(c) else 0.0)
        rmss.append(_rms_db(full))
    corrs = np.array(corrs); rmss = np.array(rmss)
    times = np.arange(n_h) * hop / sr
    scores   = np.where((corrs < -0.4) & (rmss > -32), np.abs(corrs), 0.0)
    smoothed = gaussian_filter1d(scores, sigma=2)
    min_frames = max(1, int(min_dur_ms * 0.001 * sr / hop))
    ctx_s = context_ms * 0.001
    above = smoothed > threshold
    raw_zones = []
    in_zone, z_start = False, 0
    for i in range(n_h):
        if above[i] and not in_zone:
            in_zone = True; z_start = i
        elif not above[i] and in_zone:
            in_zone = False
            if i - z_start >= min_frames:
                raw_zones.append((times[z_start], times[i]))
    merged = []
    for s, e in raw_zones:
        s2 = max(0, s - ctx_s); e2 = min(n/sr, e + ctx_s)
        if merged and s2 <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e2))
        else:
            merged.append((s2, e2))
    return merged


def _repair_zone_phase(audio, sr, start_s, end_s, fade_ms=30.0):
    result = audio.copy()
    n = len(audio)
    s = int(start_s * sr); e = int(end_s * sr)
    fade = int(fade_ms * 0.001 * sr)
    s = max(fade, s); e = min(n - fade, e)
    if e <= s:
        return result
    zone_len = e - s
    mid  = (audio[:,0] + audio[:,1]) * 0.5
    side = (audio[:,0] - audio[:,1]) * 0.5
    ctx = int(0.200 * sr)
    pre_env  = np.mean(np.abs(side[max(0,s-ctx):s]))
    post_env = np.mean(np.abs(side[e:min(n,e+ctx)]))
    rng = np.random.default_rng(seed=42)
    noise = rng.normal(0, 1, zone_len)
    sos = signal.butter(2, [200/(sr/2), min(8000,sr//2-200)/(sr/2)], btype='bandpass', output='sos')
    noise_f = signal.sosfilt(sos, noise)
    t_interp = np.linspace(0, 1, zone_len)
    target_env = pre_env * (1-t_interp) + post_env * t_interp
    noise_rms  = np.sqrt(np.mean(noise_f**2)) + 1e-12
    side_synth = noise_f * (target_env / noise_rms) * 0.3
    fi = _cosine_fade(fade,'in'); fo = _cosine_fade(fade,'out')
    side_r = side.copy()
    side_r[s-fade:s] = side[s-fade:s]*fo + side_synth[:fade]*fi
    side_r[s:e]      = side_synth
    side_r[e:e+fade] = side_synth[-fade:]*fo + side[e:e+fade]*fi
    result[:,0] = mid + side_r
    result[:,1] = mid - side_r
    return result


def repair_phase(audio, sr, zones=None, fade_ms=30.0):
    if zones is None:
        zones = find_corruption_zones(audio, sr)
    if not zones:
        print("  Repair     : no corruption zones found")
        return audio.copy(), []
    result = audio.copy(); report = []
    for i, (s, e) in enumerate(zones):
        print(f"  Repair     : zone {i+1}/{len(zones)}  "
              f"{int(s//60)}:{s%60:05.2f}s → {int(e//60)}:{e%60:05.2f}s  phase repair")
        result = _repair_zone_phase(result, sr, s, e, fade_ms=fade_ms)
        report.append({"zone":i+1,"start_s":round(s,2),"end_s":round(e,2),
                        "duration_ms":round((e-s)*1000),"method":"phase",
                        "time_display":f"{int(s//60)}:{s%60:05.2f}"})
    return result, report


def _demucs_available():
    try:
        import demucs; return True
    except ImportError:
        return False


def repair_stems(input_path, output_path, zones=None, model='htdemucs'):
    if not _demucs_available():
        raise ImportError("Demucs not installed. Run: pip install demucs")
    import demucs.separate
    audio, sr = sf.read(input_path, always_2d=True)
    audio = audio.astype(np.float64)
    if zones is None:
        zones = find_corruption_zones(audio, sr)
    if not zones:
        print("  Repair     : no corruption zones found")
        sf.write(output_path, audio, sr, subtype='PCM_16')
        return audio, []
    print(f"  Repair     : separating stems with {model}...")
    tmp_dir = tempfile.mkdtemp()
    tmp_in  = os.path.join(tmp_dir, 'input.wav')
    sf.write(tmp_in, audio, sr, subtype='PCM_24')
    demucs.separate.main(['--name', model, '--out', tmp_dir, '--two-stems', 'vocals', tmp_in])
    stem_dir = Path(tmp_dir) / model / 'input'
    vocals, sr_v = sf.read(str(stem_dir/'vocals.wav'), always_2d=True)
    other,  sr_o = sf.read(str(stem_dir/'no_vocals.wav'), always_2d=True)
    vocals = vocals.astype(np.float64); other = other.astype(np.float64)
    report = []
    for i, (s, e) in enumerate(zones):
        print(f"  Repair     : zone {i+1}/{len(zones)}  "
              f"{int(s//60)}:{s%60:05.2f}s → {int(e//60)}:{e%60:05.2f}s  stem repair")
        vocals = _repair_zone_phase(vocals, sr_v, s, e, fade_ms=25.0)
        other  = _repair_zone_phase(other,  sr_o, s, e, fade_ms=25.0)
        report.append({"zone":i+1,"start_s":round(s,2),"end_s":round(e,2),
                        "duration_ms":round((e-s)*1000),"method":"stem",
                        "time_display":f"{int(s//60)}:{s%60:05.2f}"})
    result = vocals + other
    peak = np.max(np.abs(result))
    if peak > 0.98: result = result * (0.98/peak)
    sf.write(output_path, result, sr, subtype='PCM_16')
    import shutil; shutil.rmtree(tmp_dir, ignore_errors=True)
    return result, report


def repair_boundaries(input_path, output_path, method='auto'):
    audio, sr = sf.read(input_path, always_2d=True)
    audio = audio.astype(np.float64)
    print("  Repair     : scanning for boundary corruption...")
    zones = find_corruption_zones(audio, sr)
    print(f"  Repair     : found {len(zones)} zone(s)")
    if method == 'auto':
        method = 'stem' if _demucs_available() else 'phase'
    if method == 'stem':
        result, report = repair_stems(input_path, output_path, zones=zones)
    else:
        result, report = repair_phase(audio, sr, zones=zones)
        sf.write(output_path, result, sr, subtype='PCM_16')
    return output_path, report


if __name__ == '__main__':
    import sys, json
    if len(sys.argv) < 3:
        print("Usage: python repair.py input.wav output.wav [phase|stem|auto]")
        sys.exit(1)
    method = sys.argv[3] if len(sys.argv) > 3 else 'auto'
    out, rep = repair_boundaries(sys.argv[1], sys.argv[2], method=method)
    print(f"\nRepaired {len(rep)} zone(s) → {out}")
    print(json.dumps(rep, indent=2))
