# Lessons learned — running the backtester

What the rig has actually *told us* once it could run end-to-end (Phase 1 + 1.5). Distinct
from [LEARNING.md](../LEARNING.md) (a study curriculum) and the
[strategies doc](strategies.md) (how the signal layer is built). This is a findings log:
empirical results from real runs, plus the engineering lessons that came out of building and
operating the thing.

**How to read this:** every empirical result below is a **smoke test on a thin sample** —
one synthetic ratio (ETH/BTC), ~13 months of 1h candles, a backfill starting 2025-06-01.
Nothing here is a conclusion about whether the thesis is tradable; these are *directional
signals and sanity checks*. The discipline from the brief stands: assume every result is a
liar until it survives out-of-sample, fragility, and forward paper-trading.

---

## Empirical findings

### The daily-timeframe probe (ETH/BTC 1d, 1,659 bars, ~4.5y: 2021-12 → 2026-06)

The first probe off the thin 1h sample, and the first net-positive result the rig has produced.

| Strategy | Return | Max DD | Trades | Exposure | Win rate (per-trade) | Profit factor |
|---|---|---|---|---|---|---|
| RSI mean-reversion | **+2.62%** | −29.9% | 17 | 23.5% | 52.9% | **1.06** |
| EMA crossover | −39.82% | −63.5% | 22 | 34.3% | 9.1% | 0.47 |
| Buy & hold | −69.28% | −79.1% | 0 | ~100% | n/a | n/a |

Fragility kill-filter (100 perturbed runs, slippage + fill-failure): 94% positive, return
p5/p50/p95 = −0.01% / +1.74% / +2.28%, **100% beat buy-and-hold**.

- **The fee-domination hypothesis held.** The *same* RSI strategy that netted −6.03% (PF 0.86)
  on 1h goes net-positive on daily (+2.62%, PF 1.06). Fewer, larger bars → the two-taker-fee
  drag stops swallowing the per-trade edge. This is the cleanest directional confirmation yet
  that the mean-reversion pulse from finding #2 is real and was being eaten by fees, not absent.
- **Trend is confirmed the wrong shape for this series.** EMA's 9% win rate over 4.5y is the
  far end of the same coin: the ratio whipsaws trend-followers as hard as it rewards
  fade-the-move. Strengthens the "ETH/BTC mean-reverts, doesn't trend" read.
- **Don't oversell PF 1.06.** It's barely above break-even; the stress p5 is essentially flat
  (−0.01%). The kill-filter passing means "not dead," never "ship it." And the window is a
  structural ETH/BTC *downtrend* (−69%) — part of the apparent edge is just being flat ~77% of
  the time and dodging the bleed, not active alpha. Still one synthetic pair, hand-picked RSI
  params, no walk-forward/OOS. Treat as a pulse, not a P&L.
