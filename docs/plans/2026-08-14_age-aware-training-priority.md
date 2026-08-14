# Age-Aware Training Priority Implementation Plan

**Date:** 2026-08-14
**Design:** `/Users/ns0bj/Development/Fun/osm/docs/superpowers/specs/2026-08-14-osm-training-priority-design.md`

## Checklist

- [x] Add explicit minimum-stat, age-weight, and top-band constants.
- [x] Extend the training candidate model with stable scoring inputs and output.
- [x] Separate candidate eligibility diagnostics from the backward-compatible pool helper.
- [x] Rank candidates by forecast-adjusted age priority and use that score for weighted selection.
- [x] Log selection factors and precise empty-pool reasons without credential material.
- [x] Contain candidate-ranking failures to the affected trainer pass.
- [x] Add focused tests for low-level youth, goalkeeper floor, age preference, veteran override/fallback, top-band behavior, and diagnostics.
- [x] Run the full unit suite, Python compilation, shell syntax checks, diff checks, and credential/path scans.
- [ ] Commit only the plan, implementation, and tests; preserve unrelated staged work.
- [ ] Restart the live one-process bot and verify both ad watching and age-aware training from runtime logs.

## Step 1: Candidate Model and Policy Helpers

Modify `/Users/ns0bj/Development/Fun/osm/auto_training.py`.

- Add minimum relevant-stat constants: 50 for outfield players and 40 for goalkeepers.
- Add the approved age bands and multipliers.
- Add helper functions for minimum stat, age multiplier, and priority calculation.
- Extend `Candidate` with `main_stat`, `age`, `age_multiplier`, and `priority_score`.

## Step 2: Eligibility, Diagnostics, and Ranking

Modify `/Users/ns0bj/Development/Fun/osm/auto_training.py`.

- Build base eligibility first so occupied, listed, injured, maxed, and wrong-position players remain excluded.
- Apply the current-level floor before forecast scoring; never relax it as a fallback.
- Return a precise empty-pool reason for manager logging while preserving `build_candidate_pool(...) -> list[Candidate]` for existing callers and tests.
- Sort by priority score, forecast, age, relevant stat, and player ID.
- Keep at most five candidates at or above 90% of the best priority score.
- Weight random choice by `priority_score²`.

## Step 3: Runtime Integration and Isolation

Modify `/Users/ns0bj/Development/Fun/osm/auto_training.py`.

- Use the detailed pool result in normal and universal trainer loops.
- Include main stat, age, forecast, multiplier-derived priority score in successful start logs.
- Distinguish no forecast, below-floor, and unavailable-player empty states.
- Catch ranking errors per trainer so the remaining trainers and ad conductor continue.

## Step 4: Tests

Modify `/Users/ns0bj/Development/Fun/osm/tests/test_auto_training.py`.

- Update the existing top-band fixture for the new 90% priority band.
- Prove low-level young outfield and goalkeeper candidates are excluded.
- Prove a young average-level player wins equal-forecast ordering.
- Prove a veteran with a large forecast advantage can win.
- Prove an eligible veteran remains selectable when alone.
- Prove all-below-floor candidates produce no fallback and the correct reason.
- Prove seeded weighted selection remains inside the new top band.
- Verify runtime logs contain non-secret scoring factors and manager lifecycle tests still pass.

## Step 5: Verification and Deployment

- Run `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -v`.
- Run Python compilation with bytecode directed under the ignored project runtime area.
- Run `bash -n` for project shell entry points and `git diff --check`.
- Inspect changed and staged paths; scan the intended commit for credential signatures and forbidden HAR, StorageDump, token-cache, or runtime-data paths.
- Commit only this plan, `auto_training.py`, and `tests/test_auto_training.py`.
- Stop the existing conductor gracefully, launch `/Users/ns0bj/Development/Fun/osm/run.sh`, then confirm one conductor process has both ad watchers and the updated training manager active.
