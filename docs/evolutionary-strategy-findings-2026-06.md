# Evolutionary strategy search — findings & skeptical review (2026-06)

A self-contained briefing on what the search pipeline found, written so a reader (human or LLM)
can evaluate it cold. Deliberately surfaces the weak points.

## 1. What the system is

A from-scratch crypto backtesting + strategy-search pipeline (Python, daily OHLCV from Bybit,
TimescaleDB). The goal is **not** to hand-design a strategy but to build an honest *evaluation rig*
and let a genetic algorithm (GA) search, with multiple independent filters meant to reject
overfitting. Guiding discipline: **"the search overfits; trust the out-of-sample gate, not the
search."**

A "genome" encodes: a strategy **family** + **params**, the **pair** (cross-coin ratios are
synthesized from two USDC legs), a **direction mode** (long-only, or regime-adaptive: long in an
up-regime, short in a down-regime by a point-in-time moving average), **leverage** (1–5x, via a
perpetual-futures portfolio model), and an optional intrabar **stop-loss**.

## 2. The validation pipeline

1. **Out-of-sample fitness** — K purged/embargoed walk-forward folds (not in-sample).
2. **Graduation gate** — the GA winner is run on a **holdout tail** (last 20%) the search never saw;
   must be (a) profitable, (b) ≥15 trades (evidence floor), (c) survive a **fragility Monte-Carlo**
   stress test (200–300 runs with random slippage / fill-failure) staying positive.
3. **Cross-pair robustness tagger** — the *same genome* is re-run with its pair swapped onto 5
   randomly-chosen decorrelated pairs; profitable on ≥3 → **GOLDEN** (generalizes), own pair only →
   **SPECIALIST** (pair-specific). A label, not a kill-switch.

Run across **many seeds**; verdicts aggregated. Key diagnostic: do winners **converge** on the same
strategy/pair across seeds (consistency) or **hop around** (lottery / overfit)?

## 3. What was done

- Added a **bounded multi-indicator genome**: the GA composes a rule from an indicator menu
  (e.g. `macd_hist(20) > -0.0077 AND rsi(2) > 13.75`), capped shape so the overfit surface grows in
  a controlled way. Explicit test: does the gate still hold against a bigger search space?
- Large search: **30 seeds × pop 300 × 80 generations × 10 OOS folds × 300 fragility runs × 5-pair
  cross-pair**, ~48 min, 15-pair universe (5 coins).

## 4. The headline finding

First-ever **GOLDEN** tags. Across 30 seeds: **9 GO; 3 GOLDEN, 6 SPECIALIST.** All 3 golden were the
**same class**, which also passed on **6 of 30 seeds** — a convergent attractor, not a random hop.

The golden strategy:
- **RSI mean-reversion on BNB/ETH**, regime-adaptive, **~2x perp**, 50% stop (never triggers — too
  wide), `period=2, oversold=39, exit=73`.
- **Holdout +29%** vs **buy-and-hold +13.7%** — and B&H was *positive*, so it is **not** a crash-short
  (every prior winner in the project's history was). It actively trades a rising market.
- Fragility: 300 runs, **100% positive, 100% beat B&H.**
- Cross-pair: held on **4/5 decorrelated pairs** (BTC/XRP +21%, BNB/USDC +15%, ETH/XRP +141%,
  BNB/SOL +61%; one missed).
- **Execution-parity forward test:** driven bar-by-bar through the live engine, reproduced the
  backtest to the cent; trade tape longs rallies and flips short through a drawdown, ~28 trades /
  134 days, 27.6% max drawdown.

## 5. Honest caveats

- **The forward test replays the SAME holdout the gate scored** — execution parity, **not** fresh
  out-of-sample. No post-holdout data exists yet.
- **Small, correlated universe** — 5 coins → 15 pairs; "decorrelated peers" still share legs.
- **Short series for the winning pair** — BNB/ETH ~676 daily bars → 134-bar holdout, ~19 trades.
- **`period=2` RSI** is a classic data-miner's sweet spot (Connors-style); highly parameter-sensitive,
  regime-dependent. Combined with 2x leverage = blow-up risk in a real liquidity event.
- **Single overall regime**; one ~4-year window doesn't prove persistence.
- **Multiple-comparisons burden** — 30 seeds × 300 pop × 80 gen × families × 15 pairs; cross-pair on
  5 correlated peers may be insufficient correction.

## 6. Skeptical reviewer's verdict (second LLM)

> "Still most likely overfitting / data-mined artifact, not strong evidence of a structural edge."
> The rig is better than most retail quant efforts; convergence across seeds and cross-pair are the
> strongest positives. But RSI(2) is a notorious data-miner's delight, the universe is small and
> correlated, history per pair is short, and it's a single regime. Most consistent with a lucky/overfit
> survivor. **Don't trade real capital yet.** Most informative next test: a **strict nested holdout** on
> the most recent bars, untouched by search/gate/cross-pair during development; test the finalized
> genome there. Other follow-ups: parameter-stability walk-forward, a broader/truly-decorrelated
> universe, live paper-trading with funding/slippage, and a randomized-strategy benchmark.

## 7. Strict nested holdout — the decisive test (result)

Reserved the most recent **120 bars (late Feb–Jun 2026) as an untouched future set**, re-ran the
ENTIRE process (search → gate → cross-pair) on dev-only data (≤ 2026-02-26, 10 seeds), then tested
each seed's finalized winner FRESH on the future tail (return, trades, vs B&H, fragility re-run).

| metric | result |
|---|---|
| GOLDEN on dev-only | **0** (vs 3 in the original full-data run) |
| BNB/ETH RSI(2) golden genome | **never reappeared** once the holdout regime moved earlier |
| dev-GO genomes that generalized to the future | **0 of 2** |
| the 2 dev-GO winners (ema_crossover BTC/SOL adaptive) | **−0.9%** future vs **B&H +14.2%**, fragility 2% |
| future "winners" (seed 2 +74%, seed 9 +18%) | were **dev-NO-GO** (gate rejected them), 3–7 trades = noise |

**Conclusions:**
1. **The golden convergence was regime-specific, not structural.** It existed only because the
   holdout was the Feb–Jun bull tail; moving the holdout back four months yields 0 golden and the
   BNB/ETH RSI(2) genome wins no seed. Strong evidence of a data-mined artifact (as predicted of RSI(2)).
2. **Passing every gate on one window bought no edge on the next** — endorsed (dev-GO) genomes went
   0/2 out-of-sample and lost to buy-and-hold; the future profits came only from gate-REJECTED genomes
   on tiny trade counts (luck).
3. **The gate is not a rubber stamp** (only 2/10 dev-GO; it distrusted the lucky high-variance combos),
   and chunk P didn't break it (no false golden) — but "passed the gate" ≠ "persistent edge."

**Verdict: confirms overfitting / regime-specificity. The golden tag did NOT survive a strict
temporal nested holdout. No real capital should go near this.** (Test caveat: only 120 future bars,
and dev-holdout vs future are different regimes, so 0/2 dev-GO is itself a small sample — but the
golden-disappears finding does not depend on sample size.)

No real capital is at risk anywhere in the system (no trade-permission keys exist; everything to
date reads data and simulates).
