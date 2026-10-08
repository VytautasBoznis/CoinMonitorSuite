---
name: f5-polymarket-favorites-killed
description: "F5 Polymarket favorite-longshot KILLED 2026-10-08: 90-97c favorites at endDate-24h are NOT underpriced (gap −1.53pp, CI [−3.80, +0.51]); every price bucket <= 0. Plus Polymarket API gotchas (urllib blocked, keyset pagination, prices-history only before closedTime)."
metadata:
  node_type: memory
  type: project
  originSessionId: 4238af7c-0366-4df9-991c-17ffbd36d05d
  modified: 2026-10-08T19:15:52.654Z
---

Idea 5 of [[fable-batch-10-probe-queue]], run 2026-10-08. `probes/f5_polymarket_favorites.py`, log
`runs/f5_polymarket_favorites.log`, caches `data/f5_markets.parquet`, `data/f5_priced.parquet`,
`data/f5_event_cats.json` (gitignored).

Universe: 46,510 closed binary markets >= $100k volume (feesEnabled false), 32,382 still open at
scheduled endDate−24h (the point-in-time anchor; closedTime would be look-ahead). Frozen seeded
subsample of 8,000 priced (7,933 had a price).

**KILL, all five rules failed.** N=578 favorites (P1 needs 1000 — only ~7% of markets sit at 90-97c
a day out), mean price 93.91c vs win rate 92.39% → **gap −1.53pp**, event-bootstrap CI [−3.80, +0.51].
Categories: Politics +0.21 (n=210), Crypto −0.99 (193), Sports −5.73 (94), Other −2.44. Buckets:
90-92c −5.86pp, 92-95c −0.60, 95-97c −0.16. Recent 24mo −1.17pp. The CI's upper end is below the
+1.5pp bar, so a bigger sample could not flip it. Favorites are, if anything, OVERpriced.
Not tested: Fable's second leg (decided-but-unresolved markets under 99c).

**Polymarket API facts (non-obvious, for any future use):** Gamma blocks python `urllib` (403/429)
but `requests`/aiohttp/curl work; offset pagination caps out → use `/markets/keyset` (100/page,
`after_cursor`); market `category` is ~always null → category lives in `/events/{id}` tags;
CLOB `prices-history` returns nothing for windows after `closedTime` (many markets close weeks
before their scheduled `endDate`). 2025-26 = ~90% of liquid markets.
