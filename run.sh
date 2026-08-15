#!/bin/bash
# OSM Ad Bot — ads + forecast-aware automatic training
# =====================================================
# ./run.sh [StorageDump directory-or-ZIP]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOWNLOADS_DIR="${OSM_DUMP_DIR:-/Users/ns0bj/Downloads}"
REQUESTED_DUMP="${1:-}"
DUMP_PATH="${REQUESTED_DUMP}"
HAR_PROFILE="${OSM_TRAINING_HAR:-${SCRIPT_DIR}/en.onlinesoccermanager.com-training.har}"
RUNTIME_DIR="${SCRIPT_DIR}/tmp/osm-runtime"
LOG="${OSM_LOG:-${RUNTIME_DIR}/conductor.log}"
PID_FILE="${RUNTIME_DIR}/conductor.pid"

mkdir -p "${RUNTIME_DIR}"

if [ -z "${DUMP_PATH}" ]; then
    while IFS= read -r candidate; do
        if [ -d "${candidate}" ] || [ -f "${candidate}" ]; then
            DUMP_PATH="${candidate}"
            break
        fi
    done < <(find "${DOWNLOADS_DIR}" -maxdepth 1 \
        -name 'storagedump_en.onlinesoccermanager.com_*' -print | sort -r)
fi

if [ -z "${DUMP_PATH}" ] || { [ ! -d "${DUMP_PATH}" ] && [ ! -f "${DUMP_PATH}" ]; }; then
    echo "ERROR: No StorageDump directory or ZIP found."
    echo "Export a fresh StorageDump after logging in, then run:"
    echo "  ./run.sh /absolute/path/to/storagedump_en.onlinesoccermanager.com_....zip"
    exit 1
fi

extract_dump_arg() {
    local command_line="$1"
    printf '%s\n' "${command_line}" | sed -nE 's/.* --dump ([^ ]+).*/\1/p'
}

if [ -f "${PID_FILE}" ]; then
    EXISTING_PID="$(tail -n 1 "${PID_FILE}" 2>/dev/null | awk '{print $NF}')"
    if [ -n "${EXISTING_PID}" ] && kill -0 "${EXISTING_PID}" 2>/dev/null; then
        EXISTING_COMMAND="$(ps -p "${EXISTING_PID}" -o command= 2>/dev/null || true)"
        if [[ "${EXISTING_COMMAND}" == *"osm_ad_bot_conductor.py"* ]]; then
            EXISTING_DUMP="$(extract_dump_arg "${EXISTING_COMMAND}")"
            if [ -n "${EXISTING_DUMP}" ] && [ "${EXISTING_DUMP}" != "${DUMP_PATH}" ]; then
                if [ "${OSM_RESTART_ON_NEW_DUMP:-1}" = "0" ]; then
                    echo "ERROR: Bot PID ${EXISTING_PID} uses a different StorageDump."
                    echo "Running : ${EXISTING_DUMP}"
                    echo "Selected: ${DUMP_PATH}"
                    echo "Stop PID ${EXISTING_PID}, then rerun ./run.sh (or unset OSM_RESTART_ON_NEW_DUMP=0)."
                    exit 1
                fi
                echo "Bot PID ${EXISTING_PID} uses an older/different StorageDump."
                echo "Reloading it with: ${DUMP_PATH}"
                kill "${EXISTING_PID}"
                for _ in $(seq 1 30); do
                    if ! kill -0 "${EXISTING_PID}" 2>/dev/null; then
                        break
                    fi
                    sleep 1
                done
                if kill -0 "${EXISTING_PID}" 2>/dev/null; then
                    echo "ERROR: Existing bot PID ${EXISTING_PID} did not stop within 30s."
                    echo "Stop it manually, then rerun ./run.sh."
                    exit 1
                fi
                rm -f "${PID_FILE}"
            else
                echo "Bot is already running with PID ${EXISTING_PID}."
                echo "Attaching to its live log now."
                echo "Press Ctrl+C to stop following logs; the bot keeps running."
                echo "Stop the bot: kill ${EXISTING_PID}"
                echo ""
                tail -f "${LOG}"
                exit 0
            fi
        else
            echo "Ignoring stale PID file: ${EXISTING_PID} belongs to another process."
        fi
    fi
fi

echo "=========================================="
echo "  OSM Ad Bot — Quick Run"
echo "=========================================="
echo "Dump     : ${DUMP_PATH}"
echo "Log file : ${LOG}"
echo "Mode     : headless, 1 conductor + 8 watchers"
echo "Training : automatic, forecast-aware (60s poll)"
if [ -f "${HAR_PROFILE}" ]; then
    echo "HAR      : timer/profile data only (contains no usable token)"
else
    echo "HAR      : not found; built-in safe timer defaults will be used"
fi
echo ""

cd "${SCRIPT_DIR}"

ARGS=(
    --dump "${DUMP_PATH}"
    --headless
    --watcher-tabs 8
    --poll-interval 15
    --ad-duration 120
    --auto-training
    --training-poll-interval 60
    --log "${LOG}"
)
if [ -f "${HAR_PROFILE}" ]; then
    ARGS+=(--training-har-profile "${HAR_PROFILE}")
fi

echo "Starting bot..."
nohup python3 osm_ad_bot_conductor.py "${ARGS[@]}" </dev/null >/dev/null 2>&1 &

PID=$!
echo ""
echo "Started with PID: ${PID}"
echo "${PID}" > "${PID_FILE}"
echo ""
echo "Follow logs:     tail -f ${LOG}"
echo "Stop:            kill ${PID}"
echo ""
echo "Press Ctrl+C to stop following logs. Bot keeps running in background."
echo ""

# Show logs in real-time
tail -f "${LOG}"
