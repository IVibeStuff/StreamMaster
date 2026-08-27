#!/usr/bin/env python3
"""
server.py — Local bridge server for the StreamMaster UI.

Run once:  python server.py
Browser opens automatically at http://localhost:5051

Requires: pip install flask flask-cors pyloudnorm soundfile scipy numpy
"""

import sys
import time as _time
import tempfile
import webbrowser
import threading
import io
import numpy as np
from pathlib import Path
from flask import Flask, request, jsonify, send_file, Response
from flask_cors import CORS

sys.path.insert(0, str(Path(__file__).parent))
from spotify_master import master
from splice import splice
from heal import heal
from levelbridge import level_bridge
from dejinx import dejinx
from mastering_extras import reference_match
from analyser import analyse
from qc import qc_check
from repair import repair_boundaries, find_corruption_zones, _demucs_available
from stem_master import stem_master, STEM_DEFAULTS
from previewer import generate_variants, regenerate_clips
from history import add_entry, get_grouped, clear_all
from updater import check_for_updates_background, get_update_state, apply_update

app = Flask(__name__)
CORS(app)

UPLOAD_DIR = Path(tempfile.gettempdir()) / "spotify_master"
UPLOAD_DIR.mkdir(exist_ok=True)

# ── Heartbeat shutdown ─────────────────────────────────────────────────────
_last_heartbeat    = _time.time()
_HEARTBEAT_TIMEOUT = 15   # seconds without heartbeat before shutdown
_heartbeat_active  = False  # only monitor once first heartbeat arrives

# ── Console log capture ───────────────────────────────────────────────────────
import builtins
_log_lines  = []
_log_lock   = threading.Lock()
_orig_print = builtins.print

def _capturing_print(*args, **kwargs):
    line = " ".join(str(a) for a in args)
    with _log_lock:
        _log_lines.append(line)
    _orig_print(*args, **kwargs)

builtins.print = _capturing_print

def _reset_log():
    with _log_lock:
        _log_lines.clear()

@app.route("/log")
def log_route():
    with _log_lock:
        return jsonify({"lines": list(_log_lines)})

# Serve the UI
HTML_PATH = Path(__file__).parent / "index.html"

@app.route("/")
def index():
    return send_file(str(HTML_PATH))


