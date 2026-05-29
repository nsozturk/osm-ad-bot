#!/bin/bash
# OSM Ad Bot — Legacy Single-Tab Mode
# Usage: ./run_legacy.sh <path-to-storage-dump>

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -z "$1" ]; then
    echo "Usage: $0 <path-to-storage-dump>"
    exit 1
fi

DUMP_DIR="$1"
LOG="/tmp/osm_ad_bot_legacy.log"

echo "=== OSM Ad Bot (Legacy Single-Tab) ==="
echo "Dump dir : ${DUMP_DIR}"
echo "Log file : ${LOG}"
echo "Mode     : headless, 1 tab, continuous loop"
echo ""

if [ ! -d "${DUMP_DIR}" ]; then
    echo "ERROR: Dump directory not found: ${DUMP_DIR}"
    exit 1
fi

cd "${SCRIPT_DIR}"

python3 osm_ad_bot.py \
    --dump "${DUMP_DIR}" \
    --headless \
    --tabs 1 \
    --ad-duration 120 \
    --log "${LOG}" &

PID=$!
echo "Started with PID: ${PID}"
echo "PID ${PID}" > /tmp/osm_ad_bot_legacy.pid
echo ""
echo "Follow logs:  tail -f ${LOG}"
echo "Stop:         kill $(cat /tmp/osm_ad_bot_legacy.pid)"
