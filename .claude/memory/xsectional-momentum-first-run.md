---
name: xsectional-momentum-first-run
description: "W5 cross-sectional momentum (coinmon xsectional): first run LOST, then W5.2 grid+long-short+certificate (2026-07-05) gave the VERDICT — short leg beats beta (60/162 configs) but NO certifiable per-position edge (best-of-162 config REFUTED, expectancy CI straddles 0). W5 is NOT a winner; recommend moving to W3 carry"
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

**W5.2 DONE 2026-07-05 — grid + long-short + certificate (verdict: NOT a winner).** Added a
market-neutral short leg (`short_frac`, long top / short bottom, gross ~2x), a `default_grid` sweep
(162 configs: lookback×skip×top×short×rebalance, ALL recorded), and a per-position `TradeRecord`
ledger so the Edge Certificate scores one run directly (N≫300 spanning years — no cross-pair pooling
needed). CLI: `coinmon xsectional --grid --certify --short-frac`. Live run (artifact
`runs/xsectional_usdt_1d_grid.json`, 38 USDT 1d coins, benchmark −59.0%):
- **The short leg works as hypothesized** — all top-12-by-edge configs short the bottom slice;
  60/162 beat the −59% benchmark. Long-short turns momentum from a beta-LOSER into a beta-BEATER in
  a downtrend (harvests the falling basket), confirming the first-run diagnosis.
- **But NOT a certifiable edge.** Only 1/162 has positive absolute return (+22.6%). That best-of-162
  pick (look14/skip1/top30/short30/reb14, N=2606) is **REFUTED**: win 48.1%, expectancy +0.0027 with
  95% CI [−0.0055,+0.0118] straddling zero → C2 & C3 FAIL (C4 null / C6 fragility still PENDING). The
  +81.5% headline equity edge is best-of-M selection luck; the per-decision edge ≈ 0, and the
  certificate caught it — the money-loser-catch working in reverse.

**Verdict:** W5 cross-sectional momentum, even with the long-short axis, is **not a winner** (0 of
the ≥3 the [[mission-find-edge-ship-ui]] UI gate needs). The certificate on the best config is even
selection-INFLATED and still refuted. Momentum's beta-relative edge is real but per-position it's
inside the noise/fee floor — consistent with the whole [[certified-sweep-calibrated-negative]]
price-shape valley. **Still untested (optional before abandoning W5):** ≥2-regime span via
Binance-USDT 2017+ majors (this run is still one 2021-top→2026 downtrend), weighting axis, and the
best-of-M null to formally deflate the grid. **Recommended next per mission order: move to W3 funding
carry** (a structurally different return source, not another price-shape) rather than deeper W5 tuning.
