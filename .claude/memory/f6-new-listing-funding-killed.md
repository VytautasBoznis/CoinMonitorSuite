---
name: f6-new-listing-funding-killed
description: "F6 new-perp-listing funding capture KILLED 2026-10-08 on BOTH venues (hit rate 45%/41% < 60%). Mean long-side funding +1.5% (Binance) / +0.93% (Bybit) per listing is a TAIL (median slightly negative); hedge = scarce borrow, cross-venue hedge blocked by Bybit-only doctrine."
metadata:
  node_type: memory
  type: project
  originSessionId: 4238af7c-0366-4df9-991c-17ffbd36d05d
  modified: 2026-10-08T18:53:45.717Z
---

Idea 6 of [[fable-batch-10-probe-queue]], run 2026-10-08. `probes/f6_new_listing_funding.py`, log
`runs/f6_new_listing_funding.log`, per-venue event caches `data/f6_listing_events_{bybit,binance}.parquet`
(gitignored). Funding leg only, gross of hedge (a hedge can only subtract). Window = first 7 days
from the first funding settlement; 581 Binance + 730 Bybit USDT perps listed 2021-01 → 2026-09.

**Frozen rule KILL on L3 (hit >= 60%) for both venues; L1/L2/L4 passed.**
- Binance: mean +1.505%/listing, CI [+1.08, +1.97], **median −0.16%, positive 45.3%**; recent 24mo
  +1.92% (49% positive). Top-10 listings = 36% of summed funding.
- Bybit: mean +0.928%, CI [+0.61, +1.29], median −0.10%, positive 40.8%; recent +1.26%. Top-10 = 46%.
- Naked long perp over the same window (never blended): Binance mean −3.67% / median −12.6%;
  Bybit mean +3.70% / median −3.1%. New listings dump; the naked version is not the trade.
- 2021 was NEGATIVE on both venues (−0.97 / −0.83%) — the one premium that is NOT a 2021 artifact;
  2025 strongest (+2.35 / +3.02%).

**Why the tail isn't free:** funding goes deeply negative exactly where shorting is crowded and spot
borrow is scarce, so the spot-short hedge costs ≈ what the funding pays. The borrow-free hedge (short the
same perp on another venue = cross-venue funding spread) is blocked by [[bybit-only-leverage-doctrine]].
Untested, snooped follow-ups if ever revisited: condition entry on the FIRST settlement being deeply
negative (funding persistence), and measure Bybit spot-margin borrow availability/cost on fresh listings.
