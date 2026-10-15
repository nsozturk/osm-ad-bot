# OSM Ad Watcher Error Review

**Date:** 2026-08-30
**Topic:** ad-watcher-error-review

## Summary

The redacted runtime log shows intermittent Training-page navigation and selector timeouts, followed by page-close timeouts. The close implementation cancelled its own in-flight Playwright close operation on timeout, allowing stalled pages to remain in the shared browser context; this is a plausible local cause of later navigation failures. The repair keeps the caller bounded while allowing page cleanup to complete in the background, without changing any ad-completion logic.

## Findings

### Observed failures

- Scout and watcher setup periodically time out on Training navigation or `#page-content` readiness.
- Several scout/watcher close operations time out after five seconds.
- The context cleanup report can retain a non-conductor page after those timeouts.

### Root cause and bounded repair

- `asyncio.wait_for(page.close(), timeout=...)` cancels the underlying close coroutine on timeout.
- The repair wraps a dedicated close task with `asyncio.shield`, so the caller returns after the same timeout but the browser remains free to finish closing the page.
- Completion tasks are retained until done and any actual background-close exception is logged.
- Browser startup is also bounded at 45 seconds, so a stuck Playwright driver does not leave the LaunchAgent falsely healthy forever.

### Scope boundary

No code that clicks ads, dispatches reward callbacks, or determines rewards was changed.

### Restart verification state

- The full local suite passes after the repair (54 tests).
- A clean LaunchAgent restart removed the orphaned Playwright driver created by the earlier forced shutdown.
- The subsequent LaunchAgent Python process stalled during interpreter initialization, before the bot emitted `Launching browser...`; a direct Python startup with the same sanitized environment succeeded. This is a current launchd-session problem rather than an ad-watcher code path, so no active watcher cycle is claimed for this restart.

### LaunchAgent repair

- The agent used the `Background` ProcessType, whose documented resource limits can defer background work. The plist now uses `Standard`; browser/tab limits remain enforced by the bot itself.
- `run.sh` now accepts only a PID whose process command is the conductor as a successful start. An `xpcproxy` PID can no longer be reported as a running bot.
- Verification after the change: the LaunchAgent has a real conductor PID, the Training page is ready, and Cycle #1 started successfully.

## Sources

- Local runtime log: `tmp/osm-runtime/conductor.log`
- Local source: `osm_ad_bot_conductor.py`
