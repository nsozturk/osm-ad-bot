# Watcher Page Lifecycle Implementation Plan

**Date:** 2026-08-24
**Design:** `docs/superpowers/specs/2026-08-24-watcher-page-lifecycle-design.md`

## Checklist

- [x] Add reusable fake context/page/task test fixtures.
- [x] Add StorageDump origin-filtering and init-script regression tests.
- [x] Add failed-navigation page-close regression test.
- [x] Add failed-readiness page-close regression test.
- [x] Add successful watcher ownership test.
- [x] Add tracked and stray page cleanup tests.
- [x] Implement failure-safe watcher page ownership.
- [x] Eliminate temporary StorageDump origin pages with a context init script.
- [x] Await watcher task cancellation during cleanup.
- [x] Sweep non-conductor stray context pages.
- [x] Add before/after page-count cleanup diagnostics.
- [x] Add bounded-close timeout regression coverage.
- [x] Apply bounded close to watcher, scout, and defensive cleanup paths.
- [x] Add whole-ad-attempt timeout regression coverage.
- [x] Bound scout and watcher ad attempts while preserving the real-ad wait.
- [x] Add hanging watcher page-creation regression coverage.
- [x] Bound watcher `new_page()` protocol calls.
- [x] Add prepare-before-start watcher ordering coverage.
- [x] Separate watcher page preparation from task activation.
- [x] Make watcher concurrency configurable with a default of four.
- [x] Bound conductor DOM rate-limit reads so polling cannot deadlock cleanup.
- [x] Run focused lifecycle tests.
- [x] Run the complete test suite and compile checks.
- [x] Restart the launchd-managed bot.
- [x] Verify PID, page-count baseline, RSS trend, and reward flow.

## Live Verification

- LaunchAgent PID `21489` reached `running` with four watcher tabs.
- Storage injection completed without opening temporary pages and finished in the same second.
- Scout reward was confirmed at `00:25:29`.
- All four watcher pages were prepared before any watcher task started.
- Cleanup restored the context to `after=1` (conductor only).
- Conductor RSS remained near 155-158 MB during startup, scout, and watcher preparation.
