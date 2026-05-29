#!/bin/bash
# OSM Ad Bot Conductor — Headed (Visible Browser)
# Usage: ./run_conductor_headed.sh <path-to-storage-dump>

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -z "$1" ]; then
    echo "Usage: $0 <path-to-storage-dump>"
    exit 1
fi

DUMP_DIR="$1"
LOG="/tmp/osm_conductor_headed.log"

echo "=== OSM Ad Bot Conductor (Headed) ==="
echo "Dump dir : ${DUMP_DIR}"
echo "Log file : ${LOG}"
echo "Mode     : visible browser, 1 watcher, 2-min ad duration"
echo ""

if [ ! -d "${DUMP_DIR}" ]; then
    echo "ERROR: Dump directory not found: ${DUMP_DIR}"
    exit 1
fi

cd "${SCRIPT_DIR}"

# Run in FOREGROUND so you can see the browser
python3 osm_ad_bot_conductor.py \
    --dump "${DUMP_DIR}" \
    --watcher-tabs 1 \
    --poll-interval 20 \
    --ad-duration 120 \
    --log "${LOG}"
