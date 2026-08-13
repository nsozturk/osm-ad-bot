# OSM Current Budget Transfer Analysis

**Date:** 2026-08-13
**Topic:** osm-current-budget-transfer

## Summary

The refreshed live balance is 21,353,998. For a 4-3-3, the best immediate use of that cash is the Aina + Tobias defensive package: it costs 16,409,265, raises the starting XI by a combined +19 OVR, and leaves 4,944,733. Yildiz is the best single-player purchase at +17 OVR, but costs 20,558,247 and leaves only 795,751.

## Findings

### Progress

- [x] Refresh current OSM squad, transfer market, and finances.
- [x] Rank affordable meaningful upgrades by XI impact and price efficiency.
- [x] Record a clear buy-now or wait recommendation.

### Current snapshot

- Cash: 21,353,998; savings: 0.
- Squad: 26 players; transfer market: 91 entries, of which 89 are external players and 2 are the user's listed players.
- Current 4-3-3 starting XI: ATT 47/46/46, MID 82/80/79, DEF 56/53/47/47, GK 41.
- Starting-XI marginal thresholds: GK 41, DEF 47, MID 79, ATT 46.
- Listed players: Burke for 12,137,142 and J. Friedrich for 3,062,745. These proceeds are not counted until sales complete.

### Best affordable options

- Aina, DEF OVR 59, age 29, price 9,691,128: +12 OVR to the XI.
- Tobias, DEF OVR 54, age 22, price 6,718,137: +7 OVR to the XI.
- Yildiz, ATT OVR 63, age 21, price 20,558,247: +17 OVR to the XI.
- Rayan, ATT OVR 56, age 20, price 19,060,051: +10 OVR to the XI.
- Hakimi, DEF OVR 60, age 27, price 20,708,136: +13 OVR to the XI.

An exhaustive search over affordable one-to-four-player combinations found Aina + Tobias to be the maximum immediate 4-3-3 starting-XI gain within the current cash balance. Their combined +19 gain comes from replacing both OVR 47 starting defenders.

### Recommended targets

1. Best squad-strengthening package now: buy Aina + Tobias for 16,409,265. The XI gains +19 OVR and 4,944,733 remains.
2. Best single-player/star option now: buy Yildiz for 20,558,247. The attack gains +17 OVR, but only 795,751 remains.
3. If Burke sells first, the cash would rise to 33,491,140. At that point Yildiz + Aina costs 30,249,375, gives +29 OVR to the XI, and leaves 3,241,765.
4. If both listed players sell, the cash would rise to 36,553,885. At that point Gakpo + Aina costs 35,345,443, gives +32 OVR, and leaves 1,208,442.

### Decision

For the current squad, Aina + Tobias is the rational purchase because it produces the largest immediate XI improvement under budget without exhausting the treasury. Choose Yildiz instead only if prioritizing a young attacking star over total team improvement. Re-check the live market before executing because listings and prices can change.

## Sources

- Live OSM API data, read through `/Users/ns0bj/Development/Fun/osm/transfer-advisor/live_fetch.py`
- Sensitive local storage export remains outside Git.