@app.route("/master", methods=["POST"])
def master_route():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    f = request.files["file"]
    if not f.filename.lower().endswith(".wav"):
        return jsonify({"error": "Only WAV files are supported"}), 400

    _reset_log()

    original_stem   = Path(f.filename).stem
    presence_gain   = float(request.form.get("presence_gain",    0.25))
    deess_slider    = float(request.form.get("deess_threshold",  -2.0))
    vocal_boost_db  = float(request.form.get("vocal_boost_db",   0.0))
    macro_target_db = float(request.form.get("macro_target_db",  0.0))
    profile         = request.form.get("profile", "streaming")  # 'streaming' or 'local'

    # De-esser inversion: slider -2=Off, 0-7=aggressiveness → threshold_db
    if deess_slider <= -1.5:
        deess_threshold = -2.0
    else:
        deess_threshold = 8.0 - deess_slider

    # Expert params (sent only when expert panel is unlocked)
    eq_shelf_db    = float(request.form.get("eq_shelf_db",     1.5))
    eq_mud_db      = float(request.form.get("eq_mud_db",      -2.0))
    air_blend      = float(request.form.get("air_blend",       0.018))
    dehaze_depth   = float(request.form.get("dehaze_depth",    0.04))
    sat_drive_db   = float(request.form.get("sat_drive_db",    6.0))
    sat_mix        = float(request.form.get("sat_mix",         0.15))
    comp_threshold = float(request.form.get("comp_threshold", -18.0))
    comp_ratio     = float(request.form.get("comp_ratio",      2.0))
    transient_boost= float(request.form.get("transient_boost", 2.5))
    dyneq_threshold= float(request.form.get("dyneq_threshold",-24.0))
    dyneq_max_cut  = float(request.form.get("dyneq_max_cut",   3.0))
    bass_side_mix      = float(request.form.get("bass_side_mix",      0.15))
    hishelf_threshold  = float(request.form.get("hishelf_threshold", -99.0))

    gain_db      = round(20 * np.log10(presence_gain + 1), 1)
    profile_tag  = '_local' if profile == 'local' else '_streaming'
    output_name  = (f"{original_stem}_remaster"
                    f"_w{gain_db}dB"
                    f"_d{int(deess_slider)}"
                    f"_v{vocal_boost_db:.0f}"
                    f"_m{macro_target_db:.1f}"
                    f"{profile_tag}.wav")

    input_path  = UPLOAD_DIR / "input.wav"
    output_path = UPLOAD_DIR / output_name
    f.save(str(input_path))

    try:
        master(str(input_path), str(output_path),
               presence_gain=presence_gain,
               deess_threshold=deess_threshold,
               vocal_boost_db=vocal_boost_db,
               macro_target_db=macro_target_db,
               eq_shelf_db=eq_shelf_db,
               eq_mud_db=eq_mud_db,
               air_blend=air_blend,
               dehaze_depth=dehaze_depth,
               sat_drive_db=sat_drive_db,
               sat_mix=sat_mix,
               comp_threshold=comp_threshold,
               comp_ratio=comp_ratio,
               transient_boost=transient_boost,
               dyneq_threshold=dyneq_threshold,
               dyneq_max_cut=dyneq_max_cut,
               bass_side_mix=bass_side_mix,
               hishelf_threshold=hishelf_threshold,
               profile=profile)
        qc = qc_check(str(output_path))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # Record to history
    try:
        settings_record = dict(
            presence_gain=presence_gain, deess_threshold=deess_threshold,
            vocal_boost_db=vocal_boost_db, macro_target_db=macro_target_db,
            eq_shelf_db=eq_shelf_db, eq_mud_db=eq_mud_db,
            air_blend=air_blend, dehaze_depth=dehaze_depth,
            sat_drive_db=sat_drive_db, sat_mix=sat_mix,
            comp_threshold=comp_threshold, comp_ratio=comp_ratio,
            transient_boost=transient_boost, dyneq_max_cut=dyneq_max_cut,
            bass_side_mix=bass_side_mix, hishelf_threshold=hishelf_threshold,
            profile=profile,
        )
        add_entry(
            source_file  = f.filename,
            output_files = [output_name],
            settings     = settings_record,
            qc           = qc,
        )
    except Exception:
        pass  # never fail a master export due to history write error

    return jsonify({"status": "ok", "output": output_name, "qc": qc})


@app.route("/splice", methods=["POST"])
def splice_route():
    if "master" not in request.files or "replacement" not in request.files:
        return jsonify({"error": "Both 'master' and 'replacement' files are required"}), 400

    m_file = request.files["master"]
    r_file = request.files["replacement"]

    for f in [m_file, r_file]:
        if not f.filename.lower().endswith(".wav"):
            return jsonify({"error": "Only WAV files are supported"}), 400

    try:
        in_time      = float(request.form.get("in_time", 0))
        out_time     = float(request.form.get("out_time", 0))
        crossfade_ms = float(request.form.get("crossfade_ms", 80))
    except ValueError:
        return jsonify({"error": "in_time, out_time, and crossfade_ms must be numbers"}), 400

    master_stem = Path(m_file.filename).stem
    output_name = f"{master_stem}_spliced.wav"

    master_path  = UPLOAD_DIR / "splice_master.wav"
    repl_path    = UPLOAD_DIR / "splice_repl.wav"
    output_path  = UPLOAD_DIR / output_name

    m_file.save(str(master_path))
    r_file.save(str(repl_path))

    try:
        splice(str(master_path), str(repl_path),
               in_time, out_time, crossfade_ms, str(output_path))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "ok", "output": output_name})


@app.route("/analyse", methods=["POST"])
def analyse_route():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    f = request.files["file"]
    if not f.filename.lower().endswith(".wav"):
        return jsonify({"error": "Only WAV files supported"}), 400
    original_name = f.filename
    input_path = UPLOAD_DIR / "analyse_input.wav"
    f.save(str(input_path))
    try:
        result = analyse(str(input_path))
        # Override the filename in the result with the original name
        result['file'] = original_name
        return jsonify(result)
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500


