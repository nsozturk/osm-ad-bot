# OSM Automatic Training Design

**Date:** 2026-08-13
**Status:** Approved design, pending implementation

## Goal

Extend the existing conductor so completed training sessions are claimed and empty trainer slots are refilled automatically. Player choice must react to OSM's current forecast values so repeatedly training a player whose expected progression has dropped is naturally deprioritized.

## Scope

The feature covers training lifecycle automation only:

- Poll current training sessions.
- Claim sessions whose timers have finished.
- Detect empty trainer slots.
- Refresh squad, forecasts, transfer listings, and finance state before selecting players.
- Start training for suitable players using the current timer setting IDs.
- Keep the ad conductor operational if training APIs fail.

The feature will not buy a universal trainer, spend Boss Coins, boost timers, convert Boss Coins to club funds, buy players, or alter transfer listings.

## Compatibility

Automatic training is additive and opt-in at the conductor CLI layer. Existing direct invocations of `osm_ad_bot_conductor.py` keep their present behavior unless `--auto-training` is passed. The project `run.sh` entry point enables the flag by default because that is the requested workflow.

Training runs as an independent asynchronous task. Its failures are caught, logged without credential data, and retried; they cannot terminate or delay the advertisement conductor loop.

## Authentication and Input Sources

Browser authentication continues to come from a Chrome StorageDump. Credentials are loaded into memory and injected into Playwright without printing or committing their values.

The supplied HAR is used as a training profile, not as an authentication source. Direct inspection proved that it contains no Authorization header, cookie collection, JWT, or Bearer token value. It does contain the current training endpoint behavior and observed timer settings:

- Normal trainer timer setting: `746`
- Universal trainer timer setting: `982`

The implementation accepts timer settings from the HAR profile when present and exposes safe CLI overrides. No token, HAR, StorageDump, extracted credential, or derived session file is committed.

`run.sh` no longer hardcodes the 2026-08-06 dump. It accepts an explicit StorageDump path and otherwise selects the newest compatible StorageDump in the configured downloads location. If the selected session is invalid after logout/login, it exits with a clear instruction to export a fresh post-login StorageDump; it never falls back silently to a stale credential cache.

## API Model

The manager uses the OSM endpoints confirmed by the supplied HAR and frontend implementation:

- `GET /api/v1/leagues/{league}/teams/{team}/players`
- `GET /api/v1/leagues/{league}/teams/{team}/trainingforecasts`
- `GET /api/v1/leagues/{league}/teams/{team}/trainingsessions/ongoing`
- `GET /api/v1/leagues/{league}/teams/{team}/transferplayers/0`
- `GET /api/v1/leagues/{league}/teams/{team}/finances/balanceandsavings`
- `POST /api/v1/leagues/{league}/teams/{team}/trainingsessions`
- `PUT /api/v1.1/leagues/{league}/teams/{team}/trainingsessions/{sessionId}/claim`

HTTP 404 from the ongoing-sessions endpoint is treated as an empty collection, matching the captured empty-state response. Authentication failures trigger the existing live-cookie refresh path and then back off without crashing the process.

## Trainer Model

Trainer identifiers follow the live OSM mapping:

| Trainer | Role | Candidate position | Forecast field | Timer setting |
| --- | --- | --- | --- | --- |
| 1 | Attacker | 1 | `forecast` | 746 |
| 2 | Midfielder | 2 | `forecast` | 746 |
| 3 | Defender | 3 | `forecast` | 746 |
| 4 | Goalkeeper | 4 | `forecast` | 746 |
| 5 | Universal | Any | `forecastUniversal` | 982 |

Trainer 5 is considered available when current sessions/timers expose an active universal trainer. If that state is inconclusive, the manager may make one normal start request as a capability probe; an unavailable-entitlement response is cached until relevant server state changes. The probe never calls the separate universal-trainer purchase endpoint, and its failure is a non-fatal skip.

## Lifecycle

Each poll performs one serialized reconciliation pass:

