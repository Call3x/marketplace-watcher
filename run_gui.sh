#!/bin/bash
# Starts the shopping list editor GUI and opens it in your browser.
set -euo pipefail
cd "$(dirname "$0")"

URL="http://localhost:5000"

(sleep 1 && xdg-open "$URL" >/dev/null 2>&1) &

echo "Starting editor at $URL (Ctrl+C to stop)"
python3 gui.py