@app.route("/refmatch", methods=["POST"])
def refmatch_route():
    if "target" not in request.files or "reference" not in request.files:
        return jsonify({"error": "Both 'target' and 'reference' files required"}), 400
    t_file = request.files["target"]
    r_file = request.files["reference"]
    for f in [t_file, r_file]:
        if not f.filename.lower().endswith(".wav"):
            return jsonify({"error": "Only WAV files supported"}), 400

    stem        = Path(t_file.filename).stem
    output_name = f"{stem}_refmatched.wav"
    t_path      = UPLOAD_DIR / "refmatch_target.wav"
    r_path      = UPLOAD_DIR / "refmatch_reference.wav"
    o_path      = UPLOAD_DIR / output_name
    t_file.save(str(t_path))
    r_file.save(str(r_path))
    try:
        reference_match(str(t_path), str(r_path), str(o_path))
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"status": "ok", "output": output_name})


@app.route("/dejinx", methods=["POST"])
def dejinx_route():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    f = request.files["file"]
    if not f.filename.lower().endswith(".wav"):
        return jsonify({"error": "Only WAV files are supported"}), 400
    try:
        threshold = float(request.form.get("threshold", 10.0))
        min_dur   = float(request.form.get("min_dur",   80.0))
        max_dur   = float(request.form.get("max_dur",  300.0))
    except ValueError:
        return jsonify({"error": "threshold, min_dur, max_dur must be numbers"}), 400

    original_stem = Path(f.filename).stem
    output_name   = f"{original_stem}_dejinxed.wav"
    input_path    = UPLOAD_DIR / "dejinx_input.wav"
    output_path   = UPLOAD_DIR / output_name
    f.save(str(input_path))

    # Capture repair events from the log
    _reset_log()
    try:
        dejinx(str(input_path), str(output_path), threshold, min_dur, max_dur)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # Parse repair events from captured log lines
    import re
    repairs = []
    with _log_lock:
        for line in _log_lines:
            # "  Repairing 0:18.31  dur=120ms  drop=14.8dB  (-30.3→-15.5 dBRMS)"
            m = re.search(r'Repairing\s+(\d+):(\d+\.\d+)\s+dur=(\d+)ms\s+drop=([\d.]+)dB', line)
            if m:
                mins, secs, dur_ms, drop_db = m.group(1), m.group(2), m.group(3), m.group(4)
                repairs.append({
                    "time_display": f"{mins}:{float(secs):05.2f}",
                    "time_s": int(mins)*60 + float(secs),
                    "duration_ms": int(dur_ms),
                    "drop_db": float(drop_db)
                })

    return jsonify({"status": "ok", "output": output_name, "repairs": repairs})


