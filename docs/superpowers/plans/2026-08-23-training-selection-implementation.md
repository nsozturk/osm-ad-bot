# Deterministic Training Selection Implementation Plan

**Date:** 2026-08-23
**Design:** `/Users/ns0bj/Development/Fun/osm/docs/superpowers/specs/2026-08-23-training-selection-design.md`

## Objective

Replace age-weighted random automatic-training selection with a deterministic policy shared by all trainers: main stat 90 or higher, highest current forecast first, then higher main stat, then lower player ID.

## Checklist

- [x] Replace the outfield/goalkeeper floors and priority-pool constants with one inclusive main-stat threshold of 90.
- [x] Remove age multipliers, priority scores, weighted candidate pools, and random selection from `auto_training.py`.
- [x] Preserve availability, injury, transfer-listing, occupied-player, max-stat, trainer-position, and positive-forecast filters.
- [x] Sort candidates by forecast descending, main stat descending, and numeric player ID ascending.
- [x] Make `choose_candidate` return the first ranked candidate deterministically.
- [x] Update success and empty-pool logs so they describe forecast-based selection and the 90 threshold accurately.
- [x] Rewrite focused unit tests for the inclusive threshold, forecast priority, age independence, deterministic tie-breaking, repeatability, and universal forecast field.
- [x] Update reconciliation fixtures to use eligible 90+ players while preserving existing claim/start/API behavior coverage.
- [x] Run focused automatic-training tests.
- [x] Run the complete repository test suite.
- [x] Review the final diff for unrelated edits, secret exposure, and compatibility with the conductor call site.
- [ ] Restart the LaunchAgent only after all tests pass.
- [ ] Verify the new PID, healthy training reconciliation, and deterministic-selection log format.

## Files

### `/Users/ns0bj/Development/Fun/osm/auto_training.py`

- Introduce `MIN_TRAINING_MAIN_STAT = 90`.
- Reduce `Candidate` to fields used by deterministic selection and safe logging.
- Remove `training_age_multiplier` and all priority-pool logic.
- Return all eligible candidates in stable rank order.
- Remove the manager RNG dependency and age-weighted priority log output.

### `/Users/ns0bj/Development/Fun/osm/tests/test_auto_training.py`

- Replace tests for low thresholds, youth weighting, top-band pools, and weighted randomness.
- Add direct coverage for 90 inclusion, 89 rejection, highest-forecast selection, age independence, tie-breaking, repeatability, and `forecastUniversal`.
- Raise fake API player stats to 90+ so reconciliation tests continue exercising trainer filling.

## Verification Commands

```bash
python3 -m unittest tests.test_auto_training -v
python3 -m unittest discover -s tests -v
git diff --check
./run.sh restart
./run.sh status
tail -n 120 /Users/ns0bj/Development/Fun/osm/tmp/osm-runtime/conductor.log
```

## Runtime Safety

The implementation changes only local candidate ranking. No API endpoint, payload, credential, StorageDump, training timer, advertisement, or LaunchAgent contract changes. If tests fail, do not restart the running bot. If restart succeeds but reconciliation fails, retain the logs and restore service using the last known-good committed code before reporting completion.
