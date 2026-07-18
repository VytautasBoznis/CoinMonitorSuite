---
name: session-2026-07-18-tsmom-oi
description: "2026-07-18 session (riskier-allowed): closed 2 leads + opened the OI data frontier. B17 vol-targeted TSMOM/CTA portfolio REFUTED (median Sharpe 0.24, 3/16 pos). Built the FIRST non-candle/non-funding collector: Z0 OI backfill persisted 66,417 daily open-interest points (5+ yrs, all 41 perps) into a new open_interest table. B18 OI-crowding book FAIL but diagnostic IC=-0.03 (weak, correctly-signed crowding). B19 OI-as-trend-confirm-filter FAIL (WORSE than B17 — rising-OI = crowded = reverts). OI = real weak reversal signal, not tradeable. Still 0 deployable winners; Plan-B P2-OI tested-negative."
metadata:
  node_type: memory
  type: project
  originSessionId: SESSION_2026_07_18
  modified: 2026-07-18T13:49:48.350Z
---

Session after [[riskier-strategies-allowed]]. Docker stack was down (2 days); brought up TimescaleDB
(localhost:5433). Ran GA-free (probes only, [[ga-parked]]). All 419 tests still pass after the prod-code
changes below.

**1. Time-series momentum / CTA — REFUTED (B17).** `probes/b17_tsmom_portfolio.py`, log
`runs/b17_tsmom_portfolio.log`. The gap: every momentum test so far was cross-sectional (W5, weak) or
single-pair genome trend (GA, calibrated-negative) — never a diversified, vol-targeted, inverse-vol
TIME-SERIES-momentum PORTFOLIO that goes net-short in bears (the canonical documented crypto CTA edge,
and honestly directional/leveraged = fits "riskier"). Frozen rule (M=16: L{20,40,60,90} x reb{5,20} x
mode{LS,LO}, LEV=2), pre-registered. Result: median net **-11.6%/yr, median Sharpe 0.24** (bar 0.70),
3/16 net-positive; long-only variants blow to -92/-99% maxDD. The trend edge (a 2017-2021 BTC/ETH-era
effect) is GONE on the 2021-2026 altcoin-heavy Bybit universe — chop dominates. Best cell
(L=20,reb=20,LS +10%/yr Sharpe 0.54) is 1/16 = multiple-testing. CTA/trend closed.

**2. Built the first NEW-INPUT collector (Plan-B P2 frontier unblocked).** Prod changes (all additive,
merge-friendly natural keys per [[user-infra-ui-plans]]): new `open_interest` table in `schema.sql`;
`db.insert_open_interest`/`db.read_open_interest`; `BybitAdapter.fetch_open_interest_history` (backward
`until` pagination, mirrors funding). One-shot backfill `probes/z0_backfill_oi.py` (log
`runs/z0_backfill_oi.log`) — persisted **66,417 daily OI points, 41/41 perps, back to 2020-2021** (5+
yrs, far deeper than the ~400d I expected; Bybit retains full daily OI history, so the "lookback expires
daily" fear was overblown for OI specifically — but liquidations are still websocket-only/forward-only).
The CONTINUOUS poller (extend forward daily) remains user-owned k8s infra; this was the get-the-history
stopgap. Verified: OI ts and candle open_time both align at 00:00 UTC daily.

**3. OI frontier tested — negative, but a real weak signal found.** Two pre-registered P2 probes:
- **B18 OI-crowding** (`probes/b18_oi_crowding.py`, log `runs/b18_oi_crowding.log`): dollar-neutral book,
  long least-OI-growth / short most-OI-growth (crowding-reversal hypothesis), reuses B14's honest
  funding/fee neutral-book mechanics. VERDICT FAIL (5/12 pos, median -1.7%/yr). BUT the diagnostic pooled
  next-bar IC (Spearman-via-ranks, no scipy) is **-0.024 -> -0.034 as L grows, N~60k** — correctly signed
  for crowding (high OI-growth => mild UNDERperformance) and statistically nonzero, but |IC|~0.03 is too
  weak to clear fees/funding. Same shape as [[order-flow-probe-h7-refuted]] CVD: real contemp signal, no
  tradeable edge.
- **B19 OI-as-trend-confirmation-filter** (`probes/b19_oi_trend_filter.py`, log
  `runs/b19_oi_trend_filter.log`): B17's exact book but take a trend position only if OI is RISING (the
  futures-lore "rising OI confirms the trend" gate). VERDICT FAIL and **WORSE than B17** (0/16 pos, median
  -21%/yr). Internally consistent with B18: rising OI = crowded = about to revert, so gating INTO rising-OI
  names selects the reversers. OI is a mild REVERSAL signal, the OPPOSITE of trend-confirmation lore.

**Unified read on OI:** carries a real but economically insignificant cross-sectional crowding/reversal
signal (IC~-0.03); not deployable on this universe net of costs; does not improve trend-following. P2-OI
frontier tested-negative. The persisted 66k-point OI dataset is durable and available for any future P2
work (e.g. OI+funding combined over-leverage signal, or event-driven OI-spike liquidation-fade).

**Status:** still **0 deployable winners** toward the [[mission-find-edge-ship-ui]] 3-winner UI gate.
Candle+funding+OI on a survivor CEX universe is now thoroughly exhausted. Remaining forks for the user:
(a) build the forward liquidations collector + other P2 collectors and wait for accumulation (weeks),
(b) Plan C on-chain moonshot ([[plan-c-onchain-ideation]]), (c) accept there may be no retail-reachable
CEX edge and pivot the mission. See [[plan-b-p1-results]], [[plan-b-p3-results]], [[b16-funding-signal-refuted]].
