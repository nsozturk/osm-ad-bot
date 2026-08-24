# Watcher Page Lifecycle Implementation Plan

**Date:** 2026-08-24
**Design:** `docs/superpowers/specs/2026-08-24-watcher-page-lifecycle-design.md`

## Checklist

- [x] Add reusable fake context/page/task test fixtures.
- [x] Add StorageDump failed-origin page-close regression tests.
- [x] Add failed-navigation page-close regression test.
- [x] Add failed-readiness page-close regression test.
- [x] Add successful watcher ownership test.
- [x] Add tracked and stray page cleanup tests.
- [x] Implement failure-safe watcher page ownership.
- [x] Implement failure-safe StorageDump origin page ownership.
- [x] Await watcher task cancellation during cleanup.
- [x] Sweep non-conductor stray context pages.
- [x] Add before/after page-count cleanup diagnostics.
- [x] Add bounded-close timeout regression coverage.
- [x] Apply bounded close to watcher, scout, and defensive cleanup paths.
- [x] Add whole-ad-attempt timeout regression coverage.
- [x] Bound scout and watcher ad attempts while preserving the real-ad wait.
- [x] Run focused lifecycle tests.
- [x] Run the complete test suite and compile checks.
- [ ] Restart the launchd-managed bot.
- [ ] Verify PID, page-count baseline, RSS trend, and reward flow.
