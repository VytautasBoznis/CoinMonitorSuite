---
name: f9-weekend-vrp-killed
description: "F9 weekend variance risk premium KILLED 2026-10-08 on real Deribit Monday-expiry option prints (both BTC and ETH). The DVOL proxy's +15 vol-pt 'premium' was the weekend calendar effect; real weekend options price AT/BELOW realized since 2023. Reverse (long) is a snooped macro-shock lottery, not a lead."
metadata:
  node_type: memory
  type: project
  originSessionId: 4238af7c-0366-4df9-991c-17ffbd36d05d
  modified: 2026-10-08T18:17:16.705Z
---

Idea 9 of [[fable-batch-10-probe-queue]], run 2026-10-08. Two pre-registered stages.

**Stage 1 — DVOL proxy (`probes/f9_weekend_vrp_proxy.py`, `runs/f9_weekend_vrp_proxy.log`): PASS
but meaningless.** Fri-00 DVOL minus Fri→Mon 5m RV: BTC +14.9 pts (HAC t 10.4), ETH +14.3. The
pre-declared weekday control killed the reading: same 30d index vs Mon→Thu RV only +3.4 / +1.0 pts;
weekend RV ≈ 0.8x weekday RV. The gap is the calendar effect, which short-dated options already price.

**Stage 2 — real option prints (`probes/f9b_weekend_option_iv.py`, `runs/f9b_weekend_option_iv.log`):
KILL both coins.** Deribit lists dailies ~2 days ahead, so NO Monday expiry exists Friday; the
pure-weekend trade is sell the Monday-08:00 ATM straddle at Sat 10:00 (46h). Bid IV = taker-sell
prints from Deribit's free history API (81k prints cached in gitignored `data/f9b_option_trades.parquet`).
- BTC: bid IV 42.1 vs RV 43.2 (gap −1.1), 1x short-straddle yield +1.3%/yr t 0.15; positive 2021
  (+62%/yr) and 2022 (+20%), then negative every year; recent 24mo −25.9%/yr.
- ETH: gap −5.6 pts (t −3.8), −19.4%/yr; recent −36.8%/yr.
- **Formula bug caught after first run:** straddle was priced as one call (2N(s/2)−1, should be ×2).
  Declared in docstring; it moved S4/S5 only; the S2/S3 gap FAILs (and the KILL) never depended on it.

**Reverse (long straddle at ask), post-verdict + DATA-SNOOPED:** negative every year 2021-2024,
+16%/yr BTC / +29%/yr ETH recent 24mo but t ≈ 1.8, win ~50%, top-3 weekends = 63% / 89% of PnL
(2024-08-03 yen unwind, 2025-02-01 + 2025-04-05 tariff weekends). A macro-shock lottery. Not a lead.

Takeaway for future vol ideas: never judge an options premium off a constant-maturity index (DVOL);
price the actual instrument. Deribit history API is free, fast (~1s/call), 429s at 8 threads (use 4).
