---
name: w3-funding-cashflow
description: "chunk W3 step 1: perp funding modeled as an honest per-bar cashflow + funding_rate fed into the feed; W3 is split because carry capture needs structural seams, not a registration-only family"
metadata:
  node_type: memory
  type: project
  originSessionId: continue-w3
---

**Why W3 is NOT a registration-only family** (unlike [[w1-ratio-momentum-family]] /
[[w4-donchian-breakout-family]]): the H6 probe reshaped it — funding is a COLLECTIBLE
PREMIUM, not a timing signal (IC≈0). Capturing it honestly means being market-neutral
(long spot + short perp) to collect funding without eating price direction, but the engine
is single-instrument/directional and `PerpPortfolio` modeled NO funding. So W3 needs two new
seams: (1) funding priced as a cashflow in the perp book, (2) a way to express a hedged carry
position + the funding_carry family. User chose to SPLIT W3 into sessions; this is step 1.

**W3 step 1 DONE (this session):**
- `PerpPortfolio.apply_funding(rate, price)`: `cash -= units * price * rate` (units signed).
  rate>0 ⇒ longs pay shorts, so a long bleeds / short collects. No-op when flat or liquidated.
  Base `Portfolio.apply_funding` is a concrete NO-OP so spot inherits "pays no funding" and the
  interface stays clean (no isinstance checks). Funding flows into `cash` ⇒ automatically into
  equity, round-trip PnL, and can tip an over-levered position into liquidation (no extra
  accounting). Per-BAR aggregate of the 8h settlements at the bar CLOSE — the granularity the
  backtest's bar prices support, documented like the close-only liquidation check.
- `BarStepper.step(candle, funding_rate=None)` + `BacktestEngine.run(candles, funding=None)`:
  when a per-bar funding series is supplied it (a) charges `apply_funding` on the position held
  into the close and (b) exposes the rate as the `funding_rate` BarView feature (so step 2's
  carry family reads it point-in-time). **`funding_rate=None` / `funding=None` = byte-unchanged**
  (no feature, no cashflow) — parity preserved for every existing run/test.
- 342 tests green (+10 in test_backtest.py), ruff clean.

**Deferred to W3 step 2:** the alignment helper (8h settlements → per-bar array via
`db.read_funding`), live/runner wiring, and the `funding_carry` FAMILY + hedged carry structure.
The engine capability + feed seam landed here; the family that consumes it lands next.
See [[build-roadmap]] chunk W, `.claude/plans/alpha-hunt.md` §W3.
