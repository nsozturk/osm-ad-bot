# OSM Launchd KeepAlive Implementation Plan

**Date:** 2026-08-16

- [x] Add a launchd-owned runner that selects the configured/latest dump and `exec`s the conductor.
- [x] Refactor `run.sh` into launchd start/restart/stop/status/logs control while retaining the legacy fallback.
- [x] Generate and validate a credential-free user LaunchAgent plist.
- [x] Update README usage, lifecycle, sleep, and stop semantics.
- [x] Add regression tests for command routing and launchd configuration contracts.
- [x] Install the LaunchAgent and verify start, KeepAlive restart, stop, restart, training, and ad activity.
- [x] Verify secret exclusions and final repository/runtime state.
