#!/bin/bash
# launchd-owned runner. It must remain small: resolve inputs, then exec Python.

set -euo pipefail

SCRIPT_DIR="${OSM_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
DOWNLOADS_DIR="${OSM_DUMP_DIR:-/Users/ns0bj/Downloads}"
RUNTIME_DIR="${SCRIPT_DIR}/tmp/osm-runtime"
DUMP_CONFIG="${OSM_DUMP_CONFIG:-${RUNTIME_DIR}/launchd.dump}"
LOG="${OSM_LOG:-${RUNTIME_DIR}/conductor.log}"
PID_FILE="${RUNTIME_DIR}/conductor.pid"
HAR_PROFILE="${OSM_TRAINING_HAR:-${SCRIPT_DIR}/en.onlinesoccermanager.com-training.har}"
PYTHON_BIN="${OSM_PYTHON:-$(command -v python3)}"

mkdir -p "${RUNTIME_DIR}"

DUMP_PATH=""
if [ -f "${DUMP_CONFIG}" ]; then
    DUMP_PATH="$(head -n 1 "${DUMP_CONFIG}")"
    if [ -z "${DUMP_PATH}" ] || { [ ! -d "${DUMP_PATH}" ] && [ ! -f "${DUMP_PATH}" ]; }; then
        echo "[$(date '+%Y-%m-%dT%H:%M:%S%z')] ERROR: configured StorageDump is unavailable" >&2
        exit 2
    fi
else
    DUMP_PATH=""
    if [ -d "${DOWNLOADS_DIR}" ]; then
        while IFS= read -r candidate; do
            if [ -d "${candidate}" ] || [ -f "${candidate}" ]; then
                DUMP_PATH="${candidate}"
                break
            fi
        done < <(find "${DOWNLOADS_DIR}" -maxdepth 1 \
            -name 'storagedump_en.onlinesoccermanager.com_*' -print | sort -r)
    fi
fi

if [ -z "${DUMP_PATH}" ]; then
    echo "[$(date '+%Y-%m-%dT%H:%M:%S%z')] ERROR: no valid StorageDump found" >&2
    exit 2
fi
if [ ! -x "${PYTHON_BIN}" ]; then
    echo "[$(date '+%Y-%m-%dT%H:%M:%S%z')] ERROR: Python not executable: ${PYTHON_BIN}" >&2
    exit 2
fi

printf '%s\n' "$$" > "${PID_FILE}.new"
mv "${PID_FILE}.new" "${PID_FILE}"

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

cd "${SCRIPT_DIR}"
exec "${PYTHON_BIN}" osm_ad_bot_conductor.py "${ARGS[@]}"
