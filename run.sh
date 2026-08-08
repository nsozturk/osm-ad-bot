#!/bin/bash
# OSM Ad Bot — Quick Run Script (Latest Dump: 2026-08-06)
# ======================================================
# ./run.sh  → runs directly with the latest dump

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DUMP_DIR="/Users/ns0bj/Downloads/storagedump_en.onlinesoccermanager.com_2026-08-06T18-54-40-965Z"
LOG="/tmp/osm_conductor_main.log"

echo "=========================================="
echo "  OSM Ad Bot — Quick Run"
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
echo "Stop:            kill ${PID}"
echo ""
echo "Press Ctrl+C to stop following logs. Bot keeps running in background."
echo ""

# Show logs in real-time
tail -f "${LOG}"
