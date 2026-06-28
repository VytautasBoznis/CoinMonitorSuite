---
name: leverage-breaks-fitness-scaling
description: "First live K2 search: GA picks a 4.6x perp short and NO-GOs at graduation — the gate works, but the OOS fitness is mis-scaled for leverage (rewards lucky leveraged folds, under-penalizes liquidation), so the search is pulled toward reckless leverage"
metadata:
  node_type: memory
  type: project
  originSessionId: continue-2026-06-28
---

**First live search after wiring direction into the GA (chunk K2), 2026-06-28.** Ran
`coinmon search --timeframe 1d --holdout 0.2 --stress 80` (seed 0, pop 30, gens 12) against the
live Docker DB (1d: BTC/ETH/SOL/XRP USDC ~1650 bars each, BNB 676; all UNIVERSE ratios computable).

**Result — the plumbing works, the calibration doesn't.**
- GA winner: `atr_channel` on `XRP/ETH`, **4.6x perp short** — so K2 is wired end-to-end: the GA
  explored the `short`/`leverage` genes and the winner is a leveraged short, with `decode_portfolio`
  feeding a `PerpPortfolio` through fitness + fragility + graduation.
- In-search fitness +5.48, **median OOS +607%**, per-fold `+169%(6t) / -100%(7t) / +1046%(1t) /
  +1784%(4t)` — i.e. one liquidation wipeout (-100%) plus two lucky high-leverage folds (one a SINGLE
  trade). Pure leveraged noise dressed up as a huge median.
- **Graduation gate: NO-GO** (holdout -99.32%, fragility 0% positive). The unseen-holdout + fragility
  gate caught the blow-up exactly as designed — no money-losing strategy got blessed. The safety
  architecture (absolute gate + bearish leg instead of softening, see [[perp-short-capability]]) held.

**The new problem (the actionable finding).** The OOS fitness ([[search-overfits-not-strategy]],
`backtest/fitness.py`) was calibrated for SPOT returns (~-1..+1). Under Nx leverage:
1. Returns balloon to hundreds-of-percent, so even the *robust median* is dominated by one lucky
   leveraged fold (median of `[-100, 169, 1046, 1784]` = +607).
2. Downside is floored at -100% (liquidation), so `downside_dev` ≈ 0.50 max — trivial next to a +607
   median. The instability penalty can't bite a leveraged genome.
So the SEARCH is now reliably pulled toward reckless leverage (it pays in-sample), wastes its budget
there, and its winner almost always NO-GOs at graduation. The gate saves us every time, but the
search is fishing in the wrong pond. This is the same overfit story as before, with **leverage as the
new overfit vector**.

**Candidate fixes (next session, unverified — pick one or combine):**
- Penalize/zero-out any fold that liquidates (a -100% fold should torch fitness, not just contribute
  -1.0 to an RMS) — treat liquidation as disqualifying, not merely a bad number.
- Make the fitness scale-aware: reward *risk-adjusted* return (per-fold Sharpe/Calmar or
  return-per-unit-leverage), or normalize fold returns by leverage so a 4.6x +1784% fold isn't worth
  4.6x a 1x fold.
- Add a soft leverage prior/penalty in fitness (the eval rig was *supposed* to be what punishes
  reckless leverage — it does at graduation, but not in per-genome selection, which is the gap).
- Tighten the `LEVERAGE = ParamSpec(1.0, 5.0)` range and/or raise the `min_trades` floor so 1-trade
  folds can't carry a genome.

Recommend leaning on liquidation-disqualification + a risk-adjusted (not raw-return) fold metric;
revisit before declaring the live downtrend-GO proven. Tie back to [[build-roadmap]] chunk K.

**UPDATE 2026-06-28 — Part B landed (convex drawdown penalty), partially fixes this.** `evaluate_fitness`
now subtracts a `drawdown_penalty` anchored to recovery asymmetry `g(d)=d/(1-d)`: the WORST fold's max
drawdown beyond a `drawdown_band=0.30` is charged `g(d)-g(band)`, capped finite at d=0.99 so a liquidating
fold (d=1) is catastrophic (~98) but doesn't inf-break GA ordering. Re-running the SAME search: winner
leverage **4.6x → 2.5x**, gen-0 mean fitness **-1.08 → -47.7** (ruin now priced hard), holdout **-99% →
-39.7%**. So the penalty works — leverage was NOT capped, the GA chose less of it because tail risk now
costs. **But still NO-GO:** the winner kept a 74%-drawdown fold because its +429% median raw leveraged
return outweighs the -2.48 penalty. Cranking the penalty would be the hand-picked-exponent mistake. The
real gap is that the bot has **no brake** to keep upside while cutting the drawdown → that's chunk-L Part A
(intrabar stop-loss gene). B prices the risk; A gives the bot the tool. A risk-adjusted (return/drawdown)
fold metric remains an option if A alone doesn't close it. See [[build-roadmap]] chunk L.