@app.route("/preview", methods=["POST"])
def preview_route():
    """
    Generate four preview clip variants, streaming progress via SSE.
    Each variant emits a JSON event as it completes so the UI can
    show cards becoming playable one by one rather than all at once.
    """
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400
    f = request.files["file"]
    if not f.filename.lower().endswith(".wav"):
        return jsonify({"error": "WAV only"}), 400

    import json as _json
    recommended = {}
    if "recommended" in request.form:
        try:
            recommended = _json.loads(request.form["recommended"])
        except Exception:
            pass

    input_path = UPLOAD_DIR / "preview_input.wav"
    f.save(str(input_path))

    preview_dir = UPLOAD_DIR / "previews"
    preview_dir.mkdir(exist_ok=True)

    # Clear all previous preview files
    for old_file in preview_dir.glob("*.wav"):
        try: old_file.unlink()
        except Exception: pass

    def generate():
        """Generator that yields SSE events as each variant completes."""
        import soundfile as sf
        import numpy as np
        from previewer import (find_preview_window, extract_clip,
                               waveform_data, _normalise_to_lufs,
                               _true_peak_limit, CLIP_DURATION)
        from spotify_master import master as run_master

        audio, sr = sf.read(str(input_path), always_2d=True)
        audio     = audio.astype(np.float64)
        track_dur = len(audio) / sr

        # Auto window
        start_s = find_preview_window(audio, sr, CLIP_DURATION)

        # Waveform data
        wf = waveform_data(audio, sr)

        # Emit initial metadata
        meta = _json.dumps({
            "type":           "meta",
            "waveform":       wf,
            "window_start":   start_s,
            "window_end":     min(start_s + CLIP_DURATION, track_dur),
            "clip_duration":  CLIP_DURATION,
            "track_duration": round(track_dur, 2),
        })
        yield f"data: {meta}\n\n"

        rec      = recommended
        tmp_wav  = preview_dir / "_tmp.wav"
        proc_sr  = 44100

        def _run(profile, **kwargs):
            run_master(str(input_path), str(tmp_wav), profile=profile, **kwargs)
            a, s = sf.read(str(tmp_wav), always_2d=True)
            return a.astype(np.float64), s

        # Resample raw to 44100
        raw_audio = audio.copy()
        if sr != 44100:
            from scipy.signal import resample_poly
            import math
            def gcd(a,b): return a if b==0 else gcd(b,a%b)
            g = gcd(44100, sr)
            up, dn = 44100//g, sr//g
            raw_audio = np.stack([
                resample_poly(raw_audio[:,c], up, dn)
                for c in range(raw_audio.shape[1])], axis=1)

        VARIANTS = [
            ("raw", "Raw", "Unprocessed — LUFS normalised only",
             None),
            ("optimised", "Optimised", "Full chain — analyser-recommended settings",
             dict(presence_gain=rec.get('presence_gain',0.25),
                  deess_threshold=rec.get('deess_threshold',-2.0),
                  vocal_boost_db=rec.get('vocal_boost_db',0.0),
                  macro_target_db=rec.get('macro_target_db',0.0),
                  eq_shelf_db=rec.get('eq_shelf_db',1.5),
                  eq_mud_db=rec.get('eq_mud_db',-2.0),
                  bass_side_mix=rec.get('bass_side_mix',0.15),
                  transient_boost=rec.get('transient_boost',2.5),
                  comp_threshold=rec.get('comp_threshold',-18.0),
                  comp_ratio=rec.get('comp_ratio',2.0),
                  sat_mix=rec.get('sat_mix',0.15),
                  hishelf_threshold=rec.get('hishelf_threshold',-99.0))),
            ("vocal", "Vocal Forward",
             "More presence and width — vocal sits further forward",
             dict(presence_gain=min(0.5,rec.get('presence_gain',0.25)+0.15),
                  deess_threshold=max(rec.get('deess_threshold',3.0),3.0),
                  vocal_boost_db=rec.get('vocal_boost_db',0.0),
                  macro_target_db=rec.get('macro_target_db',0.0),
                  eq_shelf_db=min(3.0,rec.get('eq_shelf_db',1.5)+0.5),
                  eq_mud_db=min(-1.0,rec.get('eq_mud_db',-2.0)-0.5),
                  bass_side_mix=rec.get('bass_side_mix',0.15),
                  transient_boost=rec.get('transient_boost',2.5),
                  comp_threshold=rec.get('comp_threshold',-18.0),
                  comp_ratio=rec.get('comp_ratio',2.0),
                  sat_mix=rec.get('sat_mix',0.15),
                  hishelf_threshold=rec.get('hishelf_threshold',-99.0))),
            ("character", "Preserve Character",
             "Minimal processing — Suno's original sound, streaming-ready",
             dict(presence_gain=0.0, deess_threshold=-2.0, vocal_boost_db=0.0,
                  macro_target_db=0.0, eq_shelf_db=0.0, eq_mud_db=0.0,
                  air_blend=0.0, dehaze_depth=0.0, bass_side_mix=1.0,
                  sat_mix=0.0, transient_boost=0.0, comp_threshold=-6.0,
                  hishelf_threshold=-99.0)),
        ]

        for key, label, desc, kwargs in VARIANTS:
            try:
                if key == "raw":
                    full = _normalise_to_lufs(raw_audio.copy(), 44100)
                    full = _true_peak_limit(full)
                    psr  = 44100
                else:
                    full, psr = _run('streaming', **kwargs)

                # Save full for regeneration
                sf.write(str(preview_dir / f"full_{key}.wav"), full, psr, subtype='PCM_16')

                # Extract and save clip
                clip = extract_clip(full, psr, start_s, CLIP_DURATION)
                clip_fname = f"preview_{key}.wav"
                sf.write(str(preview_dir / clip_fname), clip, psr, subtype='PCM_16')

                evt = _json.dumps({
                    "type":  "variant",
                    "key":   key,
                    "label": label,
                    "description": desc,
                    "file":  clip_fname,
                })
                yield f"data: {evt}\n\n"

            except Exception as e:
                yield f"data: {_json.dumps({'type':'error','key':key,'message':str(e)})}\n\n"

        yield f"data: {_json.dumps({'type':'done'})}\n\n"
        if tmp_wav.exists():
            try: tmp_wav.unlink()
            except Exception: pass

    from flask import Response
    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache",
                             "X-Accel-Buffering": "no"})


