# OSM Watcher Page Leak Investigation

**Date:** 2026-08-24
**Topic:** osm-watcher-page-leak

## Summary

The page growth came from failed watcher setup and temporary StorageDump origin pages escaping ownership and cleanup. The lifecycle is now bounded end to end: failed and stray pages are swept, Playwright operations have watchdogs, storage is installed through a context init script without temporary tabs, and default watcher concurrency is four. Live verification restored the browser context to the conductor-only baseline and confirmed reward flow.

## Findings

### Runtime state

- LaunchAgent is loaded and the conductor is running as PID 41773.
- The Playwright Chromium process is also alive.
- The last confirmed reward during inspection was at 22:58:14, increasing the total to 179.
- The current cycle continued opening watcher tabs, so the bot was degraded rather than stopped.

### Leak evidence

- Context page count was stable at 11 for many cycles.
- It then grew to 13 at 19:38:30, 15 at 20:07:49, 22 at 20:44:22, and 26 at 21:39:40.
- During the same period, watcher creation increasingly failed with `Page.goto` and `Page.wait_for_selector` timeouts, plus wallet/shop interaction failures.

### Root cause

`_open_watchers()` creates a page, navigates it, waits for `#page-content`, and only then appends it to `self.watcher_pages`. If navigation or readiness fails, the exception is logged but the newly created page is not closed. `_close_all_watchers()` only closes pages present in `self.watcher_pages`, so failed untracked pages survive every cycle.

The StorageDump injector has the same ownership defect. Its local-storage and session-storage origin loops close pages only on the success path. A failed `goto` or `evaluate` can therefore leave startup pages behind, which explains the long-running baseline of 11 pages before watcher failures raised the count further.

Live verification exposed a related close-path stall: after a scout navigation timeout, an unbounded `page.close()` call prevented the conductor from advancing to the next cycle. Page cleanup therefore also needs a short timeout so an unresponsive renderer cannot freeze the lifecycle manager.

### Required correction

- Close a newly created watcher page in every failed-open path.
- Close every StorageDump injection page in a `finally` path.
- Await cancelled watcher tasks before clearing task tracking.
- At cycle cleanup, close every non-conductor page left in the browser context.
- Bound page-close operations so an unresponsive renderer cannot block the conductor indefinitely.
- Log page counts before and after cleanup and fail loudly if the expected conductor-only baseline cannot be restored.
- Add regression tests for failed navigation, failed selector readiness, tracked watcher cleanup, and stray-page cleanup.

### Implemented and verified

- Watcher pages are prepared before their ad tasks start; failed setup paths close their page.
- Every cycle cancels and awaits watcher tasks, closes tracked pages, then sweeps stray context pages.
- Whole ad attempts, page creation, page close, and conductor DOM checks have finite timeouts.
- StorageDump local/session storage is filtered to OSM origins and applied with `BrowserContext.add_init_script`; no storage-only pages are created.
- Default concurrency is four and remains configurable through `OSM_WATCHER_TABS`.
- The complete suite passes: 49 tests.
- Live cleanup logged `pages before=2, tracked_closed=0, stray_closed=1, after=1`.
- Final LaunchAgent PID `21489` started with four watchers, injected storage in the same second, reported healthy training reconciliation, and confirmed a scout reward at `00:25:29`.

## Sources

- `/Users/ns0bj/Development/Fun/osm/osm_ad_bot_conductor.py`
- `/Users/ns0bj/Development/Fun/osm/tmp/osm-runtime/conductor.log`
- `/Users/ns0bj/Development/Fun/osm/run.sh status`
- Local process inspection for PID 41773 and its Playwright Chromium child
