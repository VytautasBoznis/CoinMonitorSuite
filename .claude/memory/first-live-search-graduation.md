---
name: first-live-search-graduation
description: "Live search→graduate runs: median-fitness hardening landed; a 5-seed sweep all NO-GO; the gate's absolute-return rule is regime-dependent (downtrend holdout) — winners beat B&H every time but stay absolutely negative"
metadata: 
  node_type: memory
  type: project
  originSessionId: 8a2fce32-6ba0-4032-8b1c-20285619c5ed
---

Live `coinmon search --timeframe 1d --holdout 0.2 --stress 80` runs against the DB (port **5433**;
daily history BTC/ETH ~1659 bars, SOL/XRP ~1648, BNB 676). Proves [[chunk-c-search-loop]] +
[[chunk-d-graduation-gate]] on real data, and drove two changes.

**1. Fitness hardened to MEDIAN (landed in code).** The first run (seed 0, mean-based fitness)
topped its population with `ema_crossover` XRP/ETH whose +94% "mean OOS" was one +355% fold among
+19% / −35% / +39% — a one-lucky-fold overfit ([[search-overfits-not-strategy]]). Fix:
`backtest/fitness.py` now rewards `_robust_center` = **median** of fold returns (with 4 folds, the
mean of the middle two), so neither best nor worst fold can carry a genome. `FitnessResult` gained
`median_oos_return` (drives fitness); `mean_oos_return` kept as informational. After the fix,
winners' median≈mean (e.g. seed 0: 29.3%/25.6%) — the GA now selects genuinely *consistent*
genomes, not spikes.

**2. 5-seed sweep (seeds 0–4, hardened fitness) — ALL NO-GO:**
- 0: rsi_mr XRP/BTC (med +29%) → holdout −24.3% (B&H −33.1%), 29t, frag 0%
- 1: atr_channel ETH/USDC (med +29%) → holdout −44.7% (B&H −57.4%), 9t, frag 0%
- 2: rsi_mr BTC/USDC (med +53%) → holdout −36.0% (B&H −48.3%), 8t, frag 0%
- 3: rsi_mr XRP/USDC (med +56%) → holdout −50.2% (B&H −64.6%), 42t, frag 0%
- 4: ema_cross XRP/ETH (med +49%) → holdout −32.4% (B&H −18.6%), 26t, frag 0%

**The key finding — the gate is regime-dependent.** Every winner BEAT buy-&-hold on the holdout
(usually by a wide margin) but every one was **absolutely negative**, because the last-20% holdout
tail (~330 daily bars) is a strong downtrend (B&H −18% to −64%). The graduation gate requires
*absolute* holdout return > 0, so a long/flat spot strategy that is doing its job (losing less than
B&H) still gets NO-GO'd. Fragility is 0%-positive for the same reason. This directly contradicts
the chunk-A truth that the real edge here is **risk-adjusted, not absolute**
([[chunk-a-findings]], [[daily-meanreversion-goes-positive]] "downtrend-flattered"): the gate
currently throws away the relative signal.

**Open decision for the user (don't change the gate silently):** how should graduation judge a
long/flat strategy in a down regime? Options — (a) keep absolute-return conservatism (never deploy
capital that loses money, regime be damned); (b) add/switch to a relative "beat B&H by margin M"
gate; (c) replace the single tail holdout with multiple windows / walk-forward graduation so one
regime can't decide; (d) accept that long/flat spot needs a market that isn't a sustained
downtrend and gate accordingly. Tied to whether the eventual product is long/flat spot only or
gains short capability (perp) later.
