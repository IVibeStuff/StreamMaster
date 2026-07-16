#!/usr/bin/env python3
"""
server.py — Local bridge server for the Spotify Mastering UI.

Run once:  python server.py
Browser opens automatically at http://localhost:5051

Requires: pip install flask flask-cors pyloudnorm soundfile scipy numpy
"""

import tempfile
import webbrowser
import threading
import io
import numpy as np
from pathlib import Path
from flask import Flask, request, jsonify, send_file, Response
from flask_cors import CORS

import sys
sys.path.insert(0, str(Path(__file__).parent))
from spotify_master import master
from splice import splice
from heal import heal
from levelbridge import level_bridge
from dejinx import dejinx
from mastering_extras import reference_match
from analyser import analyse
from qc import qc_check

app = Flask(__name__)
CORS(app)

UPLOAD_DIR = Path(tempfile.gettempdir()) / "spotify_master"
UPLOAD_DIR.mkdir(exist_ok=True)

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
    macro_target_db = float(request.form.get("macro_target_db",  3.5))
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
               profile=profile)
        qc = qc_check(str(output_path))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
    input_path = UPLOAD_DIR / "analyse_input.wav"
    f.save(str(input_path))
    try:
        result = analyse(str(input_path))
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
    print("\n┌─────────────────────────────────────────────┐")
    print("│  Spotify Mastering Server  — localhost:5051 │")
    print("└─────────────────────────────────────────────┘")
    print("  Opening http://localhost:5051 in your browser…\n")
    threading.Timer(1.0, lambda: webbrowser.open("http://localhost:5051")).start()
    app.run(port=5051, debug=False)
