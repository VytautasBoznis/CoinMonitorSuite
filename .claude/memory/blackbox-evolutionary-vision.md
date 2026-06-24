---
name: blackbox-evolutionary-vision
description: "North star: engine is a live-compatible black-box exchange; evolutionary/GA strategy search is the long-term path to alpha"
metadata:
  type: project
---

**Driving architectural principle (firm, user 2026-06-24):** the backtest engine is a **black-box exchange** — the strategy talks only to a point-in-time data feed (bars one at a time, nothing past the current bar) + an order-submission API, the *same contract a live exchange adapter implements*. Going live = swap the simulator for the real Bybit adapter, strategy unchanged. Makes no-lookahead structural, and is the seam future work spawns many strategy instances against. Must be **event-driven, not vectorized**. See [[phase-1-backtester]].

**Orders are sequential, not atomic.** A synthetic-ratio rotation = two separate orders (sell ETH/USDC, then buy BTC/USDC) with a gap → second leg drifts (achieved ratio ≠ signalled), legs can partial-fill or fail (half position in USDC). On a CEX (Bybit) these are internal matching-engine fills, **not** per-trade on-chain settlements — blockchain confirmations apply only to deposits/withdrawals or to a DEX venue later. Modeled as inter-leg latency + per-leg slippage/partial-fill (baseline = zero gap; Phase 1.5 adds it). See [[fragility-stress-test]].

**Long-term north star:** an **evolutionary / genetic-programming strategy search** — spawn many bots on backtest data, profitability + robustness as the reward — where the black box feeds each bot data and the [[fragility-stress-test]] (lag/slippage/dropped-data) is part of fitness so fragile overfits die. **Far-future phase**, only the black-box seam is built now.

**Why:** this is the user's chosen path *because* they have limited quant math (see [[user-quant-background]]) — they build the rigorous evaluation rig and let search find edge, rather than hand-deriving alpha.

**How to apply:** keep the data-feed + order API the single boundary the strategy sees; never let a strategy read the full series. A naive GA is an overfitting machine — any future GA work is gated on strict out-of-sample/walk-forward + fragility-as-fitness, and the harness must be proven to *reject* deliberate garbage before being trusted.
