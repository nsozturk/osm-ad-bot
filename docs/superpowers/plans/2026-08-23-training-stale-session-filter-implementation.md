# Training Stale Session Filter Implementation Plan

**Date:** 2026-08-23
**Design:** `docs/superpowers/specs/2026-08-23-training-stale-session-filter-design.md`

## Checklist

- [x] Add unit tests for active, claimed, finished, and incomplete sessions.
- [x] Add reconciliation coverage proving stale sessions do not block refill.
- [x] Add state-change-only occupancy logging coverage.
- [x] Implement a reusable active-session classifier.
- [x] Build occupied trainer/player sets only from active sessions.
- [x] Preserve claim-first flow and universal coach behavior.
- [x] Run focused automatic-training tests.
- [x] Run the complete test suite.
- [x] Restart the launchd-managed bot.
- [x] Verify the new PID, 60-second poll, occupancy status log, and refill outcome.
