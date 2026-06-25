---
name: daily-meanreversion-goes-positive
description: "RSI mean-reversion flips net-positive on ETH/BTC daily (fee-domination confirmed); thin edge, downtrend-flattered, needs walk-forward"
metadata: 
  node_type: memory
  type: project
  originSessionId: 5095ec5a-0d98-4250-8620-a95937224a08
---

First net-positive result the rig has produced. RSI mean-reversion on ETH/BTC **1d** over
~4.5y (2021-12 → 2026-06, 1659 bars): **+2.62%, profit factor 1.06**, 17 trades, 23% exposure,
−30% max DD — vs buy-and-hold −69%. Fragility kill-filter (100 runs): 94% positive, p5 −0.01%,
100% beat B&H. EMA trend over same window: −40%, 9% win rate (trend confirmed wrong shape).

**Why:** the *same* RSI strategy nets −6% (PF 0.86) on 1h. The flip to positive on daily is
directional confirmation that the two-taker-fee drag was eating the mean-reversion edge, not
that the edge was absent — fewer/larger bars stop the fee bleed. Validates the fee-domination
hypothesis from the 1h findings.

**UPDATE (walk-forward done):** the result survives as a FIXED parameterization but the SEARCH
overfits. Over the OOS span (2022-12 → 2026-05, 1260 daily bars): fixed default 14/30/50
returned **+12.24% (PF 1.51)**, *better* than the full-sample +2.62%; but a rolling
walk-forward grid search (re-fit each fold) returned **−22.89%**, only 1/7 folds positive, 6/7
distinct param choices (train +72% → OOS −18.6% etc.). So the daily MR pulse is REAL and robust
as fixed params; what's not robust is optimizing it. Run via the `walk-forward` CLI command
(src/coinmon/backtest/walkforward.py). See [[search-overfits-not-strategy]].

**How to apply:** treat as a robust *risk* result, not proven alpha — the 1260-bar window is a
structural ETH/BTC downtrend (−63% B&H), so +12% is heavily "be flat ~76% of the time, dodge
the crash." Don't optimize the params (the search makes it worse). Still need: more pairs
(ETH/BTC-specific?), a non-downtrend regime, purged walk-forward. Related:
[[stop-loss-hurts-mean-reversion]], [[fragility-stress-test]], [[search-overfits-not-strategy]].

Side facts: **1d candles for BTC/USDC + ETH/USDC are now backfilled in the Timescale DB**
(2021-12-09 onward), ingested manually via a one-off `ingest_series(..., '1d')` — the scraper
config still only polls `["1h"]`, so daily won't stay current without adding `1d` to
`COINMON_TIMEFRAMES`. Also: the O(n²) recompute (the feature-store-seam blocker) scales with
*bar count*, so daily stress runs in ~2 min today — feature-store precompute is the unblock for
1h stress only. See [[feature-store-seam]], [[backtester-reads-timescaledb]].
