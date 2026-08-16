#!/bin/bash
# OSM Ad Bot — launchd-supervised ads + automatic training
# =========================================================
# ./run.sh [StorageDump directory-or-ZIP]
# ./run.sh start|restart [StorageDump directory-or-ZIP]
# ./run.sh stop|status|logs

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOWNLOADS_DIR="${OSM_DUMP_DIR:-/Users/ns0bj/Downloads}"
HAR_PROFILE="${OSM_TRAINING_HAR:-${SCRIPT_DIR}/en.onlinesoccermanager.com-training.har}"
RUNTIME_DIR="${SCRIPT_DIR}/tmp/osm-runtime"
LOG="${OSM_LOG:-${RUNTIME_DIR}/conductor.log}"
LAUNCHD_LOG="${RUNTIME_DIR}/launchd.log"
PID_FILE="${RUNTIME_DIR}/conductor.pid"
DUMP_CONFIG="${RUNTIME_DIR}/launchd.dump"
SOURCE_DUMP_CONFIG="${RUNTIME_DIR}/launchd.source-dump"
STAGED_DUMP="${RUNTIME_DIR}/launchd-storage-dump.zip"
RUNNER="${SCRIPT_DIR}/launchd/osm-ad-bot-runner.sh"
LABEL="${OSM_LAUNCHD_LABEL:-dev.nsozturk.osm-ad-bot}"
LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
PLIST_PATH="${LAUNCH_AGENTS_DIR}/${LABEL}.plist"
DOMAIN="gui/$(id -u)"
SERVICE_TARGET="${DOMAIN}/${LABEL}"
PYTHON_BIN="${OSM_PYTHON:-$(command -v python3)}"

mkdir -p "${RUNTIME_DIR}"

ACTION="run"
REQUESTED_DUMP=""
case "${1:-}" in
    start|restart|stop|status|logs)
        ACTION="$1"
        REQUESTED_DUMP="${2:-}"
        ;;
    "")
        ;;
    *)
        REQUESTED_DUMP="$1"
        ;;
esac

select_dump() {
    local requested="$1"
    local candidate=""
    if [ -n "${requested}" ]; then
        if [ -d "${requested}" ] || [ -f "${requested}" ]; then
            printf '%s\n' "${requested}"
            return 0
        fi
        echo "ERROR: StorageDump not found: ${requested}" >&2
        return 1
    fi
    if [ -d "${DOWNLOADS_DIR}" ]; then
        while IFS= read -r candidate; do
            if [ -d "${candidate}" ] || [ -f "${candidate}" ]; then
                printf '%s\n' "${candidate}"
                return 0
            fi
        done < <(find "${DOWNLOADS_DIR}" -maxdepth 1 \
            -name 'storagedump_en.onlinesoccermanager.com_*' -print | sort -r)
    fi
    echo "ERROR: No StorageDump directory or ZIP found." >&2
    echo "Export a fresh StorageDump after logging in, then run:" >&2
    echo "  ./run.sh /absolute/path/to/storagedump_en.onlinesoccermanager.com_....zip" >&2
    return 1
}

launchd_loaded() {
    launchctl print "${SERVICE_TARGET}" >/dev/null 2>&1
}

launchd_pid() {
    launchctl print "${SERVICE_TARGET}" 2>/dev/null \
        | awk '/^[[:space:]]*pid = / { print $3; exit }'
}

launchd_state() {
    launchctl print "${SERVICE_TARGET}" 2>/dev/null \
        | awk -F'= ' '/^[[:space:]]*state = / { print $2; exit }'
}

