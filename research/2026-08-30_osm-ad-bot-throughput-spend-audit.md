# OSM ad bot throughput and spending audit

**Date:** 2026-08-30
**Topic:** osm-ad-bot-throughput-spend-audit

## Summary

The active bot is supervised by the per-user LaunchAgent `dev.nsozturk.osm-ad-bot`, not by a separate live `nohup` process. Its running process is the five-day-old conductor and writes to `tmp/osm-runtime/conductor.log`; a `nohup` fallback exists in `run.sh` only when `OSM_USE_LAUNCHD=0`, and that fallback discards stdout/stderr to `/dev/null`.

On 2026-08-29 the conductor counter increased from 702 to 862, or 160 claimed rewards. This is moderately below the preceding 177 on 2026-08-28, but the number is not proof of 160 completed ad impressions or 160 credited BossCoins: the current code dispatches fake completion callbacks and then counts a matching DOM element as a reward without verifying a server-side reward/finance delta.

## Findings

### Active background runtime and logs

- `launchctl` shows the loaded `dev.nsozturk.osm-ad-bot` service. The active conductor process has parent PID 1 and stdout/stderr attached to `tmp/osm-runtime/launchd.log`; its own structured output is appended to `tmp/osm-runtime/conductor.log`.
- No active process command contains `nohup`, and no current `nohup.out` or project-local nohup log exists. `run.sh` has a legacy fallback at its direct-background branch, but it is not the active route and deliberately sends its output to `/dev/null`.
- The current conductor was started shortly after 00:24 on 2026-08-25 with four watcher tabs, 15-second poll intervals, a minimum 120-second ad wait, and automatic training enabled.

### What the advertised "watched" counter actually proves

- After clicking the Watch ad UI, `_watch_single_ad` invokes browser-side fake completion callbacks/events (`invokeApplixirVideoUnit`, a rewarded-video handler, and completion event names).
- It increments `stats["watched"]` when either `.modal-dialog .reward-container` or `.consumable-image-tile` is found in a ten-second probe window. There is no impression receipt, ad-network callback validation, or before/after balance check.
- `print_summary` then renders `BossCoins Earned ~ watched`; the tilde is appropriate, but the metric is still only an in-process DOM-based approximation. A process restart resets it.

### Spending and other state-changing behavior

- No purchase, payment, transfer-buy, transfer-sell, or finance-write endpoint is called by the active conductor. Its rate-limit and finance-related reads are GET operations.
- `auto_training.py` does perform game-state mutations: it PUTs a completed training-session claim and POSTs a new training session for an eligible player. The module explicitly describes this as filling trainer slots without purchases, and it only reads `balanceandsavings`; it does not submit a budget/transfer/payment request.
- Therefore this is not "only tracking": it drives the reward UI and can start/claim training sessions. However, no code path found charges money or buys/sells players. Whether OSM itself applies an implicit in-game cost to a chosen training setting cannot be proven from this local code alone.

### 2026-08-29 throughput and failure signals

The date mapping is derived from the persistent conductor started on 2026-08-25 and the log's midnight time rollovers. The log records time-of-day rather than a full date per line.

| Date | Cumulative counter | Day delta |
|---|---:|---:|
| 2026-08-25 (started at 00:24) | 193 | 193 |
| 2026-08-26 | 355 | 162 |
| 2026-08-27 | 525 | 170 |
| 2026-08-28 | 702 | 177 |
| 2026-08-29 | 862 | 160 |

Within the inferred 2026-08-29 section, the log reports 160 local reward confirmations, 14 watcher setup failures, 14 bounded 210-second ad-attempt timeouts, six missing-wallet failures, 31 scout navigation errors, and 36 rate-limit detections. Sixty watcher batches were opened: 56 reached 4/4 ready tabs, while four were partial (one 1/4, one 2/4, two 3/4).

The most consequential instrumentation flaw is that `_scout_check()` returns the same `False` value for an unavailable ad/UI/network failure and for an actual rate limit. The loop then logs "Scout reported rate-limit" even when the immediately preceding check says no rate limit. This makes the failure diagnosis misleading and turns repeated navigation/slot failures into tight scout retries instead of a distinct retry/backoff state.

As of the morning of 2026-08-30, conditions are materially worse: the partial day contains 49 local confirmations alongside 90 watcher setup failures, 41 missing Watch-ad buttons, and 27 bounded ad timeouts. This points at OSM/page/ad-slot availability or navigation reliability, not an in-code spend/budget action.

## Sources

- Live process tree, `launchctl` service state, and open-file inspection on 2026-08-30.
- `tmp/osm-runtime/conductor.log` (active process log; locally inspected, not committed).
- `run.sh` and `launchd/osm-ad-bot-runner.sh` (background supervisor and fallback behavior).
- `osm_ad_bot_conductor.py` (reward heuristic, scout loop, rate-limit flow, watcher lifecycle).
- `auto_training.py` (training-session claim/start behavior and finance read).
