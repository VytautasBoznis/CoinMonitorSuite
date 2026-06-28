---
name: n6-multiseed-sweep-convergence
description: "N6 sweep — the 15-trade gate collapsed the prior lottery into ONE convergent pair (BTC/USDC ema adaptive), but it's still one crash regime so alpha is unproven"
metadata: 
  node_type: memory
  type: project
  originSessionId: 989aaa13-cade-4308-9308-debc5a8e2328
---

Chunk N6 (2026-06-28). Built `coinmon sweep` (`search/runner.py`: `run_search(cache=…)` for a
shared per-pair cache across seeds, + pure `SweepRow`/`sweep_row`/`summarize_sweep`; CLI
`coinmon sweep --seeds N --holdout F --stress N`). The aggregator's lottery diagnosis = GO count
+ the number of DISTINCT pairs the GOs land on (one pair across seeds = consistent edge; many =
lottery tickets).

**First live run** (10 seeds, 1d, holdout 0.2, stress 80, 15-trade gate, current 5-base / ~15-pair
DB): **2/10 GO (seeds 3, 7), and BOTH are the same genome class** — `ema_crossover BTC/USDC
adaptive`, +15–21% holdout, 16–21 trades, fragility 100%, vs B&H −48%.

**What changed vs the prior sweep** ([[regime-adaptive-multiseed-sweep]], which had 4 GOs HOPPING
pairs by seed = lottery): the N3 15-trade floor NO-GO'd the high-return THIN-trade winners (seed 5
+94% on **3 trades**, seed 4 +34% on 10), and the survivors CONVERGED on one pair. So strictness
turned a scatter of lottery winners into a single consistent candidate — evidence the gate is
doing real work.

**Why alpha is STILL unproven (do not over-read this):** B&H was −48% over the holdout — it is ONE
BTC-crash regime, and both GOs are regime-adaptive shorts riding that drop. "Consistent edge" here
may just be "BTC crashed and the adaptive leg shorted it" — the same one-regime caveat as every
prior NO-GO/GO. Convergence on BTC/USDC is also partly because the tiny universe makes BTC the
dominant liquid leg.

**Next:** the chunk-O cross-pair/cross-regime robustness gate (does the SAME genome hold on
decorrelated pairs / a non-crash regime?), and/or forward-test the BTC/USDC ema-adaptive winner.
N5 (indicator library) was DEFERRED by the user to run this payoff test first. See [[build-roadmap]].