@app.route("/preview_clip")
def preview_clip_route():
    """Serve a preview clip WAV file."""
    fname = request.args.get("file", "")
    if not fname or "/" in fname or "\\" in fname:
        return "Invalid filename", 400
    path = UPLOAD_DIR / "previews" / fname
    if not path.exists():
        return "Not found", 404
    from flask import send_file, make_response
    response = make_response(send_file(str(path), mimetype="audio/wav"))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    return response


@app.route("/preview_regen", methods=["POST"])
def preview_regen_route():
    """Re-extract clips at a new window position (fast — no re-mastering)."""
    start_s = float(request.form.get("start_s", 0))
    import json as _json
    recommended = {}
    if "recommended" in request.form:
        try:
            recommended = _json.loads(request.form["recommended"])
        except Exception:
            pass

    input_path  = UPLOAD_DIR / "preview_input.wav"
    preview_dir = UPLOAD_DIR / "previews"

    if not input_path.exists():
        return jsonify({"error": "No preview input file — run analysis first"}), 400

    try:
        result = regenerate_clips(
            str(input_path), recommended, str(preview_dir), start_s=start_s
        )
        return jsonify(result)
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500


@app.route("/check_update")
def check_update_route():
    """Return current update check state. Pass ?force=1 to bypass cache."""
    from updater import CACHE_FILE
    if request.args.get('force') == '1':
        try:
            if CACHE_FILE.exists():
                CACHE_FILE.unlink()
        except Exception:
            pass
        # Re-run the check synchronously
        import urllib.request, json as _json, re as _re
        from updater import API_URL, _get_zip_asset, is_newer, CURRENT_VERSION, _write_cache, _update_state, _state_lock
        try:
            req = urllib.request.Request(API_URL, headers={
                'User-Agent': f'StreamMaster/{CURRENT_VERSION}',
                'Accept': 'application/vnd.github+json',
            })
            with urllib.request.urlopen(req, timeout=8) as resp:
                release = _json.loads(resp.read())
            tag   = release.get('tag_name', '')
            asset = _get_zip_asset(release)
            avail = is_newer(tag)
            result = {
                'checked': True, 'update_available': avail,
                'current_version': CURRENT_VERSION,
                'latest_version': tag.lstrip('vV'),
                'release_url': release.get('html_url', ''),
                'asset_url':  asset['browser_download_url'] if asset else None,
                'asset_name': asset['name'] if asset else None,
                'error': None,
            }
            with _state_lock:
                _update_state.update(result)
            _write_cache(result)
            return jsonify(result)
        except Exception as e:
            return jsonify({'error': str(e), 'checked': True,
                            'update_available': False,
                            'current_version': CURRENT_VERSION})
    return jsonify(get_update_state())


