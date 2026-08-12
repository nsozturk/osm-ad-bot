# OSM Live Transfer Recommendations

**Date:** 2026-08-12
**Topic:** osm-live-transfer-recommendations

## Summary

The supplied Chrome storage export was used without printing or persisting its tokens. The live OSM API returned a 31-player squad, 58 transfer-list entries, and a current cash budget of 3,643,000. No available player both improves the current starting XI and fits the present budget, so the recommended action is to wait for listed-player sales or additional income rather than make a downgrade purchase.

## Findings

### Current squad

- Formation used: 4-3-3.
- Goalkeeper: 3 players, best OVR 39, starting-XI threshold 39; very weak.
- Defence: 10 players, best OVR 54, starting-XI threshold 47; very weak.
- Midfield: 7 players, best OVR 77, starting-XI threshold 75; medium.
- Attack: 11 players, best OVR 47, starting-XI threshold 45; very weak.
- Four squad players are currently listed for sale; their combined listing prices are 8,958,390. Those proceeds are not counted until sales complete.

### Recommendation

1. Do not buy at the current 3,643,000 balance; every affordable option is a non-improving depth purchase.
2. The first reachable meaningful target is R. Kristensen, DEF OVR 49, at 7,826,898. He needs roughly 4.18M additional cash and improves the current defensive XI threshold by only +2 OVR.
3. If all four listed players sell at their current prices, the projected cash becomes 12,601,390. At that point, prefer waiting rather than spending immediately on a marginal +1 goalkeeper or +2 defender unless the market is about to refresh.
4. The strongest nearer-term upgrade is Okafor, ATT OVR 60, at 16,189,579: +15 OVR over the current attacking XI threshold. He requires about 3.59M more even after all four listed sales.
5. Yildiz is the highest-ranked overall target in the current market: ATT OVR 63, age 21, price 21,257,443, and +18 OVR. Treat him as the savings target if the listing remains available.

### Other cheapest position upgrades

- Goalkeeper: Ramsdale, OVR 40, 8,130,845, only +1 OVR.
- Midfield: Saelemaekers, OVR 80, 12,596,923, +5 OVR; lower priority because midfield is already the strongest unit.
- Attack: Batshuayi, OVR 47, 14,920,887, only +2 OVR; poor value compared with saving a little longer for Okafor.

### Security and verification

- The access token had expired, so the script used the dump's refresh token in memory and completed the live read successfully.
- The existing `.token`, `.refresh`, and `.client_secret` files were all older than the live-fetch start marker, proving this storage-dump run did not rewrite them.
- The ZIP path and all derived data/token paths remain ignored by Git. No credential signature was found in the source diff.

## Sources

- Local storage export: `/Users/ns0bj/Downloads/storagedump_en.onlinesoccermanager.com_2026-08-12T16-52-10-428Z.zip` (sensitive; not copied or committed)
- Live OSM API responses stored under ignored path `/Users/ns0bj/Development/Fun/osm/transfer-advisor/data/`
- Local recommendation engine: `/Users/ns0bj/Development/Fun/osm/transfer-advisor/recommend.py`
