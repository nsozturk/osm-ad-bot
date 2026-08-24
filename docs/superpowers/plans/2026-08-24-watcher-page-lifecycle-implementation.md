# Watcher Page Lifecycle Implementation Plan

**Date:** 2026-08-24
**Design:** `docs/superpowers/specs/2026-08-24-watcher-page-lifecycle-design.md`

## Checklist

- [ ] Add reusable fake context/page/task test fixtures.
- [ ] Add StorageDump failed-origin page-close regression tests.
- [ ] Add failed-navigation page-close regression test.
- [ ] Add failed-readiness page-close regression test.
- [ ] Add successful watcher ownership test.
- [ ] Add tracked and stray page cleanup tests.
- [ ] Implement failure-safe watcher page ownership.
- [ ] Implement failure-safe StorageDump origin page ownership.
- [ ] Await watcher task cancellation during cleanup.
- [ ] Sweep non-conductor stray context pages.
- [ ] Add before/after page-count cleanup diagnostics.
- [ ] Run focused lifecycle tests.
- [ ] Run the complete test suite and compile checks.
- [ ] Restart the launchd-managed bot.
- [ ] Verify PID, page-count baseline, RSS trend, and reward flow.
