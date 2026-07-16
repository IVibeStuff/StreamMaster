#!/usr/bin/env bash
set -e

echo ""
echo "  =========================================="
echo "   StreamMaster"
echo "  =========================================="
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "  [ERROR] python3 not found."
    echo ""
    echo "  macOS:  brew install python"
    echo "  Ubuntu: sudo apt install python3 python3-pip"
    echo ""
    exit 1
fi

echo "  Found: $(python3 --version)"
echo ""

# Check packages
echo "  Checking packages..."
if ! python3 -c "import flask,flask_cors,pyloudnorm,soundfile,scipy,numpy" &>/dev/null; then
    echo "  Installing packages (first run only)..."
    python3 -m pip install flask flask-cors pyloudnorm soundfile scipy numpy matchering \
        --quiet --disable-pip-version-check
fi

# Launch
echo "  Starting server..."
echo "  Browser will open at http://localhost:5051"
echo "  Press Ctrl+C to stop."
echo ""

# Open browser after short delay (background)
(sleep 2 && python3 -c "import webbrowser; webbrowser.open('http://localhost:5051')") &

cd "$(dirname "$0")"
python3 server.py
