# OSM ad bot observability and scout retry plan

## Scope

Correct the bot's local reporting and retry classification without increasing watcher concurrency, reducing wait periods, or changing the existing ad-completion automation.

## Checklist

- [x] Replace the ambiguous boolean scout result with explicit ready, rate-limited, unavailable-ad, and navigation-error outcomes.
- [x] Apply a bounded retry delay only to unavailable-ad and navigation-error outcomes; retain the server-derived cooldown for real rate limits.
- [x] Persist daily local DOM-reward and failure counters under the ignored runtime directory, using atomic writes.
- [x] Rename user-facing local counters so they do not claim verified ads watched or BossCoins earned.
- [x] Add focused unit coverage, run the complete test suite, and restart the existing LaunchAgent.
- [x] Verify the new process, LaunchAgent state, and new log markers without triggering additional bot actions. The metrics file is created at the first recorded event.
- [x] Diagnose the fresh-storage startup timeout without exposing account tokens or initiating ad actions.
- [x] Make the conductor startup tolerate one transient Training-page readiness failure, with bounded retry and actionable local diagnostics.
- [x] Cover the retry/session-invalid branches, run the suite, and restart the existing LaunchAgent with the supplied storage dump.
- [x] Review the current redacted watcher failures and identify a reliability-only root cause.
- [x] Add a bounded recovery path and focused regression coverage without changing the ad-completion routine.
- [x] Run the full suite and verify the restarted LaunchAgent reaches a stable conductor cycle. The Standard-class LaunchAgent reached conductor Cycle #1 with a real Python PID.
