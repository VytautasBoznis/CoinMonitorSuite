---
name: execution-plan-2026-07
description: "Ordered execution plan (set 2026-07-04) — what to implement next, replacing the dead GA indicator-permutation search"
metadata: 
  node_type: memory
  type: project
  originSessionId: 30f1a354-ad20-4354-8b53-10fcc9d1bd2f
---

Execution plan agreed 2026-07-04, after all sweeps produced 0 CERTIFIED and the user
directed a hard pivot away from price-indicator permutations
([[no-more-rsi-ema-permutations]]). The GA is officially PARKED ([[ga-parked]]); the
evidence/certification pipeline (graduation gate, fragility, edge certificate) is the
durable asset and applies to all of the below. Live execution follows the per-strategy
graduation path in [[autotrading-rollout]]. Note [[machines-and-tooling]]: not every
machine can run the stack.

Ordered by (evidence strength × data availability × speed to falsification):

1. **[[cross-sectional-momentum-portfolio]]** — first, because it needs zero new data
   (existing candle DB + 861-pair universe) and is falsifiable within a day of work. No GA:
   rank + rebalance portfolio backtest.
2. **[[funding-carry-harvester]]** — best-documented structural edge; funding data already
   scraped, funding_carry strategy stub exists. Hard part is margin/liquidation risk
   engineering, not signal discovery. No GA.
3. **[[order-flow-direction]]** — OI scraper + taker-delta sourcing + h7_flow probe. Start
   the scrapers early regardless (data accrues while other work proceeds).
4. **[[liquidation-cascade-fade]]** — start recording Bybit liquidations NOW (shallow
   history), build the event probe once weeks of data exist.
5. **[[onchain-stablecoin-netflow]]** — last; external paid-data burden, only as an added
   feature once 1-4 are resolved.

Standing rule: every approach goes through a cheap hypothesis probe (probes/h*.py pattern)
before any strategy/portfolio build, and through the existing certification gate before any
live/paper deployment.
