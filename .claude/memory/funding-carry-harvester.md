---
name: funding-carry-harvester
description: "Candidate approach — delta-neutral funding-rate carry (long spot, short perp), the best-documented structural edge in crypto; income strategy, no prediction, no GA"
metadata: 
  node_type: memory
  type: project
  originSessionId: 30f1a354-ad20-4354-8b53-10fcc9d1bd2f
---

Funding carry: when perp funding is meaningfully positive, hold spot long + equal perp short;
collect funding while price exposure nets to ~zero. Rotate across coins by funding level;
exit when funding flips/compresses. This is harvesting a structural premium caused by market
segmentation and limits-to-arbitrage (retail long-leverage demand), not predicting price.

**Why plausible:** The single best-documented crypto edge: BIS Working Paper 1087 "Crypto
carry", CMU "The Crypto Carry Trade" (Christin et al.), CEPR column on market segmentation.
Industry reports ~19%/yr with <2% drawdown in 2025 for professional implementations. The
project already scrapes funding_rates and has a funding_carry strategy stub + h6_funding
probe — this direction is half-built.

**How to apply:** NOT a GA candidate — it's a yield system whose hard parts are risk
engineering: liquidation risk on the short perp leg during pumps (BIS: 10x leverage would
have been liquidated in half the sample months — use ~1-2x), funding flips, borrow/transfer
frictions, no cross-margin between spot and perp. Backtest = funding accrual minus fees minus
realistic margin calls. See [[execution-plan-2026-07]]; related [[order-flow-direction]].