generate_plist() {
    local target="$1"
    plutil -create xml1 "${target}"
    plutil -insert Label -string "${LABEL}" "${target}"
    plutil -insert ProgramArguments -json '["/bin/bash"]' "${target}"
    plutil -insert ProgramArguments.1 -string "${RUNNER}" "${target}"
    plutil -insert WorkingDirectory -string "${SCRIPT_DIR}" "${target}"
    plutil -insert RunAtLoad -bool YES "${target}"
    plutil -insert KeepAlive -bool YES "${target}"
    plutil -insert ProcessType -string Background "${target}"
    plutil -insert ThrottleInterval -integer 15 "${target}"
    plutil -insert StandardOutPath -string "${LAUNCHD_LOG}" "${target}"
    plutil -insert StandardErrorPath -string "${LAUNCHD_LOG}" "${target}"
    plutil -insert EnvironmentVariables -json '{}' "${target}"
    plutil -insert EnvironmentVariables.HOME -string "${HOME}" "${target}"
    plutil -insert EnvironmentVariables.PATH -string \
        '/opt/homebrew/bin:/usr/local/bin:/Library/Frameworks/Python.framework/Versions/3.10/bin:/usr/bin:/bin:/usr/sbin:/sbin' "${target}"
    plutil -insert EnvironmentVariables.OSM_PROJECT_DIR -string "${SCRIPT_DIR}" "${target}"
    plutil -insert EnvironmentVariables.OSM_DUMP_DIR -string "${DOWNLOADS_DIR}" "${target}"
    plutil -insert EnvironmentVariables.OSM_DUMP_CONFIG -string "${DUMP_CONFIG}" "${target}"
    plutil -insert EnvironmentVariables.OSM_LOG -string "${LOG}" "${target}"
    plutil -insert EnvironmentVariables.OSM_LAUNCHD_LOG -string "${LAUNCHD_LOG}" "${target}"
    plutil -insert EnvironmentVariables.OSM_TRAINING_HAR -string "${HAR_PROFILE}" "${target}"
    plutil -insert EnvironmentVariables.OSM_PYTHON -string "${PYTHON_BIN}" "${target}"
}

stop_manual_conductor() {
    [ -f "${PID_FILE}" ] || return 0
    local pid command_line
    pid="$(tr -cd '0-9' < "${PID_FILE}")"
    [ -n "${pid}" ] || return 0
    if ! kill -0 "${pid}" 2>/dev/null; then
        return 0
    fi
    command_line="$(ps -p "${pid}" -o command= 2>/dev/null || true)"
    if [[ "${command_line}" != *"osm_ad_bot_conductor.py"* ]]; then
        return 0
    fi
    echo "Stopping legacy conductor PID ${pid} before enabling launchd..." >&2
    kill "${pid}"
    for _ in $(seq 1 30); do
        kill -0 "${pid}" 2>/dev/null || return 0
        sleep 1
    done
    echo "ERROR: Legacy conductor PID ${pid} did not stop within 30s." >&2
    return 1
}

install_or_update_agent() {
    local candidate changed=0 was_loaded=0
    candidate="$(mktemp "${RUNTIME_DIR}/${LABEL}.XXXXXX.plist")"
    generate_plist "${candidate}"
    plutil -lint "${candidate}" >/dev/null
    mkdir -p "${LAUNCH_AGENTS_DIR}"

    if launchd_loaded; then
        was_loaded=1
    fi
    if [ "${was_loaded}" -eq 0 ]; then
        stop_manual_conductor
    fi
    if [ ! -f "${PLIST_PATH}" ] || ! cmp -s "${candidate}" "${PLIST_PATH}"; then
        changed=1
        if [ "${was_loaded}" -eq 1 ]; then
            launchctl bootout "${SERVICE_TARGET}"
        fi
        cp "${candidate}" "${PLIST_PATH}"
        chmod 600 "${PLIST_PATH}"
        launchctl bootstrap "${DOMAIN}" "${PLIST_PATH}"
    elif [ "${was_loaded}" -eq 0 ]; then
        launchctl bootstrap "${DOMAIN}" "${PLIST_PATH}"
        changed=1
    fi
    rm -f "${candidate}"
    printf '%s\n' "${changed}"
}

write_dump_config() {
    local dump_path="$1"
    local current=""
    if [ -f "${DUMP_CONFIG}" ]; then
        current="$(head -n 1 "${DUMP_CONFIG}")"
    fi
    if [ "${current}" = "${dump_path}" ]; then
        printf '0\n'
        return 0
    fi
    printf '%s\n' "${dump_path}" > "${DUMP_CONFIG}.new"
    mv "${DUMP_CONFIG}.new" "${DUMP_CONFIG}"
    printf '1\n'
}

