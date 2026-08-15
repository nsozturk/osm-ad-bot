# OSM Current Budget Transfer Analysis

**Date:** 2026-08-13
**Topic:** osm-current-budget-transfer

## Summary

The refreshed live cash balance is 24,450,659, with no savings. The strongest decision is to wait for another 359,839 and buy Gakpo, because his OVR 66 replaces an OVR 47 starting attacker for a +19 starting-XI gain. If a purchase must be made immediately, Aina is the best value: OVR 59 for 9,372,369, a +12 defensive gain while preserving 15,078,290.

## Findings

### Progress

- [x] Refresh current OSM squad, transfer market, and finances.
- [x] Rank affordable meaningful upgrades by starting-XI impact and price efficiency.
- [x] Compare buy-now, short-wait, and listed-player-sale scenarios.

### Current snapshot

- Cash: 24,450,659; savings: 0.
- Squad: 22 players; transfer market: 85 entries, including 84 external candidates and one own listed player.
- Current 4-3-3 starting-XI thresholds: GK 41, DEF 47, MID 80, ATT 47.
- The weakest areas are goalkeeper, the fourth defender, and the second/third attacker.
- Burke, ATT OVR 40, is listed for 12,137,142. Sale proceeds are not included in the current budget.

### Short-wait target

- Gakpo, ATT OVR 66, age 27, price 24,810,498.
- Current gap: 359,839.
- Immediate starting-XI effect after purchase: +19 OVR, replacing an OVR 47 attacker.
- This is the largest single-player improvement close to the current budget.

### Affordable options now

1. Aina, DEF OVR 59, age 29, price 9,372,369: +12 starting-XI OVR; 15,078,290 remains.
2. Hakimi, DEF OVR 60, age 27, price 20,027,008: +13; 4,423,651 remains.
3. Rayan, ATT OVR 56, age 20, price 18,433,132: +9; 6,017,527 remains.
4. Jovanovic, ATT OVR 49, age 19, price 11,504,292: +2; poor immediate return despite youth.
5. B. Fernandes, MID OVR 89, age 31, price 22,505,107: +9; 1,945,552 remains, and midfield is already stronger than attack and defence.

An exhaustive affordable-combination check found Aina + Jovanovic as the largest buy-now starting-XI gain: +14 for 20,876,661, leaving 3,573,998. However, Jovanovic costs 11,504,292 for only +2 immediate OVR, so this package is not good value compared with waiting 359,839 for Gakpo.

### Listed-player-sale scenario

If Burke sells at the current listing price, available cash becomes 36,587,801. Gakpo + Aina would then cost 34,182,867, add a combined +31 starting-XI OVR, and leave 2,404,934.

### Decision

- Best overall decision: do not buy yet; collect another 359,839 and buy Gakpo.
- Best immediate value if a transfer must happen now: buy Aina only.
- Avoid Hakimi at the current price: he costs 10,654,639 more than Aina for only one additional OVR of immediate improvement.
- Avoid spending on a goalkeeper now: the affordable goalkeeper upgrades provide only +1 to +3 OVR for roughly 9.6M to 17.7M.
- If Burke sells before Gakpo disappears, buy Gakpo + Aina.

The market is time-sensitive, so prices and availability should be refreshed again immediately before any purchase.

## Sources

- Live OSM squad, transfer-market, and finance endpoints read through `/Users/ns0bj/Development/Fun/osm/transfer-advisor/live_fetch.py`.
- Combination analysis performed locally from the refreshed ignored JSON files under `/Users/ns0bj/Development/Fun/osm/transfer-advisor/data/`.
- Sensitive storage-export credentials were used only in memory and were not written into this report.
