---
name: liquidation-cascade-fade
description: Candidate approach — event-driven mean reversion after forced-liquidation cascades; economically grounded (forced sellers are price-insensitive); needs liquidation data collection NOW
metadata: 
  node_type: memory
  type: project
  originSessionId: 30f1a354-ad20-4354-8b53-10fcc9d1bd2f
---

Liquidation-cascade fade: detect bursts of forced liquidations (liquidation feed volume spike
+ extreme short-window price move + OI collapse), then fade the move — long after a long-
liquidation flush, betting on the V-shaped snap-back once forced sellers are exhausted.
Horizon: minutes to hours. Event-driven, few high-conviction trades.

**Why plausible:** Forced sellers are price-insensitive by definition — the classic
economic precondition for short-term reversal. Crypto has repeated multi-billion-dollar
cascades (Sept/Oct 2025: $1.5B and $19B single-day wipeouts) and documented post-cascade
recoveries; market-maker literature (Amberdata etc.) treats post-cascade imbalance as a
known opportunity window.

**How to apply:** Requires Bybit liquidation stream/REST + OI — historical liquidation data
is shallow, so START RECORDING EARLY even before building the strategy (cheap scraper
addition). Overlaps with [[order-flow-direction]] data work (OI, taker delta). Certification
challenge: event strategies produce few trades — pool across many symbols to reach N. No GA
needed: the detector is a hand-built event definition + probe (h8 style) first. See
[[execution-plan-2026-07]].
