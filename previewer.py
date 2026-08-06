"""
previewer.py — Preview variant generator for StreamMaster.

Generates four 30-second clip variants from a track:
  - raw:       LUFS-normalised only, no processing
  - optimised: full chain with analyser-recommended settings
  - vocal:     presence-forward variant (more width, tighter de-ess)
  - character: minimal processing — preserves Suno's original sonic character

Also provides:
  - find_preview_window(): finds the most representative 30s section
  - extract_clip():        extracts a 30s clip at a given start time
  - waveform_data():       returns downsampled amplitude array for Canvas rendering
"""

import numpy as np
import soundfile as sf
from pathlib import Path
from scipy import signal as sg
from scipy.ndimage import gaussian_filter1d


CLIP_DURATION = 30   # seconds
WAVEFORM_POINTS = 1200  # resolution for Canvas render


# ── Helpers ───────────────────────────────────────────────────────────────────

def _rmsdb(x):
    return 20.0 * np.log10(np.sqrt(np.mean(x**2)) + 1e-12)

def _db_to_lin(db):
    return 10 ** (db / 20.0)

def _normalise_to_lufs(audio, sr, target=-14.0):
    """Simple RMS-based normalisation with pyloudnorm fallback."""
    try:
        import pyloudnorm as pyln
        meter = pyln.Meter(sr)
        lufs  = meter.integrated_loudness(audio)
        if np.isfinite(lufs):
            return audio * _db_to_lin(target - lufs)
    except Exception:
        pass
    rms = np.sqrt(np.mean(audio**2))
    if rms > 1e-8:
        target_rms = _db_to_lin(target + 14 - 20)
        return audio * (target_rms / rms)
    return audio

def _true_peak_limit(audio, ceil_db=-1.0):
    peak = np.max(np.abs(audio))
    ceil = _db_to_lin(ceil_db)
    if peak > ceil:
        audio = audio * (ceil / peak)
    return audio


# ── Window selection ──────────────────────────────────────────────────────────

