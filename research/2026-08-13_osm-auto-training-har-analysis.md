# OSM Automatic Training HAR Analysis

**Date:** 2026-08-13
**Topic:** osm-auto-training-har-analysis

## Summary

The current Training HAR confirms the complete OSM training API flow, including five trainer slots, player-specific forecasts, starting sessions, and the separate claim operation required after a timer finishes. The implemented manager claimed five completed sessions and started four normal position-matched sessions using current forecast values; OSM rejected the unavailable universal slot without triggering a purchase. The HAR does not contain usable authentication values: Chrome omitted Authorization and cookie data, and no JWT or Bearer value is present.

## Findings

### HAR scope and credential finding

- The HAR contains 235 network entries and current Training page responses.
- API request headers contain no `Authorization` header and no `Cookie` header; the HAR request cookie collections are empty.
- A direct credential-pattern scan found zero JWT-like values and zero Bearer values.
- The strings `access_token` and `refresh_token` occur only in downloaded OSM JavaScript source, not as session credential values.
- Therefore the HAR can safely provide endpoint behavior, current squad/forecast data, trainer mapping, and timer setting IDs, but it cannot replace a post-login StorageDump for browser authentication.

### Training API flow

- `GET /api/v1/leagues/{league}/teams/{team}/players` returns the current squad.
- `GET /api/v1/leagues/{league}/teams/{team}/trainingforecasts` returns `playerId`, `forecast`, and `forecastUniversal` for each player.
- `GET /api/v1/leagues/{league}/teams/{team}/trainingsessions/ongoing` returns the ongoing sessions; the captured empty state returned HTTP 404.
- `POST /api/v1/leagues/{league}/teams/{team}/trainingsessions` starts a training with `playerId`, `trainer`, and `timerGameSettingId`.
- `PUT /api/v1.1/leagues/{league}/teams/{team}/trainingsessions/{sessionId}/claim` claims a finished session. Claiming is required before the UI completes the player progression and frees the slot.

### Trainer and timer mapping observed in the HAR

- Trainer 1: attacker, normal training timer setting 746, observed duration 7,200 seconds.
- Trainer 2: midfielder, normal training timer setting 746, observed duration 7,200 seconds.
- Trainer 3: defender, normal training timer setting 746, observed duration 7,200 seconds.
- Trainer 4: goalkeeper, normal training timer setting 746, observed duration 7,200 seconds.
- Trainer 5: universal, universal timer setting 982, observed duration 5,400 seconds.
- Timer setting IDs should be read from the supplied HAR profile when available and kept configurable, because OSM can change game settings.

### Recommended selection policy

- Match trainers 1-4 to their position and score candidates with `forecast`.
- Score universal trainer candidates with `forecastUniversal`.
- Exclude players already in another active training, injured players, max-level players, and players currently listed for transfer.
- Use the server forecast as the primary diminishing-return signal: repeated training that has become inefficient naturally receives a lower forecast.
- Randomly choose among the near-best candidates rather than always selecting one player. A weighted top band preserves variety while keeping expected progression high.
- Re-fetch squad, forecasts, transfer listings, and ongoing sessions before every fill pass so decisions use current values.

### Compatibility and failure isolation

- Keep automatic training behind a new conductor flag so existing direct CLI invocations remain unchanged; enable it from `run.sh` for the requested default behavior.
- Run training polling independently from the ad watcher loop. Training API failures must be logged and retried without stopping ads.
- Claim completed sessions before filling free slots, then re-fetch state to avoid duplicate starts.
- Do not buy trainers, spend Boss Coins, boost timers, or convert Boss Coins to club funds automatically.
- Do not persist or print access/refresh tokens. Continue using StorageDump cookies in memory for the browser session.

### Live verification

- The 2026-08-12 StorageDump access token had expired, but its refresh token produced a new access token in memory; no rotated credential was written to disk.
- Five completed sessions were successfully claimed.
- Four normal sessions were started: Burcu with attacker trainer 1, Haberer with midfielder trainer 2, M. Friedrich with defender trainer 3, and Klaus with goalkeeper trainer 4.
- The final server read returned exactly four ongoing sessions. The current forecast values were 57, 75, 72, and 44 respectively.
- OSM returned HTTP 400 for the universal trainer. The manager cached the unavailable state and did not invoke universal-trainer purchase, timer boost, Boss Coin conversion, transfer, or player-buy endpoints.
- The final verified balance was 23,390,659 with savings 0.
- Fourteen unit tests, Python compilation, Bash syntax, offline HAR parsing, and diff checks passed.
- A scan of all ten changed/untracked files found zero JWTs, Bearer literals, GitHub tokens, private keys, or AWS access keys. HAR, ZIP, token cache, refresh cache, and runtime log paths remain ignored and untracked.

## Sources

- Local HAR: `/Users/ns0bj/Development/Fun/osm/en.onlinesoccermanager.com-training.har`
- Current conductor: `/Users/ns0bj/Development/Fun/osm/osm_ad_bot_conductor.py`
- OSM Training frontend JavaScript embedded in the supplied HAR (`training.js.v32540`)
