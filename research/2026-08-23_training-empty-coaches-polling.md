# Automatic Training Empty Coaches and Polling

**Date:** 2026-08-23
**Topic:** training-empty-coaches-polling

## Summary

The automatic training manager is configured to reconcile all four normal coaches every 60 seconds and should fill every coach that the OSM API reports as unoccupied. A completed session is claimed first, then the ongoing-session list is refreshed and eligible players are selected. The current live log shows the manager running, but normal coaches are being silently treated as occupied by the API while the UI reportedly shows them as empty.

## Findings

### Intended behavior

- `run.sh` launches the conductor with `--auto-training --training-poll-interval 60`.
- Each successful reconciliation checks trainers 1 through 4 in order.
- A trainer reported as unoccupied is assigned the eligible position player with the highest positive forecast and a main stat of at least 90.
- Completed sessions are claimed before empty trainers are filled.

### Timing

- Normal healthy interval: 60 seconds.
- Therefore, after OSM exposes a completed slot consistently through the API, the expected refill latency is at most roughly 60 seconds plus API request time.
- On API/network failure, retry delay backs off from 60 to 120, 240, and at most 300 seconds. A successful pass resets it to 60 seconds.

### Current runtime evidence

- The running process uses `--training-poll-interval 60`.
- The manager log reports `poll every 60s` and later recovered from a transient network failure.
- At 18:52:21 it claimed completed session `532354772`.
- At 19:26:15 it attempted only trainer 5 (universal) and received HTTP 400.
- No current deterministic-selection start or no-candidate message appears for trainers 1 through 4.

### Likely state mismatch

In the current code, an ordinary trainer can be skipped without a log only when its trainer number appears in the API's `/trainingsessions/ongoing` response. If the visible Training page says `Select a player` for trainers 1 through 4 while the manager remains silent for those trainers, the API response used by the bot is still presenting those slots as occupied. This is a likely stale or already-claimed-session filtering issue, not a disabled polling loop.

## Sources

- `/Users/ns0bj/Development/Fun/osm/auto_training.py`
- `/Users/ns0bj/Development/Fun/osm/run.sh`
- `/Users/ns0bj/Development/Fun/osm/tmp/osm-runtime/conductor.log`
- Running process arguments for PID 10877