stage_dump_for_launchd() {
    local source_path="$1"
    local candidate="${STAGED_DUMP}.new.$$"
    local changed=1
    if [ -f "${source_path}" ]; then
        cp "${source_path}" "${candidate}"
    else
        /usr/bin/ditto -c -k --norsrc "${source_path}" "${candidate}"
    fi
    if [ -f "${STAGED_DUMP}" ] && cmp -s "${candidate}" "${STAGED_DUMP}"; then
        changed=0
        rm -f "${candidate}"
    else
        chmod 600 "${candidate}"
        mv "${candidate}" "${STAGED_DUMP}"
    fi
    printf '%s\n' "${source_path}" > "${SOURCE_DUMP_CONFIG}.new"
    mv "${SOURCE_DUMP_CONFIG}.new" "${SOURCE_DUMP_CONFIG}"
    printf '%s\n' "${changed}"
}

wait_for_launchd_pid() {
    local pid=""
    for _ in $(seq 1 30); do
        pid="$(launchd_pid || true)"
        if [ -n "${pid}" ] && kill -0 "${pid}" 2>/dev/null; then
            printf '%s\n' "${pid}"
            return 0
        fi
        sleep 1
    done
    echo "ERROR: LaunchAgent did not reach a running state within 30s." >&2
    return 1
}

print_status() {
    local pid state selected=""
    if ! launchd_loaded; then
        echo "LaunchAgent: not loaded"
        echo "Plist      : ${PLIST_PATH}"
        return 1
    fi
    pid="$(launchd_pid || true)"
    state="$(launchd_state || true)"
    if [ -f "${SOURCE_DUMP_CONFIG}" ]; then
        selected="$(head -n 1 "${SOURCE_DUMP_CONFIG}")"
    elif [ -f "${DUMP_CONFIG}" ]; then
        selected="$(head -n 1 "${DUMP_CONFIG}")"
    fi
    echo "LaunchAgent: loaded"
    echo "State      : ${state:-unknown}"
    echo "PID        : ${pid:-restarting}"
    echo "Dump       : ${selected:-not selected}"
    echo "Log        : ${LOG}"
    echo "Launchd log: ${LAUNCHD_LOG}"
}

stop_launchd() {
    local old_pid=""
    if launchd_loaded; then
        old_pid="$(launchd_pid || true)"
        launchctl bootout "${SERVICE_TARGET}"
        for _ in $(seq 1 15); do
            if ! launchd_loaded && { [ -z "${old_pid}" ] || ! kill -0 "${old_pid}" 2>/dev/null; }; then
                break
            fi
            sleep 1
        done
        if launchd_loaded || { [ -n "${old_pid}" ] && kill -0 "${old_pid}" 2>/dev/null; }; then
            echo "ERROR: ${LABEL} did not stop within 15s." >&2
            return 1
        fi
        echo "Stopped ${LABEL}. KeepAlive is disabled until the next ./run.sh start."
    else
        echo "${LABEL} is already stopped."
    fi
    rm -f "${PID_FILE}"
}

