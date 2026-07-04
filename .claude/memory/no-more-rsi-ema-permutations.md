---
name: no-more-rsi-ema-permutations
description: User directive (2026-07-04) — price-transform indicator strategies (RSI/EMA/ATR/Donchian permutations) are exhausted and must not be the focus anymore
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 30f1a354-ad20-4354-8b53-10fcc9d1bd2f
---

The user explicitly and emphatically directed (2026-07-04): stop focusing on RSI / EMA /
price-transform indicator strategies. Many sweep runs confirmed nothing certifies from that
family — 0 CERTIFIED across all sweeps, GO winners always refuted or unproven with negative
per-trade expectancy. Repeating permutations of them is wasted compute.

**Why:** The GA's searchable registry in `src/coinmon/search/genome.py` contains only seven
families, six of which are close-price transforms (rsi_meanreversion, ema_crossover,
atr_channel, donchian_breakout, ratio_momentum, indicator_combo). Every sweep necessarily
outputs these, and repeated evidence shows no edge there. Big holdout returns came from
leverage riding trends, not entry edge.

**How to apply:** Do not propose, prioritize, or build more price-indicator permutation
strategies or tweaks to them. Direction the user is interested in instead: order-flow and
positioning signals — taker buy/sell volume delta (CVD), open-interest trends, long/short
ratio, funding (funding_rates table already exists). See [[order-flow-direction]]. If RSI/EMA
families come up, treat them as legacy; they may remain as baseline/control only.
