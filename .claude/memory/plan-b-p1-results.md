---
name: plan-b-p1-results
description: "Plan-B Tier P1 free probes (B1-B4) ALL RUN 2026-07-06 → all FAIL. Post-shock reversal, volume shock, cross-venue lead-lag dead; weekly rebalancing premium a near-miss (68% vs 70% bar, +6.2%/yr mean, but it's an overlay not a strategy). Testable-today candle-shape signals exhausted; next = P3 cost-side (B9/B10, testable now) + P2 collector-gated"
metadata: 
  node_type: memory
  type: project
  originSessionId: 040f02e6-16e3-4c02-b338-1ec313bfc38d
---

Ran the full Plan-B P1 tier ([[plan-b-fallback-probes]], `.claude/plans/alpha-hunt-plan-b.md`
§P1) on 2026-07-06 after order-flow H7 refuted ([[order-flow-probe-h7-refuted]]). All frozen
rules transcribed verbatim; all on 4h/1d Binance-USDT majors from the local DB (deep candle
history). Scripts: `probes/b1_shock_reversal.py`, `b2_volume_shock.py`, `b3_cross_venue.py`,
`b4_rebalance_premium.py`.

- **B1 post-shock reversal — FAIL 0/5.** 3-bar CAR after a <−2σ 4h bar: every major's CI
  straddles 0; no bounce, let alone one clearing round-trip cost.
- **B2 volume shock — FAIL.** Only XRP up-branch significant (1/5, need ≥3); the cross-coin
  guard correctly rejects 1-of-5 as noise (same as T0's H2).
- **B3 cross-venue lead-lag — FAIL 0/5.** lag-0 corr = 0.999 (Binance/Bybit perfectly
  arbitraged), lag-1 ≈ 0 both directions. Arbitrage closes any 4h cross-venue signal, as
  expected.
- **B4 rebalancing premium — FAIL (narrow miss, the only sign of life).** Weekly rebalance:
  premium>0 in **68.0%** of rolling-1y windows (bar = 70%), **mean +6.2%/yr** over
  buy-and-hold; daily loses to fees (63.3%, −2.7%). Real-ish variance harvest at weekly
  cadence but sub-threshold — AND it's a portfolio overlay with no trade ledger, so even a
  PASS funds an overlay-certification design note, not a family. Basket was the 5 correlated
  majors, so this is a conservative lower bound (decorrelated basket would harvest more).

**Conclusion:** every testable-today candle-shape / order-flow signal is now exhausted (H7 +
B1–B3 dead, B4 an overlay near-miss). This is exactly the calibrated-negative thesis holding —
retail-reachable edge is NOT in price/volume shape on daily/4h candles. Confirmed winner count
still **1** (W3 carry, [[w3-carry-first-live-diagnosis]]); UI gate is ≥3.

**Next per the plan's priority (P1→P2→P3/P4):** P2 (B5–B8: OI/basis/positioning/listing) is
COLLECTOR-GATED — no scraper/tables exist yet (Z0 not built; only candles+funding in schema).
The testable-today remainder is **P3 cost-side B9/B10** (re-run Y's top-10 with maker fees;
1h maker-hurdle check — recycle existing artifacts, no new data) and **P4 B11/B12** (external
free CoinGecko: stablecoin supply, BTC dominance). Recommend B9/B10 next (cheapest, may reveal
the fee hurdle — not signal absence — killed the families), then decide on Z0 collectors vs P4.
