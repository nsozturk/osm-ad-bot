#!/bin/bash
# OSM Ad Bot Conductor — Debug Mode
# Usage: ./run_conductor_debug.sh <path-to-storage-dump>

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -z "$1" ]; then
    echo "Usage: $0 <path-to-storage-dump>"
    exit 1
fi

DUMP_DIR="$1"
LOG="/tmp/osm_conductor_debug.log"

echo "=== OSM Ad Bot Conductor (DEBUG) ==="
echo "Dump dir : ${DUMP_DIR}"
echo "Log file : ${LOG}"
echo "Mode     : visible browser, 1 watcher, fast poll (10s)"
echo ""

if [ ! -d "${DUMP_DIR}" ]; then
    echo "ERROR: Dump directory not found: ${DUMP_DIR}"
    exit 1
fi

cd "${SCRIPT_DIR}"

python3 osm_ad_bot_conductor.py \
    --dump "${DUMP_DIR}" \
    --watcher-tabs 1 \
    --poll-interval 10 \
    --ad-duration 120 \
    --log "${LOG}"
