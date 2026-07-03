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

**W3 step 2 SPLIT again (user chose primitives-first + market-neutral hedged carry over a
directional funding bet — H6 says funding is a collectible premium, not a timing signal).**

**W3 step 2a DONE (this session):** the two new PURE, unit-tested primitives —
- `CarryPortfolio` (`backtest/portfolio.py`): market-neutral hedged book, long spot + short perp
  on the SAME candle series so price legs cancel → `equity()` is price-INDEPENDENT (returns cash);
  only 4 taker-fee legs (each on cash/2, self-funded 1x) + per-bar funding move it. `target` 1
  hedge-on / 0 flat. `apply_funding` credits the short (`-perp_units*price*rate`, notional drifts
  with the mark). No liquidation (no price risk). `ClosedTrade(direction=0)` = market-neutral (2b
  ledger interprets 0). ~45 lines. Verified end-to-end: price swung 10→20→5→40→10, equity stayed
  pure-funding.
- `align_funding(funding_df, candle_times)` (`data/funding.py`): sums 8h settlements into each
  bar's `[t_i, t_{i+1})` window (settlement on an open-time belongs to that bar; pre-first &
  far-future-beyond-last-bar-spacing dropped). Feeds the step-1 `BacktestEngine.run(funding=...)`.
355 tests green (+13), ruff clean. Engine/genome UNTOUCHED — pure primitives only.

**W3 step 2b DONE (this session):** the `funding_carry` FAMILY + the genome→book/stop seam.
- `strategies/funding_carry.FundingCarry(window, entry_pct)`: reads the point-in-time
  `funding_rate` feature, keeps a bounded (N1) rolling window, hedges on (target 1) only when the
  current rate is POSITIVE and ranks ≥ `entry_pct` quantile of the window (funding at its richest),
  flat (0) otherwise — never pays to hold. No-funding bars (ratios / `funding=None` runs) → flat.
- **The family→portfolio decoupling seam:** `StrategyFamily` gained an optional
  `portfolio: (cash,fee)->Portfolio` factory. A market-neutral family sets it (funding_carry →
  `CarryPortfolio`); `decode_portfolio` returns it and the direction/leverage genes go inert.
  `decode` never wraps a market-neutral family in `RegimeAdaptive` (no directional side). New
  `decode_stop(genome)` returns None for market-neutral families (a hedged carry has no price side
  to stop out, and a price stop would tear the hedge apart) — wired into EVERY genome→engine call
  site (runner `_score_genome`+fragility, graduation, evidence/certify) replacing raw
  `genome.stop_pct`. Registration-only for the GA otherwise (sample/mutate/crossover unchanged).
- 372 tests green (+17 test_funding_carry.py), ruff clean. Adding the 6th family shifted the GA RNG
  but the pop40/gens20 improve test (bumped in W4) held. Engine-verified end-to-end:
  `BacktestEngine.run(candles, funding=[...])` on a carry genome harvests the premium and books a
  direction-0 round-trip; `funding=None` → flat/0 trades.

**Deferred to W3 step 2c (the integration layer):** thread REAL funding through the search rig —
`CandleCache` must load+`align_funding` per DIRECT USDC perp (not ratios) and carry it (cleanest:
a `funding_rate` COLUMN on the candle frame so fold/holdout/fragility slicing carries it for free,
leaf engine calls extract+pass), CLI wiring of `db.read_funding`, parallel worker funding, + the
live feed. Until 2c the family is REACHABLE but un-searchable (funding=None → carry always loses
to fees → GA rejects it), same "registered, alpha unproven" state as W1/W4 but data-gated.
See [[build-roadmap]] chunk W, `.claude/plans/alpha-hunt.md` §W3.
