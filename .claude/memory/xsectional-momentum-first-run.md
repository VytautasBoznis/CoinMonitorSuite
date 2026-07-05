---
name: xsectional-momentum-first-run
description: "W5 cross-sectional momentum backtester BUILT (coinmon xsectional) + first live run 2026-07-05: default config LOSES vs equal-weight benchmark, but the universe is a 2021-top-anchored downtrend — not yet a verdict on the effect"
metadata: 
  node_type: memory
  type: project
  originSessionId: 35fc8b90-e0c9-4650-ad74-ff859246376e
---

First mission candidate ([[cross-sectional-momentum-portfolio]], [[mission-find-edge-ship-ui]]) is
now runnable. Built 2026-07-05:

- **New module** `src/coinmon/backtest/xsectional.py` — a MULTI-instrument backtester (distinct from
  the single-series BarStepper): ranks the whole quote universe by trailing return each rebalance,
  holds the top slice equal-weight, charges fees on turnover. Benchmark = equal-weight universe
  (crypto beta), same cadence/fees. Emits a pooled per-position outcome ledger (the N the certificate
  will use). CLI `coinmon xsectional`; 6 tests (incl. a no-lookahead guard); 399 suite green, ruff clean.
- **First live run** (artifact `runs/xsectional_usdt_1d.json`): Bybit USDT 1d, 38 coins, lookback 28 /
  skip 1 / top 20% / weekly, 257 rebalances, N=1748 positions. **Strategy −79.6% vs benchmark −71.8%
  (edge −7.8pp), win-rate 40.6%.** A LOSER, and worse than beta.

**Do NOT over-read this as "momentum is dead":** the Bybit USDT history starts ~2021-07 for most
coins (1823 bars), so this universe is essentially the 2021-top→2026 altcoin basket — a secular
downtrend where the benchmark itself is −72%. Long-only momentum bleeds in a downtrend. This is ONE
pre-registered default config, not the [[portfolio-search-protocol]] verdict.

**Next chunk (not yet done):** the exhaustive config grid (lookback/skip/slice/rebalance/long-short/
weighting) ALL RECORDED with multiple-testing deflation, the portfolio-level Edge Certificate + nulls,
and — critically — a ≥2-regime span (pull the Binance USDT 2017+ majors and/or the longer-history
coins so the sample isn't one crash regime). Long-short (short the bottom slice) is the obvious axis
to test given the downtrend: the losing basket is exactly what a short leg would harvest.
