---
name: order-flow-probe-h7-refuted
description: "Order-flow candidate (#3) tested 2026-07-06: taker-flow/CVD leg REFUTED (probe H7); OI leg = POTENTIAL BUT PARKED pending Z0 collector data (no scraper/table exists yet). User verdict: keep for future Z0 investigation, moved on to Plan-B P1"
metadata: 
  node_type: memory
  type: project
  originSessionId: 040f02e6-16e3-4c02-b338-1ec313bfc38d
---

Ran the pre-registered order-flow probe `probes/h7_flow.py` (H7) on 2026-07-06, the third
candidate in [[execution-plan-2026-07]] after W5 (not a winner) and W3 carry (the one winner).

**Taker-flow / CVD leg — REFUTED (clean calibrated negative).** Frozen rule: next-bar IC
= corr(per-bar taker imbalance = (2·takerBuyBase − vol)/vol, logret_{t+1}), PASS if 95% CI
excludes 0 same-sign on ≥2/4 majors. Result on 4h Binance USDT majors (2021→2026, ~12k bars
each): contemporaneous corr **+0.36 to +0.40** (signal is real & correctly measured — taker
buying moves price *inside* its own bar), but next-bar IC **≈0** everywhere (−0.006..+0.005),
every CI straddles 0, **0/4 significant**. Order-flow imbalance is fully absorbed within its
own bar — same efficiency wall the price-shape families hit ([[no-more-rsi-ema-permutations]],
[[certified-sweep-calibrated-negative]]). Deepest-history order-flow leg, tested and dead.

**OI-change leg — collector-gated, NOT testable today.** Exchange-served OI history is only
~30 days (Binance ~180 pts, Bybit ~200 pts at 4h) — trade-starved, can't span regimes for a
certificate. No `open_interest` table or scraper exists (schema has only candles/raw_candles/
funding_rates). Same for **#4 liquidation-cascade fade** ([[liquidation-cashcade-fade]] /
[[liquidation-cascade-fade]]): no liquidations table/collector, exchange serves ~no history.

**So of the remaining candidate list, #3 is done to the extent data allows (deep leg refuted),
and #3-OI / #4 / #5 all need collectors that DON'T EXIST YET and weeks of accrued lookback.**
This is the Z0-collector gate the mission flagged ("lookback expires daily"). Fork for the
user: (A) build the Z0 collectors now to start accruing OI/liq/long-short history, or (B) move
to Plan-B P1 free probes (post-shock reversal / volume shock) that ARE testable today on
existing candle data. Testable-today price/flow signals are looking exhausted; the live edge
frontier is new *collected* inputs. Winner count still 1 ([[w3-carry-first-live-diagnosis]]);
UI gate is ≥3 ([[mission-find-edge-ship-ui]]).
