# Watcher Page Lifecycle Design

**Date:** 2026-08-24
**Status:** Approved by delegated user authority

## Problem

Watcher pages that fail during navigation or readiness checks are never added
to `watcher_pages` and are never closed. Repeated failures leak pages across
cycles, increasing browser memory pressure and making later navigation and ad
interaction progressively slower.

StorageDump origin pages have the same failure-path defect: they close only
after successful navigation and injection, so a failed origin can leak a page
before the conductor is opened.

## Selected Approach

Use explicit page ownership plus a final context sweep:

1. `_open_watchers()` owns each page from `new_page()` until it either hands
   the page to a watcher task or closes it after failure.
2. `StorageLoader.inject()` closes each temporary origin page in a `finally`
   path regardless of navigation or evaluation outcome.
3. `_close_all_watchers()` cancels and awaits all watcher tasks, closes tracked
   watcher pages, then closes every remaining context page except the conductor.
4. Cleanup logs page counts before and after the sweep.
5. If cleanup cannot return to a conductor-only baseline, it logs a warning;
   it does not silently accumulate pages or immediately destroy the context.

This combines precise local cleanup with a defensive recovery seam. Closing
only failed pages would fix the known path but would not recover pages leaked by
future lifecycle mistakes. Recreating the entire browser context on every cycle
would be more disruptive and would complicate token/session continuity.

## Lifecycle Rules

- A page created for a watcher must be either tracked or closed before the
  corresponding loop iteration ends.
- A temporary StorageDump origin page must close even when navigation,
  evaluation, or storage assignment fails.
- A page is appended to `watcher_pages` only after navigation and readiness
  succeed.
- If task creation fails after tracking, the page is removed and closed.
- Cleanup awaits task cancellation before closing pages to avoid task/page
  races.
- The conductor page is the only protected page during end-of-cycle cleanup.
- Closed pages and close failures are handled idempotently.

## Compatibility and Live Impact

- Ad selection, reward handling, cooldown logic, training, tokens, and request
  payloads remain unchanged.
- Active training sessions are not cancelled or modified.
- Restarting the bot clears the pages already leaked by the old process.
- The change affects only page resource ownership and diagnostics.

## Tests

- A navigation failure closes the newly created page.
- A readiness failure closes the newly created page.
- A StorageDump origin failure closes its temporary page.
- A successfully opened watcher remains tracked and starts one task.
- Cleanup cancels and awaits tasks, closes tracked pages, and clears tracking.
- Cleanup closes an untracked stray page but preserves the conductor.
- Repeated cleanup is safe and retains the conductor-only baseline.

## Live Verification

After focused and full tests pass, restart the LaunchAgent and verify:

- a new conductor PID and healthy browser startup;
- context page count returns to one after watcher cleanup;
- page count does not rise across at least two cleanup observations;
- process RSS does not show unbounded growth;
- at least one reward is confirmed after restart, unless OSM itself exposes an
  explicit rate limit or ad inventory failure.
