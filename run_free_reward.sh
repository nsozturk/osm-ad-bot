#!/usr/bin/env bash
# ==============================================================================
# run_free_reward.sh — Convenience launcher for OSM Auto Free Reward Bot
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_BIN="python3"
if [[ -d "venv" && -x "venv/bin/python3" ]]; then
    PYTHON_BIN="venv/bin/python3"
elif [[ -d ".venv" && -x ".venv/bin/python3" ]]; then
    PYTHON_BIN=".venv/bin/python3"
fi

export PYTHONUNBUFFERED=1

PID_FILE="tmp/osm-runtime/free_reward_worker.pid"
LOG_FILE="tmp/osm-runtime/free_reward_worker.log"

case "${1:-}" in
    status)
        if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
            echo "Free Reward Worker is RUNNING (PID: $(cat "$PID_FILE"))"
            if [[ -f "$LOG_FILE" ]]; then
                echo "--- Recent Log Output ---"
                tail -n 12 "$LOG_FILE"
            fi
        else
            echo "Free Reward Worker is NOT running."
        fi
        exit 0
        ;;
    stop)
        if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
            PID=$(cat "$PID_FILE")
            echo "Stopping Free Reward Worker (PID: $PID)..."
            kill "$PID" 2>/dev/null || true
            rm -f "$PID_FILE"
            echo "Stopped."
        else
            echo "No running Free Reward Worker found."
            rm -f "$PID_FILE" 2>/dev/null || true
        fi
        exit 0
        ;;
    start)
        shift || true
        if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
            echo "Free Reward Worker is ALREADY running (PID: $(cat "$PID_FILE"))."
            exit 0
        fi
        mkdir -p tmp/osm-runtime
        echo "Starting Free Reward Worker in background..."
        nohup "$PYTHON_BIN" -u "$SCRIPT_DIR/auto_free_reward.py" --continuous --workers 3 --delay 0.5 "$@" > "$LOG_FILE" 2>&1 &
        echo $! > "$PID_FILE"
        echo "Started Free Reward Worker (PID: $(cat "$PID_FILE")). Log: $LOG_FILE"
        exit 0
        ;;
esac

exec "$PYTHON_BIN" -u "$SCRIPT_DIR/auto_free_reward.py" "$@"
