# Training Stale Session Filter Design

**Date:** 2026-08-23
**Status:** Approved for specification review

## Problem

The Training page can show a normal coach as empty while
`/trainingsessions/ongoing` still returns an old session for that coach. The
current reconciliation loop treats every returned session as active when it
builds `occupied_trainers` and `occupied_players`. As a result, an already
claimed or already finished session can silently block an otherwise empty
coach from being refilled.

## Goals

- Fill all genuinely empty normal coaches during the same reconciliation pass.
- Never disturb a genuinely active training session.
- Tolerate stale claimed or finished records in the ongoing-session response.
- Log coach occupancy only when it changes, avoiding one log entry per coach
  every minute.
- Preserve the existing 60-second healthy polling interval and bounded retry
  backoff on API failures.

## Non-goals

- Do not use DOM scraping as a second source of truth.
- Do not cancel or replace active training sessions.
- Do not change player eligibility, forecast ranking, timer IDs, or universal
  coach entitlement rules.
- Do not add fixed sleeps after claim requests.

## Design

### Session classification

Introduce a focused helper that classifies sessions returned by the ongoing
endpoint. A session occupies its trainer and player only when all of the
following are true:

1. It is not marked claimed.
2. It has not reached its finished timestamp according to the greatest of the
   local time and the API-provided current timestamp.
3. It contains a valid trainer and player identifier.

Claimed sessions and sessions whose finished timestamp has passed are stale for
occupancy purposes. They remain available to the existing claim phase, but do
not enter the occupied trainer/player sets used for refill decisions.

If a session has no usable finished timestamp, it is treated conservatively as
active when it is unclaimed and has valid identifiers. This protects older API
payload shapes and avoids replacing a live session accidentally.

### Reconciliation flow

Each pass keeps the existing order:

1. Fetch ongoing sessions.
2. Claim every unclaimed session whose timer has finished.
3. Refresh ongoing sessions after any claim attempt succeeds or is already
   resolved.
4. Build occupied trainer/player sets from active sessions only.
5. For trainers 1 through 4, select and start the deterministic maximum-forecast
   eligible player when the trainer is not occupied.
6. Apply the same active-session occupancy set to the existing universal coach
   probe without changing entitlement behavior.

This means a stale session that remains in the refreshed API response cannot
block a same-pass refill.

### State-change logging

Track the last observed active occupancy signature for trainers 1 through 4.
Log a compact status line only when that signature changes. The line identifies
which normal trainers are active and which are empty, without exposing tokens
or other credentials. Existing start, skip, claim, recovery, and error logs
remain unchanged.

## Error Handling and Compatibility

- API/network failures continue using the existing 60, 120, 240, then maximum
  300-second retry backoff.
- Unknown or incomplete unclaimed sessions are treated as active when they have
  valid trainer/player IDs, favoring safety over aggressive refill.
- The change is backward compatible with existing saved sessions and live game
  state because it only excludes records that are already claimed or provably
  finished.
- No request payload or endpoint contract changes.

## Tests

Add focused unit and reconciliation tests covering:

- An unclaimed future session remains active and blocks refill.
- A claimed session is excluded from occupied trainer/player sets.
- An unclaimed session with a passed finished timestamp is claimable and does
  not block refill if it remains in the refreshed response.
- A missing finished timestamp is treated conservatively as active.
- Multiple empty normal trainers are refilled in a single pass.
- Occupancy logs are emitted on state change but not repeated every poll.
- Existing 90-inclusive deterministic forecast selection remains unchanged.

## Deployment Verification

After unit and full test suites pass:

1. Restart the launchd-managed bot through `run.sh`.
2. Confirm the LaunchAgent is loaded with a new running PID.
3. Confirm the training manager reports its 60-second polling interval.
4. Confirm a status-change log identifies the normal coach occupancy state.
5. Confirm any API-reported empty normal coach either starts an eligible player
   or logs the precise no-candidate/start-rejected reason.

Live verification will not cancel a currently active training session merely to
force an empty-slot event.
