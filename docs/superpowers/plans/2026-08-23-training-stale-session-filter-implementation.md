# Training Stale Session Filter Implementation Plan

**Date:** 2026-08-23
**Design:** `docs/superpowers/specs/2026-08-23-training-stale-session-filter-design.md`

## Checklist

- [ ] Add unit tests for active, claimed, finished, and incomplete sessions.
- [ ] Add reconciliation coverage proving stale sessions do not block refill.
- [ ] Add state-change-only occupancy logging coverage.
- [ ] Implement a reusable active-session classifier.
- [ ] Build occupied trainer/player sets only from active sessions.
- [ ] Preserve claim-first flow and universal coach behavior.
- [ ] Run focused automatic-training tests.
- [ ] Run the complete test suite.
- [ ] Restart the launchd-managed bot.
- [ ] Verify the new PID, 60-second poll, occupancy status log, and refill outcome.
