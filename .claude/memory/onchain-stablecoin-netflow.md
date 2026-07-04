---
name: onchain-stablecoin-netflow
description: Candidate approach (lower priority) — stablecoin exchange netflow / supply as buy-side liquidity signal for BTC/ETH; some academic support but external-data burden
metadata: 
  node_type: memory
  type: project
  originSessionId: 30f1a354-ad20-4354-8b53-10fcc9d1bd2f
---

On-chain liquidity signals: USDT/stablecoin net inflows to exchanges as a proxy for imminent
buy-side liquidity. An arXiv study ("Return and Volatility Forecasting Using On-Chain Flows",
2411.06327) finds USDT exchange net inflows predict higher BTC/ETH returns at 1-2h horizons,
and ETH netflows negatively predict ETH returns. Slower variants: stablecoin supply ratio
(SSR), sustained BTC exchange outflows.

**Why plausible but lower priority:** Peer-reviewed-ish predictive evidence exists, and the
signal is orthogonal to anything price-derived. BUT: quality flow data is paywalled
(Glassnode/Nansen/CryptoQuant), free sources are unreliable, custodial/market-maker transfers
add noise, and the strongest documented horizons (1-2h) demand tighter execution than the
current rig. Treat as a feature source to bolt on AFTER the derivatives-data work, not a
first move. See [[execution-plan-2026-07]]; complements [[order-flow-direction]].
