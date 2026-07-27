#!/bin/bash
# Entry point for cron. Loads .env, runs the watcher, logs output.
set -euo pipefail
cd "$(dirname "$0")"

if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

LOG_FILE="logs/run_$(date +%Y%m%d_%H%M%S).log"
python3 run.py >> "$LOG_FILE" 2>&1

# Keep only the last 60 log files.
ls -t logs/run_*.log 2>/dev/null | tail -n +61 | xargs -r rm --
