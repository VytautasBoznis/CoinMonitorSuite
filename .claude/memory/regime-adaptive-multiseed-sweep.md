---
name: regime-adaptive-multiseed-sweep
description: "10-seed robustness sweep of the regime-adaptive search (chunk M): the eval gate is VALIDATED as a trustworthy judge (discriminates on direction/evidence/robustness), but durable alpha is NOT proven — every GO is a thin-trade leveraged crash-short on a single (down) regime, with luck-level return variance. Raise the min-trades floor; test across regimes; forward-test before believing it."
metadata:
  node_type: memory
  type: project
  originSessionId: continue-2026-06-28
---

**10-seed sweep, 2026-06-28** — `search --timeframe 1d --holdout 0.2 --stress 80 --population 40
--generations 16`, seeds 0–9, full 12-pair UNIVERSE, against the Docker DB. Follow-up to the single
seed-0 GO in [[direction-gene-overfits-regime]]. **Result: 4 GO / 6 NO-GO.** (1h was ruled out — the
O(n²) engine makes its 9420 bars ~32× slower/backtest than 1d's ~1659, and only 3 pairs are computable
on 1h.)

**Per-seed (winner | holdout | trades | verdict):**
- 0: ema BTC/USDC **4.2× adaptive** | +248% (B&H −48%) | 7 | **GO**
- 1: ema BTC/USDC long/flat | −8.95% | 3 | NO-GO (long into crash + thin)
- 2: atr ETH/USDC **1.7× adaptive** | +11.85% (B&H −57%) | 6 | **GO**
- 3: ema BTC/USDC **1.2× adaptive** | +64.96% | 5 | **GO**
- 4: ema BTC/USDC **2.6× adaptive** | **+159%** | 4 | **NO-GO** (profitable but <5 trades)
- 5: ema BTC/USDC long/flat | −8.95% | 3 | NO-GO
- 6: ema XRP/ETH long/flat | −8.80% | 7 | NO-GO (negative)
- 7: ema BTC/USDC **4.7× adaptive** | +3.13% | 5 | **GO**
- 8: atr ETH/USDC long/flat | −28.86% | 8 | NO-GO
- 9: ema ETH/USDC **2.3× adaptive** | **−33.51%** | **28** | **NO-GO** (whipsawed)

**What IS proven — the gate is a trustworthy judge (the hard part).** It discriminated correctly on
four independent axes: (1) DIRECTION — every long/flat bet into the crash was rejected (1,5,6,8), every
GO was regime-adaptive (correct direction); (2) EVIDENCE — seed 4 made **+159% and was NO-GO'd for only
4 trades**; (3) ROBUSTNESS — seed 9 was regime-adaptive ("right" direction) but a fast/whippy genome
(EMA 2/15) got chopped up in the choppy crash → 28 trades, −33.51%, fragility 0% → correctly killed;
(4) only clean, fragility-positive, correct-direction genomes passed. **Seed 9 is the key result: it
proves "regime-adaptive = free crash profits" is FALSE (the [[chunk-l-live-validation]] whipsaw caveat,
caught live) and that the gate is not fooled by the label.** The chunk-M direction fix is validated
across seeds (it removed the wrong-direction NO-GOs the fixed `short` gene caused).

**What is NOT proven — durable alpha.** All 4 GOs are thin-trade (5–7) leveraged (1.2–4.7×) crash-shorts
on a SINGLE down-regime (every recent holdout is a −19%..−57% crash — the whole recent market fell,
[[chunk-l-live-validation]]). Red flags that the "edge" is low-sample luck, not signal: (a) profits
cluster at LOW trade counts while the only high-N genome (seed 9, 28 trades) LOST; (b) noise-level return
variance — seeds 0 and 7 ran near-identical leverage (4.2× vs 4.7×) on the same crash and made +248% vs
+3.13%; (c) single regime means we cannot distinguish "found edge" from "shorted a falling knife and the
2% stop happened to catch it." Same lesson as [[search-overfits-not-strategy]], now visible as thin-N
leveraged crash-shorts surviving one holdout.

**Actionable next moves (recommended order):**
1. **Raise `--graduate-min-trades` from 5 to ~15–20.** At 5 the gate passes low-evidence genomes; a
   higher floor would have NO-GO'd most of these GOs and pushed the search toward real sample size.
   (Cheapest, highest-signal change — fastest way to separate luck from edge.)
2. **Test across regimes**, not just the all-crash recent tail (older slices, BNB pairs, mixed up/down
   holdouts) — otherwise every result is "shorted a down market."
3. **Forward/paper test (chunk G)** before believing any GO — a graduation GO is "survived an honest
   historical split," explicitly NOT a promise of live profit.

Bottom line for the user (limited quant background, relies on the rig — [[user-quant-background]]): the
JUDGE works and is safe to keep searching with; the SEARCH has not yet been shown to find money-making
alpha. Don't conflate "first GOs on real data" with "GP found a strategy." See [[build-roadmap]] chunk M.