@app.route("/apply_update", methods=["POST"])
def apply_update_route():
    """Download the update, stage it, and schedule a restart."""
    import json as _json
    from updater import CACHE_FILE

    # Always clear the cache before downloading so we fetch the true latest
    # asset URL — a cached result may point to an old release asset
    try:
        if CACHE_FILE.exists():
            CACHE_FILE.unlink()
    except Exception:
        pass

    # Re-fetch the current state (now uncached)
    state = get_update_state()
    if not state.get('update_available'):
        return jsonify({"error": "No update available"}), 400
    if not state.get('asset_url'):
        return jsonify({"error": "No download asset found — visit GitHub to update manually",
                        "release_url": state.get('release_url')}), 400
    try:
        result = apply_update(state['asset_url'], state['asset_name'])
        def _restart():
            import time, subprocess, os
            time.sleep(1.5)
            # Use 'start' to open bat in a new visible window that stays open
            subprocess.Popen(
                ['cmd', '/c', 'start', 'cmd', '/k', result['bat_path']]
            )
            os._exit(0)
        threading.Thread(target=_restart, daemon=True).start()
        return jsonify({"status": "restart_pending"})
    except Exception as e:
        # Clear cache on failure so next attempt re-fetches
        try:
            if CACHE_FILE.exists():
                CACHE_FILE.unlink()
        except Exception:
            pass
        return jsonify({"error": str(e)}), 500


@app.route("/history")
def history_route():
    """Return all history entries grouped by source file."""
    return jsonify(get_grouped())


@app.route("/history/clear", methods=["POST"])
def history_clear_route():
    """Clear all history entries."""
    clear_all()
    return jsonify({"status": "ok"})


@app.route("/stem_defaults")
def stem_defaults_route():
    return jsonify(STEM_DEFAULTS)


@app.route("/stem_master", methods=["POST"])
def stem_master_route():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    f = request.files["file"]
    if not f.filename.lower().endswith(".wav"):
        return jsonify({"error": "Only WAV files supported"}), 400
    if not _demucs_available():
        return jsonify({"error": "Demucs not installed. Run: pip install demucs"}), 400

    original_stem = Path(f.filename).stem
    profile       = request.form.get("profile", "streaming")
    profile_tag   = "_local" if profile == "local" else "_streaming"
    output_name   = f"{original_stem}_stemmaster{profile_tag}.wav"
    input_path    = UPLOAD_DIR / "stemmaster_input.wav"
    output_path   = UPLOAD_DIR / output_name
    f.save(str(input_path))

    # Parse per-stem settings from form
    import json as _json
    stem_settings = {}
    for stem_name in ['vocals', 'drums', 'bass', 'other']:
        key = f"stem_{stem_name}"
        if key in request.form:
            try:
                stem_settings[stem_name] = _json.loads(request.form[key])
            except Exception:
                pass

    _reset_log()
    try:
        result = stem_master(
            str(input_path), str(output_path),
            stem_settings=stem_settings if stem_settings else None,
            profile=profile
        )
        qc = qc_check(str(output_path))
        return jsonify({
            "status":  "ok",
            "output":  output_name,
            "stems":   result.get('stems', {}),
            "qc":      qc,
        })
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500


@app.route("/repair_status")
def repair_status():
    return jsonify({
        "demucs_available": _demucs_available(),
        "phase_available":  True
    })


@app.route("/repair", methods=["POST"])
def repair_route():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    f = request.files["file"]
    if not f.filename.lower().endswith(".wav"):
        return jsonify({"error": "Only WAV files are supported"}), 400

    method        = request.form.get("method", "auto")
    original_stem = Path(f.filename).stem
    output_name   = f"{original_stem}_repaired.wav"
    input_path    = UPLOAD_DIR / "repair_input.wav"
    output_path   = UPLOAD_DIR / output_name

    f.save(str(input_path))
    _reset_log()

    try:
        _, repairs = repair_boundaries(str(input_path), str(output_path),
                                       method=method)
    except ImportError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({
        "status":  "ok",
        "output":  output_name,
        "repairs": repairs,
        "method":  method
    })


@app.route("/bridge", methods=["POST"])
def bridge_route():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    f = request.files["file"]
    if not f.filename.lower().endswith(".wav"):
        return jsonify({"error": "Only WAV files are supported"}), 400

    try:
        start_time = float(request.form.get("start_time", 0))
        end_time   = float(request.form.get("end_time",   0))
    except ValueError:
        return jsonify({"error": "start_time and end_time must be numbers"}), 400

    original_stem = Path(f.filename).stem
    output_name   = f"{original_stem}_bridged.wav"

    input_path  = UPLOAD_DIR / "bridge_input.wav"
    output_path = UPLOAD_DIR / output_name

    f.save(str(input_path))

    try:
        level_bridge(str(input_path), start_time, end_time, str(output_path))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "ok", "output": output_name})


