# OSM Storage Dump Review

**Date:** 2026-08-10
**Topic:** osm-storage-dump-review

## Summary

The supplied archive is a Chrome browser-storage export, not a HAR capture. It includes 132 local-storage records and 12 session-storage records; no saved API response paths for squad, transfer list, or finances were found. Its cookie export contains both `access_token` and `refresh_token`, and both were unexpired at the time of this review; the archive is therefore sensitive and must remain outside Git.

## Findings

### Progress

- [x] Archive structure inventoried.
- [x] Browser storage and session schema classified without exposing credentials.
- [x] Current extractor and live-fetch compatibility checked.
- [x] Recommended next action documented.

### Archive contents

- The archive has `manifest.json`, cookie/session/local storage exports, IndexedDB, cache, service-worker, and extension records.
- `local/part-1.json` has 132 records; `session.json` has 12. Neither contains the OSM API-response route markers used for squad, transfer list, or finance parsing (`/players`, `transferplayers`, or `balanceandsavings`).
- Cookie record names include `access_token` and `refresh_token`. Both values are JWT-shaped and were not printed, copied, or written into this repository. At the check time, the access token expired at `2026-08-10T15:48:33Z` and the refresh token at `2026-08-17T15:28:33Z`.

### Compatibility with the current tools

- `transfer-advisor/har_extract.py` requires a HAR `log.entries` structure, so it cannot parse this storage export.
- `transfer-advisor/live_fetch.py` already supports an access token plus refresh-token rotation, but only from CLI flags, environment variables, or ignored files under `transfer-advisor/data/`; it has no `--storage-dump` input.
- The checked Python sources compile successfully. No source-code change was made during this review.

### Recommended next action

Add a dedicated `--storage-dump <zip>` option to `live_fetch.py` that reads only the two OSM cookie values in memory, never logs them, and continues to write rotated credentials only to the existing ignored `transfer-advisor/data/` paths. Do not add the ZIP, extracted JSON, or any token file to Git.

## Sources

- Local archive: `/Users/ns0bj/Downloads/storagedump_en.onlinesoccermanager.com_2026-08-10T15-28-52-457Z.zip` (not committed or copied into the repository)
- Local code: `/Users/ns0bj/Development/Fun/osm/transfer-advisor/`