- **Bar count, not timeframe, gates the stress harness.** The O(n²) recompute (lesson #8) scales
  with bars: at 1,659 daily bars the 100-run fragility harness finished in ~2 min. The
  feature-store precompute is the unblock for *1h* stress, not daily — daily work can run the
  kill-filter today.

### Walk-forward: the search overfits, the fixed params survive (ETH/BTC 1d)

Put the daily result through the test the methodology demands: a rolling walk-forward
(train 365 / test 180 bars, 7 folds) that fits the RSI grid on each train window and scores
the chosen params on the next, *unseen* window — then, separately, the fixed default params
over the same out-of-sample span. Over the identical OOS span (2022-12 → 2026-05, 1,260 bars):

| Approach | OOS return | vs buy & hold (−63%) |
|---|---|---|
| Grid **search**, re-fit each fold | **−22.89%** | beats B&H, but loses money; 1/7 folds positive |
| **Fixed** default 14/30/50, no search | **+12.24%** (PF 1.51) | +75pp over B&H |

- **The grid search is the overfitting engine — not the strategy.** Re-fitting params every
  window turns a +12% fixed strategy into a −23% loser. The tell is param instability: the
  search picked **6 of 7 distinct** parameter sets (period swinging 7↔21, oversold 20↔35), with
  gorgeous train returns collapsing out-of-sample (fold 5: train **+72%** → OOS **−18.6%**;
  fold 2: +40% → −9.2%). In-sample ceiling (best single grid fit on the whole series) was
  +19.4% vs the −22.9% the search actually delivered forward — a ~42pp overfit gap. With only
  ~13–17 trades per window, each fold's "optimum" is decided by one or two trades, i.e. noise.
- **The fixed textbook params generalize.** 14/30/50 — never tuned to this series — returned
  **+12.24% (PF 1.51)** over the OOS span, *better* than the +2.62% full-sample read that
  started this thread. So the daily mean-reversion pulse is real and robust *as a fixed
  parameterization*; what isn't robust is optimizing it.
- **This is the direct warning shot for the GA / evolutionary north star.** If a 48-point grid
  overfits this hard on daily data, an evolutionary search with far more freedom overfits far
  worse unless validation is brutal: fitness must be **out-of-sample / purged walk-forward**
  (never in-sample), and must penalize **parameter instability** and **low trade counts**. The
  rig just demonstrated that the *search itself* is the primary overfitting risk — design the
  GA's fitness function around that, not around in-sample returns.
- **Still keep the honesty caveats.** One synthetic pair, one timeframe, and the whole window
  is a structural ETH/BTC downtrend (−63%) — the fixed strategy's +12% is heavily "be flat ~76%
  of the time and dodge the crash" (risk avoidance), not proven directional alpha. Needs other
  pairs and a non-downtrend regime before it's more than a robust *risk* result.

### Multi-pair + purged real-data run — chunk A (8 daily series, fitness + fragility)

The first run with the DB live, the purged walk-forward, and the OOS fitness function all
together — and the first time the thesis was tested across *more than one* ratio pair. Backfilled
SOL/BNB/XRP USDC legs (daily) and scored the **fixed** default genome (14/30/50) out-of-sample
with `evaluate_fitness` (4 folds, embargo 5):

| Series | B&H | mean OOS | return std | trades | fitness | per-fold |
|---|---|---|---|---|---|---|
| **XRP/ETH** | +181.1% | **+34.15%** | 25.1% | 17 | **−0.060** | +74 / +36 / +18 / +8 — **all positive** |
| **XRP/BTC** | −9.0% | **+29.33%** | 27.8% | 19 | **−0.034** | −1 / +73 / +32 / +14 |
| BTC/USDC | +23.1% | +18.30% | 21.8% | 12 | −0.44 | +40 / +23 / +27 / −18 |
| SOL/ETH | −8.3% | +6.25% | 31.9% | 15 | −0.51 | −31 / +10 / +56 / −10 |
| ETH/BTC | −69.7% | −1.83% | 8.8% | 16 | −0.31 | −12 / +0 / −7 / +12 |
| SOL/BTC | −70.2% | −2.76% | 28.2% | 16 | −0.51 | −51 / +14 / +19 / +7 |
| ETH/USDC | −62.7% | −16.41% | 18.5% | 10 | −0.85 | −40 / +9 / −8 / −27 |
| BNB/BTC† | +37.5% | −3.38% | 6.4% | 5 | −0.85 | short series, undertraded |

†BNB/USDC only lists on Bybit from 2024-08 (674 daily bars), so BNB/BTC is too short to score.

- **Pair selection is the dominant lever — bigger than any parameter.** The *same untuned*
  genome ranges from garbage (ETH/USDC −16%, SOL/BTC −2.8%) to a strong, fold-consistent edge
  (XRP/ETH +34% mean, **positive in every fold**; XRP/BTC +29%, 3/4). The ETH/BTC pulse that
  started this whole thread is actually one of the *weaker* pairs. **Implication for the GA: the
  genome must encode the pair/universe, not just strategy params** — choosing *what* to trade
  carries more signal here than choosing *how*.
- **XRP/ETH survives the fragility kill-filter cleanly.** Full-series fixed genome: **+127.3%**
  return at **−37.5% max DD** (vs B&H +176% at −69% DD) — Calmar **3.40 beats B&H's 2.55** with
  half the drawdown, PF 1.94, 59% win rate, 25% exposure. Fragility (80 perturbed runs,
  slippage + fill-failure): p5/p50/p95 = **+121% / +125% / +128%, 100% of runs positive**. It
  gives up raw upside (0% of runs beat the roaring B&H) in exchange for far lower risk — a
  robust *risk-adjusted* result, not a return-maximizer.
- **The fitness function's instability penalty is miscalibrated — this is the headline
  engineering finding.** XRP/ETH is positive in **all four** OOS folds, averages +34%, and is
  fragility-robust, yet `evaluate_fitness` scores it **−0.06 (below zero)** purely because the
  symmetric `return_std` (25%) is docked at `instability_weight = 1.0`. A symmetric standard
  deviation **cannot tell "always wins, by varying amounts" from "swings negative"** — so the
  current penalty would have the GA *reject a genuine edge*. Fix before the GA runs: penalize
  **downside / negative-fold dispersion** (e.g. count/magnitude of losing folds, or downside
  deviation), not symmetric spread. A genome green in every fold should never score negative.
- **Purged walk-forward reconfirms the search overfits on fresh real data.** ETH/BTC, embargo 5,
  total_return objective: in-sample ceiling **+19.4%** → stitched **OOS −15.6%**, 1/7 folds
  positive, **6/7 distinct** param choices. calmar objective only looks "safer" because it
  selects no-trade params (OOS −2.8%). [search-overfits] holds with the purge in place.
- **The O(n²) recompute is now the binding constraint on the GA.** A 300-run fragility stress on
  one daily pair did **not finish in >11 min** (had to drop to 80 runs); the multi-pair fitness
  sweep is only tolerable because it's the single fixed genome, not a search. Activating the
  feature-store (lesson #8) is a hard prerequisite for any real evolutionary search, not a
  nice-to-have.
- **Verdict on "is there a pulse worth scaling?"** Yes — but conditional and modest: RSI-MR has
  **no universal edge** (most pairs rejected, correctly), yet on XRP ratios the fixed genome is a
  real, fold-consistent, fragility-robust *risk-adjusted* pulse. The rig did its job in both
  directions: it rejected the weak pairs and flagged a survivor. The two concrete carry-forwards
  are **(a) make pair/universe a gene** and **(b) fix the downside-vs-symmetric penalty** so the
  GA can actually keep a winner like XRP/ETH.

### The baseline runs (ETH/BTC 1h, ~9,350 bars)

| Strategy | Return | Max DD | Trades | Exposure | Win rate (per-trade) | Profit factor |
|---|---|---|---|---|---|---|
| EMA crossover | −1.21% | −39.3% | 63 | 40.6% | 33.3% | 0.99 |
| RSI mean-reversion | −6.03% | −13.5% | 71 | 17.9% | 62.0% | 0.86 |
| RSI + 5% stop-loss | −9.72% | −17.4% | 71 | 14.6% | 60.6% | 0.78 |
| Buy & hold | +8.79% | −41.2% | 0 | ~100% | n/a | n/a |

1. **No strategy beat buy-and-hold — and that's the rig working, not failing.** A naive EMA
   crossover bleeding to fees and a mean-reversion strategy that nets negative are exactly
   what theory predicts. The value is that the rig reported it *honestly* instead of
   flattering anything. The whole "edge is the test rig, not the math" thesis depends on the
   rig being a reliable bullshit detector; so far it is.

2. **The win-rate flip is the most interesting signal.** EMA (trend) wins **33%** of trades;
   RSI (mean-reversion) wins **62%**. That flip is directional confirmation of the core
   thesis: the ETH/BTC ratio mean-reverts more than it trends. RSI also sidesteps the big
   moves — exposure 18%, max drawdown −13.5% vs buy-and-hold's −41%. On a *risk* basis it's a
   completely different, far tamer animal. The thesis has a pulse; it just isn't profitable
   yet.

3. **Read the fingerprints, not the headline return.**
   - *Trend (EMA):* 33% win rate, profit factor ≈ 1, winners ≈ 2× losers. Classic
     trend-follower — many small losses, few big wins, ~break-even before fees, then the
     two-taker-fee drag on 63 round-trips sinks it.
   - *Mean-reversion (RSI):* 62% win rate but profit factor 0.86. The textbook MR trap — win
     small often, then occasionally the dip keeps dipping and you eat a big one (pennies in
     front of a steamroller). Fat-tail losses + fees swallow the edge.

4. **A fixed stop-loss made mean-reversion worse on every metric** (return, profit factor,
   *and* max drawdown). It's structural, not a tuning miss: a stop sells *into* the dip at the
   local bottom — exactly where MR expects the bounce — so you realize the loss and miss the
   recovery the thesis was waiting for. Realized losses also compound permanently down the
   equity curve (an unrealized dip recovers; a realized loss doesn't), which is how "cutting
   losses" paradoxically *deepens* drawdown. **Stops belong to trend-following, not
   mean-reversion.** For the future search, a stop-loss "gene" is wasted (likely harmful) on
   MR genomes.

---

## Engineering & diagnostic lessons

5. **Per-bar metrics mislead; trade-level metrics diagnose.** The first metrics pass computed
   win rate *per bar*, which read 19% for a strategy that's flat most of the time (flat bars
   count as non-wins) — alarming and meaningless. Switching to **per-trade** win rate /
   profit factor, plus **trade count** and **exposure**, is what made `−1.21%` legible (few
   held positions vs steady fee bleed). Build the metric to answer "*why*," not just "how
   much."

6. **Per-bar Sharpe is uninformative at hourly granularity** — it rounds to 0.00 for
   everything because the per-bar mean/std ratio is ~0.001. Kept (the brief lists it) but
   distrusted; don't read signal into it. Crypto fat tails make Sharpe low-value anyway.

7. **The biggest performance bug was one line.** RSI recompute was **~300× slower** than EMA
   (3,000-bar bench: EMA 0.95s, RSI 288s). Cause: `_wilder_smooth` did a pandas
   `out.iloc[i] = prev` *scalar assignment per element* inside a Python loop, run twice per
   call. Writing into a numpy array instead (same math) cut it to ~8× EMA — a ~38× speedup.
   Lesson: never scalar-assign into a pandas Series in a hot loop.

8. **O(n²) indicator recompute is fine for one run, fatal for Monte Carlo.** Strategies
   recompute their indicator over the whole growing buffer every bar (the documented
   pure-function-on-buffer choice). One RSI backtest at ~9,350 bars ≈ ~38s; the 200-run
   fragility harness therefore ≈ **~2 hours** — and it's *redundant*, because the indicator is
   identical across noise-only runs. The intended fix is the **feature-store seam**
   (`BarView.features`): precompute the indicator once, feed it to every run, strategies skip
   the recompute. This is also the compute-sharing path the GA/many-bots vision needs.

9. **The data store reality diverged from the brief.** The brief says candles persist to
   Parquet; the actually-built scraper writes to **TimescaleDB** and already had a working
   reader. The backtester was pointed at Timescale (`db.read_candles`); the Parquet `store.py`
   and `fetch-data` command were retired. When the written plan and the built reality disagree,
   follow where the data actually lives.

10. **No-lookahead is structural, and worth keeping that way.** Decision on the closed bar →
    fill at the next bar's open; the strategy only ever sees data ≤ now. New features
    (stop-loss overlay, stochastic execution) were all designed to preserve this — e.g. the
    stop triggers on the just-closed bar's low (known at close) but still fills next-open, so
    it honestly *slips* on a gap rather than cheating.

---

## Methodology reminders (don't betray the rig)

- Every number here is **one thin sample**. Widening the backfill, adding pairs, and a daily
  timeframe would all change the picture — and none of it is trustworthy without walk-forward
  + out-of-sample.
- **Hand-picked parameters are overfitting bait.** The `5%` stop, the EMA periods, the RSI
  levels — those are knobs for the *search* to set under purged/walk-forward validation, never
  eyeballed into looking good.
- The fragility harness is a **kill-filter, not a badge**: failing is a red flag; passing is
  not a green light. Never tune to pass it.

---

## Open follow-ups

- **Activate the feature-store precompute** so the stress harness (and every backtest) is fast
  — the immediate unblock for using `--stress` on RSI.
- **Inter-leg gap** is unmodelled: the engine treats the synthetic ratio as one instrument,
  not two sequential ETH/USDC + BTC/USDC orders. Modelling the real two-leg rotation is the
  "sequential non-atomic legs" north-star item.
- **Thesis probes:** daily + wider history, **more ratio pairs**, and non-downtrend regimes —
  *done* (see the multi-pair chunk A run). Verdict: the effect is **pair-specific, not general** —
  RSI-MR is weak/garbage on most pairs but a real fragility-robust pulse on XRP ratios
  (XRP/ETH, which is itself an uptrend, +181% B&H — so the edge is not merely "dodge a downtrend").
- **Walk-forward / out-of-sample on the daily result** — *done* (see the walk-forward section
  above). Verdict: the fixed params survive OOS (+12.24%), the grid *search* overfits to −22.89%.
  Open from here: more pairs and a non-downtrend regime.
- **Purged walk-forward** — *built and run* (`walk_forward(..., embargo_bars=N)`, CLI `--embargo`).
  Chunk A ran it on real data with embargo 5: the search still overfits (ETH/BTC in-sample +19.4%
  → OOS −15.6% total_return). The purge didn't rescue the *search*; fixed params remain the robust path.
- **OOS-gated fitness for the GA** — *built and run* (`backtest/fitness.py`: `evaluate_fitness`).
  Chunk A surfaced a calibration bug: the **symmetric `return_std` instability penalty
  (weight 1.0) scores an all-folds-positive genome (XRP/ETH) below zero**, so the GA would reject
  a real edge. **Fix before the GA loop:** replace symmetric std with a downside / negative-fold
  penalty. This is now the first task feeding the genome + GA chunks.
- **Make pair/universe a gene.** Chunk A showed pair selection dominates parameter selection
  (same genome: garbage on ETH/USDC, strong on XRP/ETH). The genome representation (next chunk)
  should encode *what* to trade, not only *how*.