1. Fetch ongoing sessions and current server time information.
2. Identify finished sessions from their countdown timer state.
3. Claim finished sessions one at a time.
4. Re-fetch ongoing sessions after claims.
5. Fetch players, forecasts, own transfer listings, and finances.
6. Build the set of occupied trainer slots and players already training.
7. Fill each free normal trainer slot, then the free universal slot if available.
8. Re-fetch ongoing sessions after each successful start to prevent duplicate assignments.
9. Sleep until the configured poll interval or shutdown signal.

The default poll interval is 60 seconds. The manager uses a lock so a slow pass cannot overlap the next pass.

## Candidate Eligibility

A player is eligible only when all of these are true:

- The player belongs to the current squad.
- The player matches the normal trainer position, or the trainer is universal.
- The player is not already in an ongoing training session.
- The player is not injured.
- The player's relevant main stat is below the maximum level.
- The player is not currently listed for transfer.
- The forecast field required for the trainer is present and positive.

Suspended players remain eligible because suspension does not prevent training in the observed OSM client. Lineup players remain eligible when the league setting permits it; if the API rejects one, the candidate is skipped for that pass without weakening the global loop.

## Selection Algorithm

For each empty trainer, candidates are sorted by the current relevant forecast. Let `best` be the highest forecast in that eligible group.

The random pool contains up to the five highest candidates whose forecast is at least 85% of `best`. Selection is weighted by `forecast²`, which keeps the result varied while strongly favoring better expected progression. The latest server forecast is the main diminishing-return signal; a repeatedly trained player whose expected gain falls will leave the top band naturally.

Within equal forecasts, younger players and players with greater first-XI relevance receive deterministic tie-break priority before weighted sampling. No persistent player-training history is required because stale local history could contradict the server's current forecast after transfers, events, or level changes.

## Funds and Spending Safety

The manager fetches finances for diagnostics but never performs the web client's Boss Coin conversion step. It submits only the normal training start request. If club funds are insufficient, the API error is logged as a safe skip and the slot is retried on a later poll.

Logs include trainer ID, selected player name/ID, forecast, action result, and next retry time. They never include request headers, cookies, access tokens, refresh tokens, raw HAR bodies, or StorageDump contents.

## CLI and `run.sh`

New conductor options:

- `--auto-training`: enable the manager.
- `--training-poll-interval SECONDS`: polling period, default 60.
- `--training-har-profile PATH`: safely read timer setting IDs and validated endpoint context from a HAR without treating it as an auth source.
- `--normal-training-timer-id ID`: explicit override.
- `--universal-training-timer-id ID`: explicit override.

`run.sh` enables automatic training, points at the supplied Training HAR profile, writes logs and PID state under the repository's ignored `tmp/` directory, and selects the latest StorageDump unless the user supplies one explicitly.

## Error Handling

- Network timeout or 5xx: log once per failure class, exponential backoff capped at five minutes.
- 401/403: retry once with the latest browser cookie; if still unauthorized, pause training and leave ads running.
- Empty-state 404: normalize to no sessions.
- Claim conflict or already-claimed response: refresh state and continue.
- Start conflict or occupied slot: refresh state and continue.
- Invalid/missing forecast or timer setting: skip that trainer and explain the reason.
- Shutdown: cancel the training task cleanly before closing the browser context.

## Verification

Implementation is complete only after all of the following pass:

- Unit tests for trainer mapping, eligibility, top-band construction, weighted selection boundaries, empty 404 handling, finished-session claiming, duplicate prevention, and error isolation.
- Offline HAR fixture test proving the profile parser obtains timer settings without exposing credentials.
- Existing conductor DOM queue tests remain green.
- Python and Bash syntax checks.
- `git diff --check`.
- Secret scan over tracked/staged changes proving no token, HAR, StorageDump, or credential file is included.
- With a fresh post-login StorageDump, a bounded live smoke test that reads current sessions and performs at most the requested normal lifecycle actions without buying or boosting anything.

## Success Criteria

- Finished training sessions are claimed without manual intervention.
- Every eligible empty normal trainer slot is refilled within one poll interval.
- The universal slot is refilled only when already available.
- Player selection uses current forecast values and avoids low-yield repeated choices.
- Training failures never terminate the advertisement conductor.
- `run.sh` no longer depends on a hardcoded old dump.
- No authentication material appears in Git or logs.
