# OSM Launchd KeepAlive Design

**Date:** 2026-08-16
**Status:** Approved by the user's direct `launchd KeepAlive eklesene` request and prior no-questions preference

## Goal

Run the combined OSM ad and automatic-training conductor continuously while the Mac is awake, without tying its lifetime to a terminal, Codex PTY, or `tail -f` process. Normal macOS sleep must remain allowed. After wake, the process should continue or be restarted by launchd if it exited.

## Chosen Approach

Use a per-user LaunchAgent with `RunAtLoad=true` and `KeepAlive=true`. A small repository-owned runner resolves the selected StorageDump and then uses `exec` to replace itself with the Python conductor. This makes the conductor the process launchd directly supervises.

Alternatives rejected:

- Stronger `nohup` or shell disowning remains vulnerable to terminal/process-group cleanup.
- A shell watchdog dies with the same terminal or parent shell it is intended to outlive.
- A system LaunchDaemon would require root and is unnecessary for a user-owned browser automation job.

## Components

### `run.sh`

Acts as the user-facing controller.

- Default invocation: ensure the LaunchAgent is installed/running, then follow the live conductor log.
- `start [dump]`: install/update and start without following logs.
- `restart [dump]`: update the selected dump and force a controlled launchd restart.
- `stop`: unload the LaunchAgent so `KeepAlive` does not immediately restart it.
- `status`: report launchd state, PID, selected dump, and log path without exposing credentials.
- `logs`: follow the conductor log only.
- `OSM_USE_LAUNCHD=0`: preserve the legacy direct background-launch fallback.

The selected dump is staged as a mode-`0600` copy in the ignored runtime directory because a background LaunchAgent does not inherit Terminal's Downloads-folder privacy grant. Token contents are never printed or added to the plist.

### `launchd/osm-ad-bot-runner.sh`

Reads the selected dump path or finds the newest valid StorageDump in the configured Downloads directory. It builds the same conductor arguments currently used by `run.sh`, writes its PID to the ignored runtime PID file, and `exec`s the configured Python interpreter.

### Installed LaunchAgent

`run.sh` generates and validates `~/Library/LaunchAgents/dev.nsozturk.osm-ad-bot.plist` using project-local scratch space before installation.

Properties:

- Label: `dev.nsozturk.osm-ad-bot`
- `RunAtLoad`: true
- `KeepAlive`: true
- `ProcessType`: Background
- `ThrottleInterval`: 15 seconds
- Working directory: repository root
- Wrapper stdout/stderr: ignored runtime launchd log
- No secrets or token values in the plist

The plist records the absolute repository, runner, Python, Downloads, log, and HAR paths required by launchd's restricted environment.

## Lifecycle and Data Flow

1. `run.sh` selects an explicit dump or the newest valid dump.
2. It copies the dump to the ignored runtime directory with mode `0600` and stores the source/runtime paths there.
3. It generates and validates the LaunchAgent plist.
4. It unloads/reloads only when the plist or dump selection changes; otherwise it reuses the existing job.
5. launchd starts the runner, which `exec`s the conductor.
6. If the conductor exits or is killed, launchd restarts it after throttling.
7. `run.sh stop` calls `bootout`, disabling restart until the next start.

During system sleep macOS pauses normal user processes. This design does not use `caffeinate` and does not prevent sleep. launchd resumes supervision after wake.

## Error Handling

- Missing dump: runner exits with a clear path-only error; launchd retries at the throttle interval.
- Invalid plist: installation stops before changing the loaded job.
- Stale manual conductor: controller sends SIGTERM and waits before loading launchd, preventing duplicates.
- Repeated crashes: launchd throttles restart attempts; logs remain in `tmp/osm-runtime/`.
- Manual `kill <pid>`: `KeepAlive` intentionally restarts the job; use `./run.sh stop` for a persistent stop.

## Backward Compatibility

Existing `./run.sh [dump]` behavior remains: it starts the combined ad/training bot and follows logs, and Ctrl+C only stops following logs. The stop instruction changes from `kill <pid>` to `./run.sh stop` because direct kills are now auto-restarted. Non-launchd execution remains available through `OSM_USE_LAUNCHD=0`.

## Verification

- Shell syntax checks for controller and runner.
- `plutil -lint` on the generated LaunchAgent.
- launchctl state and PID verification after start.
- Kill the supervised conductor and verify launchd assigns a new PID.
- Verify current dump path, `CONDUCTOR STARTED`, training health, and ad/scout activity in the live log.
- Verify `stop` unloads the job and leaves no conductor process.
- Restart after the stop verification and leave the job running.
- Confirm no HAR, ZIP, token, runtime file, or client secret is tracked.
