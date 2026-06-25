---
name: feature-store-seam
description: BarView point-in-time feature-snapshot seam; future post-scraper indicator engine path; kept as cache not contract
metadata: 
  node_type: memory
  type: project
  originSessionId: b4371132-6a7e-48a5-87bc-b1f5638e7457
---

Decision (2026-06-25): the strategy contract is `Strategy.on_bar(view: BarView) -> int`, where `BarView` = current closed candle + an optional point-in-time `features` map (precomputed indicators known as-of that bar). Defined in `src/coinmon/feed.py` alongside `CostModel`.

This was generalized from a bare `on_bar(candle)` to keep open a future **post-scraper indicator engine**: scraper saves raw → indicator engine computes indicators once → stored in DB → many bots read precomputed values instead of each maintaining its own buffer (compute-sharing for the [[blackbox-evolutionary-vision]] GA many-bots path; fits [[deployment-target-k8s]] as its own container).

**Why / constraints (the hard lines):**
- It must stay a **cache, not the contract**. Strategies must still work from `candle` alone (feature absent → compute from own buffer), or backtest/live parity breaks.
- **Point-in-time correctness is the whole point**: a feature value is keyed to the closed bar it was computed at; only serve `indicator[t]` from bars ≤ t. Same closed-bar discipline the scraper already enforces. This preserves structural no-lookahead.
- "Compute all indicators" doesn't close — indicators are parameterized and the GA evolves params, so the store is a **fixed-menu fast path** (feature key convention `ema_<period>`, `rsi_<period>`), with candle-recompute fallback for novel params.

**How to apply:** the indicator-engine container itself is **deferred** — build it only once the Phase 1 backtester proves a strategy worth scaling (don't build speculative infra). The seam is in place so nothing blocks it. Step-5 strategies already read features-if-present, else recompute.
