# OSM Age- and Forecast-Aware Training Priority Design

**Date:** 2026-08-14
**Status:** Approved design

## Goal

Refine automatic player selection so training favors players who combine high expected progression with useful development age. A very young player must not be selected merely because of age when the player's current level is too low, while an older player may still be selected when the server forecast makes that choice clearly worthwhile.

This change affects only candidate ranking and eligibility inside automatic training. Ad watching, training claim/start lifecycle, authentication, timer selection, and spending safeguards remain unchanged.

## Live Compatibility

The running conductor remains on the existing selection behavior until a controlled restart. The updated code is additive within the candidate-selection layer and does not change CLI arguments, API payloads, stored data, or the behavior of direct conductor invocations without `--auto-training`.

`run.sh` continues to start one process containing both the ad conductor and automatic training manager. A training-selection failure must remain isolated from the ad loop.

## Eligibility Rules

The existing exclusions remain mandatory:

- Exclude players who are already training.
- Exclude injured players.
- Exclude players listed for transfer.
- Exclude players at the maximum relevant stat.
- Require a positive forecast for the trainer being filled.
- Require the normal trainer's position; the universal trainer may consider every position.

Add a current-level floor based on the player's relevant main stat:

- Outfield players: minimum 50.
- Goalkeepers: minimum 40.

Players below these floors are ineligible regardless of age or forecast. If no player meets the floor for a trainer, the trainer remains empty and the reason is logged. The floor is not relaxed as a fallback.

## Priority Score

For every eligible player, calculate:

```text
priority_score = forecast * age_multiplier
```

Age multipliers:

| Age | Multiplier | Intent |
|---|---:|---|
| 21 or younger | 1.25 | Strong development preference |
| 22–24 | 1.15 | Development preference |
| 25–28 | 1.00 | Neutral prime-age baseline |
| 29–31 | 0.80 | Veteran penalty |
| 32 or older | 0.60 | Strong veteran penalty |

Forecast remains the source of truth for expected immediate progression. Age modifies priority but does not become an absolute ban: an older player can outrank a younger player when the forecast advantage is large enough. If an older player is the only eligible candidate above the current-level floor, the player may be selected so the trainer does not remain idle unnecessarily.

## Candidate Pool and Choice

For each empty trainer:

1. Build the eligible candidate list.
2. Calculate each candidate's priority score.
3. Sort by descending priority score, then descending forecast, then ascending age, then descending relevant main stat, then player ID for deterministic ordering.
4. Let `best_score` be the highest priority score.
5. Keep at most five candidates whose score is at least 90% of `best_score`.
6. Choose from that pool with weight `priority_score²`.

The narrow top band preserves limited variety without allowing a materially weaker candidate to win frequently. Repeated training remains self-correcting because the latest server forecast is fetched before every selection pass; when expected gain drops, the player's score and selection probability drop with it.

The universal trainer uses `forecastUniversal` with the same eligibility floors, age multipliers, top-band rule, and weighted selection.

## Logging and Failure Behavior

Successful selection logs include trainer ID, player name and ID, relevant main stat, age, forecast, and rounded priority score. Empty-slot logs distinguish between:

- no positive forecast candidate;
- all candidates excluded by current-level floor;
- all candidates occupied, injured, listed, or maxed.

Logs must never include request headers, cookies, tokens, raw HAR bodies, or StorageDump content.

An invalid player field is treated conservatively: missing age receives the strongest veteran penalty, while a missing relevant stat fails the minimum-level check. Candidate-ranking errors skip only that trainer/pass and do not terminate the training manager or ad conductor.

## Implementation Boundaries

The change should remain localized to training candidate construction and selection. A candidate data object may gain `main_stat`, `age_multiplier`, and `priority_score` fields so ranking and logging do not recompute them inconsistently.

No persistent training history, database, new API endpoint, player purchase, timer boost, Boss Coin conversion, or automatic transfer action is introduced.

## Verification

Unit tests must prove:

- A very young outfield player below 50 is excluded even with the highest forecast.
- A goalkeeper below 40 is excluded.
- A young average-level player outranks an older player with the same forecast.
- An older player can outrank a younger player when the forecast advantage is sufficiently large.
- An eligible older player can be selected when no younger eligible player exists.
- No below-floor fallback occurs when every candidate is too weak.
- The 90% pool limit and weighted selection remain deterministic under a seeded random generator.
- Existing occupied, injured, listed, maximum-stat, position, claim, and non-fatal-loop tests continue to pass.

Run the full test suite, Python syntax compilation without tracked bytecode, shell syntax checks, and `git diff --check`. Before a live restart, verify that no HAR, StorageDump, token cache, ignored runtime JSON, or credential value is included in the commit.

## Success Criteria

- Young players receive a meaningful advantage only after meeting the current-level floor.
- Server forecast remains the dominant progression signal.
- Older players are disfavored but not categorically blocked.
- Low-level prospects are never selected as a fallback.
- The ad conductor continues running independently of training selection outcomes.
- A controlled restart activates the new logic without changing the one-process `run.sh` workflow.
