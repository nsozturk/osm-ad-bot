# Deterministic Training Selection Design

**Date:** 2026-08-23
**Status:** Approved design, pending implementation

## Goal

Change automatic training selection so every trainer considers only players whose position-specific main stat is at least 90, then deterministically chooses the player with the highest current training forecast. Age must not affect eligibility, ranking, or tie-breaking.

## Current Behavior

`auto_training.py` currently filters candidates using a lower minimum-stat threshold, multiplies forecast by an age-based coefficient, creates a near-best candidate pool, and performs a weighted random selection. This can choose a younger player with a lower current training return instead of the player showing the highest progression percentage in the OSM training screen.

## Required Behavior

1. Apply the same policy to all five trainers:
   - attacker coach
   - midfielder coach
   - defender coach
   - goalkeeping coach
   - universal coach
2. Keep existing availability filters: exclude occupied, injured, transfer-listed, or maxed players.
3. Determine eligibility using the position-specific main stat:
   - forwards: `statAtt`
   - midfielders: `statOvr`
   - defenders: `statDef`
   - goalkeepers: `statDef`
4. Include players with a main stat of exactly 90. Reject players below 90.
5. Rank eligible candidates by the current forecast field:
   - position coaches: `forecast`
   - universal coach: `forecastUniversal`
6. Select the candidate with the highest positive forecast without randomness.
7. Use deterministic tie-breaking in this order:
   - higher main stat
   - lower numeric player ID
8. Do not apply an age multiplier or any other age preference.
9. Do not add a separate same-day training penalty. If a repeatedly trained player still has the highest current forecast, select that player again because the API forecast is the source of truth for the current return.
10. If no eligible player exists, leave that trainer idle for the current reconciliation pass and log a precise reason.

## Data Flow

`AutoTrainingManager` continues to fetch players, ongoing sessions, transfer listings, timers, and `/trainingforecasts`. `build_candidate_pool_result` applies availability and minimum-stat filters, maps the trainer to the correct forecast field, and returns candidates in deterministic rank order. `_select_candidate` takes the first candidate. The request payload and training API endpoints remain unchanged.

## Compatibility and Runtime Impact

The change is local to candidate selection. It does not alter authentication, StorageDump handling, API payloads, timers, claim behavior, advertisement watching, or LaunchAgent supervision. The currently running process keeps the old behavior until it is deliberately restarted after tests pass. Restarting causes only a short bot interruption; no persisted training data is migrated.

## Logging

Successful starts should continue to log player name, ID, main stat, and forecast. The obsolete age-weighted priority value should be removed or replaced with deterministic rank information so logs do not imply age affects selection. Empty-pool logs must distinguish at least:

- all otherwise available candidates are below main stat 90;
- no eligible candidate has a positive forecast;
- candidates exist but are unavailable because they are occupied, injured, listed, or maxed.

## Testing

Update `tests/test_auto_training.py` to prove:

1. A player at main stat 90 is eligible and a player at 89 is rejected.
2. The highest forecast always wins, regardless of age.
3. A veteran with the highest forecast beats a younger player with a lower forecast.
4. Equal forecasts prefer higher main stat.
5. Equal forecast and main stat prefer lower player ID.
6. Selection is repeatable across calls and does not use randomness.
7. Position coaches use `forecast` and the universal coach uses `forecastUniversal`.
8. Existing injury, listing, occupied-player, maximum-stat, API payload, and reconciliation behavior remains covered.

Run the focused training tests first, then the complete repository test suite. After restart, verify the runtime log reports a 90+ player with the highest forecast for the corresponding trainer.

## Non-Goals

- Changing training duration, timers, advertisement acceleration, or claim logic.
- Automatically buying or selling players.
- Predicting future forecasts beyond the value returned by OSM for the current pass.
- Adding position-balancing or age-based preferences.