@app.route("/heal", methods=["POST"])
def heal_route():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    f = request.files["file"]
    if not f.filename.lower().endswith(".wav"):
        return jsonify({"error": "Only WAV files are supported"}), 400

    try:
        in_time  = float(request.form.get("in_time",  0))
        out_time = float(request.form.get("out_time", 0))
        blend_ms = float(request.form.get("blend_ms", 120))
    except ValueError:
        return jsonify({"error": "in_time, out_time, and blend_ms must be numbers"}), 400

    original_stem = Path(f.filename).stem
    output_name   = f"{original_stem}_healed.wav"

    input_path  = UPLOAD_DIR / "heal_input.wav"
    output_path = UPLOAD_DIR / output_name

    f.save(str(input_path))

    try:
        heal(str(input_path), in_time, out_time, blend_ms, str(output_path))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "ok", "output": output_name})


@app.route("/heartbeat", methods=["POST"])
def heartbeat_route():
    """Called by the browser every 5 seconds. Resets the shutdown timer."""
    global _last_heartbeat, _heartbeat_active
    _last_heartbeat = _time.time()
    if not _heartbeat_active:
        _heartbeat_active = True
        threading.Thread(target=_heartbeat_monitor, daemon=True).start()
    return jsonify({"status": "ok"})


def _heartbeat_monitor():
    """
    Background thread: exits the server if no heartbeat arrives within
    _HEARTBEAT_TIMEOUT seconds. Fires only after the first heartbeat,
    so the server stays alive indefinitely if the browser hasn't connected yet.
    Page refreshes are safe — the browser resumes heartbeats within ~1s.
    """
    import os
    while True:
        _time.sleep(5)
        elapsed = _time.time() - _last_heartbeat
        if elapsed > _HEARTBEAT_TIMEOUT:
            print(f"\n  Server     : no browser heartbeat for {elapsed:.0f}s — shutting down")
            os._exit(0)


@app.route("/shutdown", methods=["POST"])
def shutdown_route():
    """Gracefully shut down the server."""
    def _stop():
        import time, os
        time.sleep(0.5)
        os._exit(0)
    threading.Thread(target=_stop, daemon=True).start()
    return jsonify({"status": "shutting down"})


@app.route("/download", methods=["GET"])
def download_route():
    filename = request.args.get("file")
    if filename:
        p = UPLOAD_DIR / Path(filename).name  # sanitise
        if p.exists():
            return send_file(str(p), as_attachment=True,
                             download_name=p.name, mimetype="audio/wav")
    # Fallback: most recent remaster
    candidates = sorted(
        list(UPLOAD_DIR.glob("*_remaster*.wav"))  +
        list(UPLOAD_DIR.glob("*_spliced.wav"))    +
        list(UPLOAD_DIR.glob("*_healed.wav"))     +
        list(UPLOAD_DIR.glob("*_bridged.wav"))    +
        list(UPLOAD_DIR.glob("*_dejinxed.wav"))   +
        list(UPLOAD_DIR.glob("*_refmatched.wav")),
        key=lambda p: p.stat().st_mtime
    )
    if not candidates:
        return jsonify({"error": "No output file found"}), 404
    p = candidates[-1]
    return send_file(str(p), as_attachment=True,
                     download_name=p.name, mimetype="audio/wav")


@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status": "ready"})


if __name__ == "__main__":
    # Check if another instance is already running on port 5051
    import socket
    _sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _in_use = _sock.connect_ex(('127.0.0.1', 5051)) == 0
    _sock.close()
    if _in_use:
        print("\n⚠  Port 5051 is already in use — another StreamMaster instance may be running.")
        print("   Opening the existing instance in your browser instead.\n")
        import webbrowser as _wb
        _wb.open("http://localhost:5051")
        sys.exit(0)

    print("\n┌─────────────────────────────────────────────┐")
    print("│  StreamMaster v2.0.9  —  localhost:5051      │")
    print("└─────────────────────────────────────────────┘")
    print("  Opening http://localhost:5051 in your browser…\n")
    check_for_updates_background()
    if '--no-browser' not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open("http://localhost:5051")).start()
    app.run(port=5051, debug=False)
