---
name: cross-sectional-momentum-portfolio
description: "Candidate approach — rank the whole coin universe weekly, long top-decile / short bottom-decile; academically supported, needs ZERO new data, no GA"
metadata: 
  node_type: memory
  type: project
  originSessionId: 30f1a354-ad20-4354-8b53-10fcc9d1bd2f
---

Cross-sectional (relative) momentum: every rebalance (e.g. weekly), rank all coins in the
universe by trailing return (1–4 week lookbacks), go long the top decile and short (or just
avoid) the bottom decile, equal-weighted. Contrast with the dead per-pair time-series
indicator search: the bet is on *relative ordering* across many coins, which diversifies away
single-pair overfitting — the exact failure mode of the GA sweeps.

**Why plausible:** Best-replicated anomaly in crypto academic literature (JFQA "A Trend
Factor for the Cross-Section of Cryptocurrency Returns"; factor-momentum studies report
~1.65%/week winner portfolios, Sharpe ~1.28). Fama-MacBeth-tested factor, not a curve-fit.

**How to apply:** Implementable TODAY with the existing candle DB (861-pair universe already
built) — no new scraper, no GA. Portfolio backtest = rank + rebalance loop; the existing
evidence/certification machinery applies to the portfolio's rebalance-period returns. Highest
priority in [[execution-plan-2026-07]] because it is the fastest falsifiable test. Beware:
fees on weekly full-portfolio turnover are the main killer — model them first. Testing and
certification follow [[portfolio-search-protocol]] — no pair parameter, exhaustive grid,
portfolio-level certificate against an equal-weight universe benchmark.
