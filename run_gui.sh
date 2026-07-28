#!/bin/bash
# Starts the shopping list editor GUI and opens it in your browser.
#
# Works both from a terminal and double-clicked in a file manager (e.g.
# Nautilus "Run as a Program"), which launches scripts without a terminal
# and with a minimal environment — so this avoids relying on PATH lookups
# or a controlling terminal for its output.
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

PYTHON=/usr/bin/python3
URL="http://localhost:5000"
LOG="$DIR/logs/gui.log"
mkdir -p "$DIR/logs"

notify() {
    command -v notify-send >/dev/null 2>&1 && notify-send "marketplace-watcher" "$1" || true
}

# Already running? Just open the browser.
if curl -s -o /dev/null --max-time 1 "$URL" 2>/dev/null; then
    xdg-open "$URL" >/dev/null 2>&1 &
    exit 0
fi

: > "$LOG"
"$PYTHON" "$DIR/gui.py" >> "$LOG" 2>&1 &
GUI_PID=$!

# Poll for the server to actually come up instead of a blind sleep.
for i in $(seq 1 30); do
    if curl -s -o /dev/null --max-time 1 "$URL" 2>/dev/null; then
        xdg-open "$URL" >/dev/null 2>&1 &
        notify "Editor started at $URL"
        exit 0
    fi
    if ! kill -0 "$GUI_PID" 2>/dev/null; then
        notify "Editor failed to start — see logs/gui.log"
        exit 1
    fi
    sleep 0.5
done

notify "Editor is taking longer than expected — check logs/gui.log"
exit 1