run_legacy() {
    local dump_path="" pid="" command_line="" current_dump=""
    case "${ACTION}" in
        logs)
            touch "${LOG}"
            tail -n 30 -f "${LOG}"
            return
            ;;
        status)
            if [ -f "${PID_FILE}" ]; then
                pid="$(tr -cd '0-9' < "${PID_FILE}")"
            fi
            if [ -n "${pid}" ] && kill -0 "${pid}" 2>/dev/null; then
                echo "Legacy conductor running with PID ${pid}."
                return
            fi
            echo "Legacy conductor is stopped."
            return 1
            ;;
        stop)
            if [ -f "${PID_FILE}" ]; then
                pid="$(tr -cd '0-9' < "${PID_FILE}")"
            fi
            if [ -n "${pid}" ] && kill -0 "${pid}" 2>/dev/null; then
                kill "${pid}"
                echo "Stop requested for legacy conductor PID ${pid}."
            else
                echo "Legacy conductor is already stopped."
            fi
            return
            ;;
    esac

    dump_path="$(select_dump "${REQUESTED_DUMP}")"
    if [ -f "${PID_FILE}" ]; then
        pid="$(tr -cd '0-9' < "${PID_FILE}")"
    fi
    if [ -n "${pid}" ] && kill -0 "${pid}" 2>/dev/null; then
        command_line="$(ps -p "${pid}" -o command= 2>/dev/null || true)"
        current_dump="$(printf '%s\n' "${command_line}" | sed -nE 's/.* --dump ([^ ]+).*/\1/p')"
        if [ "${ACTION}" = "restart" ] || { [ -n "${current_dump}" ] && [ "${current_dump}" != "${dump_path}" ]; }; then
            kill "${pid}"
            for _ in $(seq 1 30); do
                kill -0 "${pid}" 2>/dev/null || break
                sleep 1
            done
        else
            echo "Legacy conductor is already running with PID ${pid}."
            if [ "${ACTION}" = "run" ]; then
                tail -n 30 -f "${LOG}"
            fi
            return
        fi
    fi

    local args=(
        --dump "${dump_path}" --headless --watcher-tabs 8 --poll-interval 15
        --ad-duration 120 --auto-training --training-poll-interval 60 --log "${LOG}"
    )
    if [ -f "${HAR_PROFILE}" ]; then
        args+=(--training-har-profile "${HAR_PROFILE}")
    fi
    cd "${SCRIPT_DIR}"
    nohup "${PYTHON_BIN}" osm_ad_bot_conductor.py "${args[@]}" </dev/null >/dev/null 2>&1 &
    pid=$!
    printf '%s\n' "${pid}" > "${PID_FILE}"
    echo "Legacy conductor started with PID ${pid}."
    if [ "${ACTION}" = "run" ]; then
        tail -n 30 -f "${LOG}"
    fi
}

if [ "${OSM_USE_LAUNCHD:-1}" = "0" ]; then
    run_legacy
    exit $?
fi

case "${ACTION}" in
    stop)
        stop_launchd
        exit 0
        ;;
    status)
        print_status
        exit $?
        ;;
    logs)
        touch "${LOG}"
        tail -n 30 -f "${LOG}"
        exit 0
        ;;
esac

if [ ! -x "${RUNNER}" ]; then
    echo "ERROR: launchd runner is missing or not executable: ${RUNNER}" >&2
    exit 1
fi
if [ ! -x "${PYTHON_BIN}" ]; then
    echo "ERROR: Python executable not found: ${PYTHON_BIN}" >&2
    exit 1
fi

SOURCE_DUMP_PATH="$(select_dump "${REQUESTED_DUMP}")"
STAGE_CHANGED="$(stage_dump_for_launchd "${SOURCE_DUMP_PATH}")"
DUMP_PATH="${STAGED_DUMP}"
DUMP_CHANGED="$(write_dump_config "${DUMP_PATH}")"
PLIST_CHANGED="$(install_or_update_agent)"

if [ "${PLIST_CHANGED}" = "0" ]; then
    if [ "${ACTION}" = "restart" ] || [ "${DUMP_CHANGED}" = "1" ] || [ "${STAGE_CHANGED}" = "1" ]; then
        launchctl kickstart -k "${SERVICE_TARGET}"
    elif [ -z "$(launchd_pid || true)" ]; then
        launchctl kickstart "${SERVICE_TARGET}"
    fi
fi

PID="$(wait_for_launchd_pid)"
echo "=========================================="
echo "  OSM Ad Bot — launchd KeepAlive"
echo "=========================================="
echo "State    : running"
echo "PID      : ${PID}"
echo "Dump     : ${SOURCE_DUMP_PATH}"
echo "Log      : ${LOG}"
echo "Training : automatic, forecast-aware (60s poll)"
echo "KeepAlive: enabled; system sleep is not prevented"
echo "Stop     : ./run.sh stop"
echo "Status   : ./run.sh status"
echo ""

if [ "${ACTION}" = "run" ]; then
    echo "Press Ctrl+C to stop following logs; launchd keeps the bot running."
    echo ""
    tail -n 30 -f "${LOG}"
fi
