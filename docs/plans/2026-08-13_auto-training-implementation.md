# OSM Automatic Training Implementation Checklist

- [x] Inspect the supplied HAR, current conductor, authentication flow, and live compatibility requirements.
- [x] Approve and commit the automatic-training design specification.
- [x] Add a secret-safe HAR training-profile parser and pure player-selection logic.
- [x] Implement claim, refresh, empty-slot detection, and refill reconciliation in an isolated training manager.
- [x] Integrate the manager into the conductor behind opt-in CLI flags without changing existing direct invocations.
- [x] Update `run.sh` to select the latest StorageDump, enable automatic training, use project-local runtime files, and avoid stale hardcoded credentials.
- [x] Add unit tests for parsing, eligibility, weighted top-band selection, claiming, refill, duplicate prevention, and failure isolation.
- [x] Run unit tests, Python/Bash syntax checks, offline HAR validation, and diff checks.
- [x] Scan tracked/staged scope for secrets and confirm HAR, StorageDump, token caches, and runtime files remain excluded.
- [x] Run a bounded live smoke test when a fresh post-login StorageDump is available; otherwise report that external credential blocker explicitly.

## Live verification result

- Claimed five completed sessions.
- Started four normal sessions: Burcu (ATT), Haberer (MID), M. Friedrich (DEF), and Klaus (GK).
- The universal start was rejected by OSM with HTTP 400; the manager cached the unavailable state and did not call a purchase, boost, transfer, or Boss Coin conversion endpoint.
- Final read-only verification returned four ongoing sessions and a balance of 23,390,659 with savings 0.
