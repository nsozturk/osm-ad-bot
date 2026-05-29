#!/bin/bash
# OSM Ad Bot Conductor — MAIN SCRIPT (9 Tabs)
# ======================================================
# Usage: ./run.sh <path-to-storage-dump>
#   The dump directory should contain cookies.json (and optionally local.json, session.json)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Allow passing dump directory as argument, otherwise show usage
if [ -z "$1" ]; then
    echo "Usage: $0 <path-to-storage-dump>"
    echo ""
    echo "Example:"
    echo "  $0 /Users/ns0bj/Downloads/storagedump_en.onlinesoccermanager.com_2026-05-29T19-49-58-310Z"
    exit 1
fi

DUMP_DIR="$1"
LOG="/tmp/osm_conductor_main.log"

echo "=========================================="
echo "  OSM Ad Bot Conductor — 9 Tabs"
echo "=========================================="
echo "Dump dir : ${DUMP_DIR}"
echo "Log file : ${LOG}"
echo "Mode     : headless, 1 conductor + 8 watchers"
echo ""

if [ ! -d "${DUMP_DIR}" ]; then
    echo "ERROR: Dump directory not found: ${DUMP_DIR}"
    exit 1
fi

cd "${SCRIPT_DIR}"

echo "Starting bot..."
python3 osm_ad_bot_conductor.py \
    --dump "${DUMP_DIR}" \
    --headless \
    --watcher-tabs 8 \
    --poll-interval 15 \
    --ad-duration 120 \
    --log "${LOG}" &

PID=$!
echo ""
echo "Started with PID: ${PID}"
echo "PID ${PID}" > /tmp/osm_conductor_main.pid
echo ""
echo "Follow logs:     tail -f ${LOG}"
echo "Stop:            kill $(cat /tmp/osm_conductor_main.pid)"
echo ""
echo "Press Ctrl+C to stop following logs. Bot keeps running in background."
echo ""

# Show logs in real-time
tail -f "${LOG}"
