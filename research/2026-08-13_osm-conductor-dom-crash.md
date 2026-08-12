# OSM Conductor DOM Crash Investigation

**Date:** 2026-08-13
**Topic:** osm-conductor-dom-crash

## Summary

The fatal error was caused by an unguarded `.length` read on a page-scoped queue after OSM replaced the conductor document. The fix makes the observer idempotent, detects both replaced JavaScript globals and replaced `<body>` nodes, restores observation automatically, and treats transient Playwright evaluation errors as a non-fatal loss of the optional DOM signal.

## Findings

### Progress

- [x] Traceback mapped to the exact JavaScript expression.
- [x] Lifecycle and navigation paths reviewed.
- [x] Minimal backward-compatible repair designed.
- [x] Repair verified with targeted tests.

### Root cause

- `_read_dom_cooldown()` assigned `window.__osm_toast_queue` to `q` and immediately read `q.length`.
- The queue and its MutationObserver existed only in the current browser document. A reload/navigation replaced `window`, making the queue undefined. Replacing only the body could also leave an observer object present but attached to a stale body.
- The optional DOM fallback had no exception boundary, so its failure cancelled all watcher tasks and terminated the conductor.

### Repair

- Observer installation now disconnects any old observer before replacing it and preserves an existing queue.
- The observer records the body it watches; reads verify that it is still attached to the current body.
- Missing queue, missing observer, stale body, or transient evaluation failure returns no DOM limit for that poll and attempts automatic restoration.
- Restoration failure is logged once and remains non-fatal; the API rate-limit check continues to be the primary signal.

### Verification

- Six async unit tests cover missing, empty, populated, transient-read-error, idempotent-install, and transient-install-error paths.
- A real headless Chromium smoke test detected a replaced body, restored the observer, and successfully read a later toast.
- Python compilation, Bash syntax, and Git whitespace checks passed. No live ad session was started.

## Sources

- `/Users/ns0bj/Development/Fun/osm/osm_ad_bot_conductor.py`
- User-provided runtime traceback from 2026-08-13 00:16:21.