def find_preview_window(audio: np.ndarray, sr: int,
                        duration: float = CLIP_DURATION) -> float:
    """
    Find the most representative start time for the preview clip.

    Maximises vocal activity (300-3kHz) combined with full-mix energy,
    avoiding the first and last 15% of the track (intros/outros).

    Returns: start time in seconds
    """
    n          = len(audio)
    track_dur  = n / sr
    clip_samps = int(duration * sr)

    # Guard: track shorter than clip
    if n <= clip_samps:
        return 0.0

    # Exclusion zone: first and last 15%
    margin = int(track_dur * 0.15 * sr)
    margin = min(margin, n // 4)

    mono     = audio.mean(axis=1)

    # Vocal band energy (300-3kHz)
    sos_vox = sg.butter(4, [300/(sr/2), min(3000,sr//2-200)/(sr/2)],
                        btype='bandpass', output='sos')
    vox     = sg.sosfilt(sos_vox, mono)

    # Score every possible start position (1-second hops)
    hop    = sr  # 1-second hops
    scores = []
    pos    = margin
    while pos + clip_samps <= n - margin:
        seg_vox  = vox[pos:pos+clip_samps]
        seg_full = mono[pos:pos+clip_samps]
        score    = _rmsdb(seg_vox) * 0.6 + _rmsdb(seg_full) * 0.4
        scores.append((score, pos))
        pos += hop

    if not scores:
        return 0.0

    best_pos = max(scores, key=lambda x: x[0])[1]
    return round(best_pos / sr, 2)


# ── Clip extraction ───────────────────────────────────────────────────────────

def extract_clip(audio: np.ndarray, sr: int,
                 start_s: float, duration: float = CLIP_DURATION) -> np.ndarray:
    """Extract a clip from audio at start_s with crossfaded edges."""
    start = int(start_s * sr)
    end   = min(len(audio), start + int(duration * sr))
    clip  = audio[start:end].copy()

    # 50ms fade in/out to avoid clicks at clip edges
    fade = min(int(0.05 * sr), len(clip) // 4)
    if fade > 0:
        t = np.linspace(0, 1, fade)
        clip[:fade]  *= t[:, np.newaxis]
        clip[-fade:] *= (1 - t)[:, np.newaxis]

    return clip


# ── Waveform data ─────────────────────────────────────────────────────────────

def waveform_data(audio: np.ndarray, sr: int,
                  points: int = WAVEFORM_POINTS) -> list:
    """
    Return a downsampled amplitude envelope for Canvas rendering.
    Returns list of floats in [0, 1].
    """
    mono    = np.abs(audio.mean(axis=1))
    hop     = max(1, len(mono) // points)
    n_hops  = len(mono) // hop
    env     = np.array([mono[i*hop:(i+1)*hop].max() for i in range(n_hops)])
    # Smooth slightly
    env     = gaussian_filter1d(env, sigma=2)
    peak    = env.max()
    if peak > 1e-6:
        env = env / peak
    return env.tolist()


# ── Variant generation ────────────────────────────────────────────────────────

def generate_variants(input_path: str, recommended: dict,
                      output_dir: str,
                      start_s: float = None,
                      clip_duration: float = CLIP_DURATION) -> dict:
    """
    Generate four preview clip variants.

    Returns dict with:
      - variant clips saved to output_dir
      - waveform data for the full track
      - auto-selected window start time
      - clip duration
    """
    import sys, os
    sys.path.insert(0, str(Path(__file__).parent))
    from spotify_master import master

    audio, sr = sf.read(input_path, always_2d=True)
    audio     = audio.astype(np.float64)
    track_dur = len(audio) / sr
    out_dir   = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Auto-select window if not provided
    if start_s is None:
        start_s = find_preview_window(audio, sr, duration=clip_duration)

    # Waveform data for the full track
    wf_data = waveform_data(audio, sr)

    # Build variant settings
    rec = recommended or {}

    # Helper to run master() on the full file and return processed audio + sr
    def _run_master(tmp_out, **kwargs):
        master(input_path, str(tmp_out), **kwargs)
        processed, proc_sr = sf.read(str(tmp_out), always_2d=True)
        return processed.astype(np.float64), proc_sr

    tmp_wav  = out_dir / '_tmp_variant.wav'
    variants = {}

    # master() always resamples to 44100 Hz — use that rate for all writes
    # We discover it from the first processed file rather than assuming
    proc_sr = None  # discovered after first _run_master call

    # ── 1. Raw — LUFS normalise only ─────────────────────────────────────────
    # Raw uses the input sr since we're not running the chain
    # but we resample to 44100 to match the processed variants
    from scipy.signal import resample_poly
    import math
    def _gcd(a, b): return a if b == 0 else _gcd(b, a % b)

    raw_audio = audio.copy()
    raw_sr    = sr
    if raw_sr != 44100:
        g = _gcd(44100, raw_sr)
        up, down = 44100 // g, raw_sr // g
        raw_audio = np.stack([
            resample_poly(raw_audio[:, c], up, down)
            for c in range(raw_audio.shape[1])], axis=1)
        raw_sr = 44100

    print("  Preview    : generating Raw variant...")
    raw = _normalise_to_lufs(raw_audio, raw_sr, target=-14.0)
    raw = _true_peak_limit(raw)
    sf.write(str(out_dir / 'full_raw.wav'), raw, raw_sr, subtype='PCM_16')
    clip_raw = extract_clip(raw, raw_sr, start_s, clip_duration)
    sf.write(str(out_dir / 'preview_raw.wav'), clip_raw, raw_sr, subtype='PCM_16')
    variants['raw'] = {'file': 'preview_raw.wav', 'label': 'Raw',
                       'description': 'Unprocessed — LUFS normalised only'}

    # ── 2. Optimised — full chain, analyser-recommended settings ─────────────
    print("  Preview    : generating Optimised variant...")
    full_opt, proc_sr = _run_master(tmp_wav,
        presence_gain    = rec.get('presence_gain',    0.25),
        deess_threshold  = rec.get('deess_threshold',  -2.0),
        vocal_boost_db   = rec.get('vocal_boost_db',   0.0),
        macro_target_db  = rec.get('macro_target_db',  0.0),
        eq_shelf_db      = rec.get('eq_shelf_db',      1.5),
        eq_mud_db        = rec.get('eq_mud_db',       -2.0),
        bass_side_mix    = rec.get('bass_side_mix',    0.15),
        transient_boost  = rec.get('transient_boost',  2.5),
        comp_threshold   = rec.get('comp_threshold',  -18.0),
        comp_ratio       = rec.get('comp_ratio',       2.0),
        sat_mix          = rec.get('sat_mix',          0.15),
        hishelf_threshold= rec.get('hishelf_threshold',-99.0),
        profile='streaming',
    )
    sf.write(str(out_dir / 'full_optimised.wav'), full_opt, proc_sr, subtype='PCM_16')
    clip_opt = extract_clip(full_opt, proc_sr, start_s, clip_duration)
    sf.write(str(out_dir / 'preview_optimised.wav'), clip_opt, proc_sr, subtype='PCM_16')
    variants['optimised'] = {'file': 'preview_optimised.wav', 'label': 'Optimised',
                              'description': 'Full chain — analyser-recommended settings'}

    # ── 3. Vocal forward — more presence, tighter de-ess ────────────────────
    print("  Preview    : generating Vocal Forward variant...")
    full_voc, _ = _run_master(tmp_wav,
        presence_gain    = min(0.5, rec.get('presence_gain', 0.25) + 0.15),
        deess_threshold  = max(rec.get('deess_threshold', 3.0), 3.0),
        vocal_boost_db   = rec.get('vocal_boost_db', 0.0),
        macro_target_db  = rec.get('macro_target_db', 0.0),
        eq_shelf_db      = min(3.0, rec.get('eq_shelf_db', 1.5) + 0.5),
        eq_mud_db        = min(-1.0, rec.get('eq_mud_db', -2.0) - 0.5),
        bass_side_mix    = rec.get('bass_side_mix', 0.15),
        transient_boost  = rec.get('transient_boost', 2.5),
        comp_threshold   = rec.get('comp_threshold', -18.0),
        comp_ratio       = rec.get('comp_ratio', 2.0),
        sat_mix          = rec.get('sat_mix', 0.15),
        hishelf_threshold= rec.get('hishelf_threshold', -99.0),
        profile='streaming',
    )
    sf.write(str(out_dir / 'full_vocal.wav'), full_voc, proc_sr, subtype='PCM_16')
    clip_voc = extract_clip(full_voc, proc_sr, start_s, clip_duration)
    sf.write(str(out_dir / 'preview_vocal.wav'), clip_voc, proc_sr, subtype='PCM_16')
    variants['vocal'] = {'file': 'preview_vocal.wav', 'label': 'Vocal Forward',
                          'description': 'More presence and width — vocal sits further forward'}

    # ── 4. Preserve character — minimal processing ────────────────────────────
    print("  Preview    : generating Preserve Character variant...")
    full_char, _ = _run_master(tmp_wav,
        presence_gain    = 0.0,
        deess_threshold  = -2.0,
        vocal_boost_db   = 0.0,
        macro_target_db  = 0.0,
        eq_shelf_db      = 0.0,
        eq_mud_db        = 0.0,
        air_blend        = 0.0,
        dehaze_depth     = 0.0,
        bass_side_mix    = 1.0,
        sat_mix          = 0.0,
        transient_boost  = 0.0,
        comp_threshold   = -6.0,
        hishelf_threshold= -99.0,
        profile='streaming',
    )
    sf.write(str(out_dir / 'full_character.wav'), full_char, proc_sr, subtype='PCM_16')
    clip_char = extract_clip(full_char, proc_sr, start_s, clip_duration)
    sf.write(str(out_dir / 'preview_character.wav'), clip_char, proc_sr, subtype='PCM_16')
    variants['character'] = {'file': 'preview_character.wav',
                              'label': 'Preserve Character',
                              'description': 'Minimal processing — Suno\'s original sound, streaming-ready'}

    # Cleanup tmp
    if tmp_wav.exists():
        tmp_wav.unlink()

    return {
        'variants':       variants,
        'waveform':       wf_data,
        'window_start':   start_s,
        'window_end':     min(start_s + clip_duration, track_dur),
        'clip_duration':  clip_duration,
        'track_duration': round(track_dur, 2),
    }


def regenerate_clips(input_path: str, recommended: dict,
                     output_dir: str, start_s: float,
                     clip_duration: float = CLIP_DURATION) -> dict:
    """
    Re-extract clips from already-processed variants at a new window position.
    Much faster than generate_variants() — no mastering chain re-run.
    Falls back to full generation if processed files don't exist.
    """
    out_dir   = Path(output_dir)
    audio, sr = sf.read(input_path, always_2d=True)
    track_dur = len(audio) / sr

    variant_files = {
        'raw':       'preview_raw.wav',
        'optimised': 'preview_optimised.wav',
        'vocal':     'preview_vocal.wav',
        'character': 'preview_character.wav',
    }

    # Check all processed full-track files exist
    # (we save full processed tracks during generation for fast regeneration)
    full_files = {
        'raw':       out_dir / 'full_raw.wav',
        'optimised': out_dir / 'full_optimised.wav',
        'vocal':     out_dir / 'full_vocal.wav',
        'character': out_dir / 'full_character.wav',
    }

    all_exist = all(p.exists() for p in full_files.values())
    if not all_exist:
        # Fall back to full regeneration
        return generate_variants(input_path, recommended, output_dir,
                                 start_s=start_s, clip_duration=clip_duration)

    variants = {}
    labels = {
        'raw':       ('Raw',               'Unprocessed — LUFS normalised only'),
        'optimised': ('Optimised',         'Full chain — analyser-recommended settings'),
        'vocal':     ('Vocal Forward',     'More presence and width — vocal sits further forward'),
        'character': ('Preserve Character','Minimal processing — Suno\'s original sound, streaming-ready'),
    }

    for key, full_path in full_files.items():
        full_audio, full_sr = sf.read(str(full_path), always_2d=True)
        full_audio          = full_audio.astype(np.float64)
        clip                = extract_clip(full_audio, full_sr, start_s, clip_duration)
        clip_path           = out_dir / variant_files[key]
        sf.write(str(clip_path), clip, full_sr, subtype='PCM_16')
        label, desc = labels[key]
        variants[key] = {'file': variant_files[key], 'label': label, 'description': desc}

    wf_data = waveform_data(audio, sr)
    return {
        'variants':       variants,
        'waveform':       wf_data,
        'window_start':   start_s,
        'window_end':     min(start_s + clip_duration, track_dur),
        'clip_duration':  clip_duration,
        'track_duration': round(track_dur, 2),
    }
