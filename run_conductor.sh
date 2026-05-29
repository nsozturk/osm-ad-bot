#!/bin/bash
# OSM Ad Bot Conductor — Default Run
# Usage: ./run_conductor.sh <path-to-storage-dump>

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -z "$1" ]; then
    echo "Usage: $0 <path-to-storage-dump>"
    exit 1
fi

DUMP_DIR="$1"
LOG="/tmp/osm_conductor_default.log"

echo "=== OSM Ad Bot Conductor (Default) ==="
echo "Dump dir : ${DUMP_DIR}"
echo "Log file : ${LOG}"
echo "Mode     : headless, 1 watcher, 2-min ad duration"
echo ""

if [ ! -d "${DUMP_DIR}" ]; then
    echo "ERROR: Dump directory not found: ${DUMP_DIR}"
    exit 1
fi

cd "${SCRIPT_DIR}"

python3 osm_ad_bot_conductor.py \
    --dump "${DUMP_DIR}" \
    --headless \
    --watcher-tabs 1 \
    --poll-interval 30 \
    --ad-duration 120 \
    --log "${LOG}" &

PID=$!
echo "Started with PID: ${PID}"
echo "PID ${PID}" > /tmp/osm_conductor_default.pid
echo ""
echo "To follow logs:  tail -f ${LOG}"
echo "To stop:         kill $(cat /tmp/osm_conductor_default.pid)"
