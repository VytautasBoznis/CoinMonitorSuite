---
name: f11-post-listing-drift-killed
description: "F11 post-listing drift short (day 8→98, alt-basket hedged, 1x isolated) KILLED 2026-10-15 on both venues. The drift is real (median short +20-27%) but ~26% of listings double after day 8 and liquidate the 1x short. Never-liquidated upper bound passes, so leverage, not signal, is what kills it."
metadata:
  node_type: memory
  type: project
  originSessionId: ab39adfc-9206-426e-a9df-03dab117d6f0
  modified: 2026-10-15T16:14:39.822Z
---

Fable's spec, pasted by the owner and frozen by the owner as written on 2026-10-15. Owner constraint: no
Hyperliquid data; its API budget belongs to the live bot, and it is kept for a final recheck. Probe:
`probes/f11_post_listing_drift_short.py`. Logs: `runs/f11_post_listing_drift_short.log`, and the buggy
first pass in `_v1.log`. Caches: `data/f11_{bars,funding}_{binance,bybit,basket}.parquet`, gitignored.
The pull took ~55 min: Binance's funding endpoint took 24 min, and Bybit was slow that evening at
~3 s/call.

**Rule:** short at t1+7d, cover at t1+97d. Hedge = long an equal-weight basket of the 37 crypto legs of
the DB's 41, without USDC, RLUSD, USD1 and XAUT, pulled from the Bybit API because the DB candles stop
2026-07-02. Fees = 0.11% round trip per leg. Liquidation on 1h highs, with funding paid from the
isolated margin.

**Result: KILL on both venues.**

| | N | mean/event | CI (month clusters) | recent 24mo | median |
|---|---|---|---|---|---|
| Binance | 572 | +2.03% | [-6.3, +10.9] | +0.68% | +21% |
| Bybit | 566 | -4.61% | [-13.0, +4.6] | -3.13% | +11% |

The losing checks are mean, CI and top-5 share; Bybit also fails the recent-24mo check.

**Sensitivities:**
- Literal 41-leg basket: KILL.
- CLOSE-LIQ (liquidated only when a 1h close crosses, a generous mark-price proxy): KILL. Binance
  +4.34%, CI includes 0; Bybit -2.96%.
- NO-LIQ (never liquidated, floored at -100% at exit): **PASS**. Binance +18.6% [+11.4, +26.8], Bybit
  +9.1% [+2.3, +16.8], recent-24mo positive on both. This is an upper bound, not a reachable 1x position.

**Why it dies:**
- 151/137 events liquidate: a 1h high reaches ~2x the day-8 price.
- Most are real squeezes, not wicks: 93/98 had closes above 2x for 24h or more; only 19/9 were
  wick-only.
- 61 of the Binance and 52 of the Bybit liquidated names ended BELOW entry by day 97. The short was
  right and still died.

**Per year, Binance:** 2024 +19.9%, 2025 -8.2%, 2026 -10.1%. Bybit 2026 +9.8% (n=134).

**Bugs fixed after seeing the v1 output** (both helped the short; the verdict did not change): v1
charged funding on top of a -100% liquidation (worst event -183%), and ignored funding when computing
the liquidation price.

**If revisited, every variant is SNOOPED; re-register before running:**
- Lower leverage (0.33-0.5x, liquidation at 3-4x, more capital per unit of notional).
- Squeeze-trap kill-filter: Fable's idea, proposed before the data. It would have to predict ~1 in 4
  listings, not the "worst 5".
- Survivor bias (delisted perps missing) probably runs against the short, size unknown.
