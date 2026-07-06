---
name: b16-funding-signal-refuted
description: "Fresh-ideation probe B16 (2026-07-06) REFUTED: cross-sectional funding-CROWDING signal (long lowest-funding / short highest-funding perps, dollar-neutral) has NO edge on the 41 Bybit USDT legs — 6/12 net-positive, median -0.23%/yr, recent-half -8.4%, win rates ~49-51% (coin-flip). Chosen over queued B15 hour-of-day because weekday H2 already failed. Distinct from W3 carry (directional bet, not a delta-neutral harvest) and from H6 (which only checked BTC/ETH). Fresh-ideation well now nearly dry."
metadata: 
  node_type: memory
  type: project
  originSessionId: 49a239d6-d378-4a85-8322-68078f7f322f
---

2026-07-06 session, after B14 (market-neutral low-vol, [[b13-low-vol-fresh-lead]]) turned out to be a
regime-timed short-vol bet the user asked for another fresh-ideation probe rather than Plan C.

I picked **B16 cross-sectional FUNDING-CROWDING signal** over the queued B15 (hour-of-day seasonality),
because B15's parent family — weekday seasonality (probe H2) — already FAILED and B15 is fee-fragile on
1h. `probes/b16_funding_signal.py`, log `runs/b16_funding_signal.log`.

**Hypothesis:** a perp's funding rate is a crowding gauge — persistently HIGH positive funding = crowded
longs paying up = over-extended → underperform; LOW/negative funding = unloved → outperform. So LONG the
lowest-funding slice / SHORT the highest-funding slice (dollar-neutral) should earn a crowding-reversal
premium, and the funding cashflow works WITH the signal (shorting high-funding coins also collects it).
Distinct from W3 carry ([[w3-carry-first-live-diagnosis]] — that's a per-coin DELTA-NEUTRAL cashflow
harvest; B16 is a DIRECTIONAL cross-sectional bet on different coins) and from H6 (which only tested
funding on BTC/ETH, never ranked the universe cross-sectionally).

Pre-registered frozen rule (before running): 41 Bybit USDT legs with candles+perp funding, 1d; score =
trailing MEAN daily funding over L bars, point-in-time; grid L∈{7,14,30}×q∈{0.1,0.2}×reb∈{7,14}=12;
PASS iff ≥9/12 net-positive AND median annualized ≥+5%/yr AND median recent-half >0. Honest costs (real
funding + fees). Sharpe+maxDD printed for every config (the B14 lesson: a PASS with sub-1 Sharpe / worse-
than-BTC drawdown is certificate-only, never deployable).

**Result: FAIL, clean calibrated negative.** 6/12 net-positive, median **-0.23%/yr**, median recent-half
**-8.4%**, win rates **~49-51% (coin-flip)** on every config, Sharpe mostly <0.5, drawdowns -40% to -82%.
The few positive configs (q=0.2, longer L/reb) are inconsistent and low-Sharpe — noise, not signal.
Funding-crowding is not a cross-sectional edge on the liquid survivor universe. Well-behaved numbers (no
survivorship-inflation red flag), so the refutation is trustworthy.

**Fresh-ideation scorecard since the pivot (still 0 deployable winners):** B13 low-vol long-only (PASS
rule / underperforms BTC), B14 low-vol neutral (PASS rule / short-vol crash bet, undeployable), B16
funding-crowding (REFUTED). Weekday (H2) failed; hour-of-day (B15) is weak (fee-fragile, failed parent).
The candle+funding data on hand is looking mined out — the next fork is genuinely Plan C on-chain
([[plan-c-onchain-ideation]]) or new-data collectors (Plan B P2, [[plan-b-fallback-probes]]) vs one more
fresh idea. Surface this to the user; don't silently keep probing a dry well ([[honest-status-reporting]]).