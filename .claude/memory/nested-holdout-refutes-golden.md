---
name: nested-holdout-refutes-golden
description: "A strict temporal nested holdout REFUTED the 'golden' BNB/ETH edge: move the holdout regime earlier and 0 golden appear, the RSI(2) genome never recurs, and dev-GO genomes go 0/2 out-of-sample (lose to B&H). Confirms overfitting/regime-specificity. The gate is defensive but 'passed gate' != 'persistent edge'."
metadata: 
  node_type: memory
  type: project
  originSessionId: 6228a1b7-55e8-4106-a7b7-2c7e61920b0e
---

2026-06-28, the decisive follow-up to [[first-golden-structural-edge]] (prompted by a skeptical
second-LLM review). **Strict nested holdout:** reserved the most recent 120 daily bars (late Feb–Jun
2026, cutoff 2026-02-26) as a TRULY untouched future set, re-ran the ENTIRE selection process (GA
search → graduation gate → cross-pair tag) on dev-only data (≤ cutoff, 10 seeds, same grind config),
then ran each seed's finalized winner FRESH on the future tail (return, trades, vs B&H, fragility).

**Result — the golden edge did NOT survive:**
- **0 golden on dev-only** (vs 3 in the full-data grind). The BNB/ETH RSI(2) regime-adaptive genome
  NEVER reappeared once the holdout window moved earlier. So the "convergent attractor on 6/30 seeds"
  was an artifact of the holdout happening to be the Feb–Jun BULL TAIL — change the regime the gate
  scores on and the convergence vanishes. This is the cleanest single piece of evidence it was a
  data-mined artifact (exactly the RSI(2)-is-a-data-miner's-delight critique).
- **dev-GO genomes generalized 0/2:** the only two that passed all gates on dev-only (both
  `ema_crossover BTC/SOL adaptive`, +11.6% dev holdout) returned **−0.9% on the untouched future
  while B&H made +14.2%**, fragility 2%. Passing the gate on one window bought NO edge on the next.
- The future "winners" (seed 2 +74%, seed 9 +18%) were dev-NO-GO (the gate REJECTED them), 3–7
  trades = small-sample luck. The gate correctly distrusted them.

**What survives (fair):** the gate is NOT a rubber stamp — only 2/10 dev-GO, and it distrusted the
lucky high-variance combos; chunk-P's bigger surface produced NO false golden. The DEFENSIVE judge
works. What fails is the inference "passed the gate → persistent edge." Test caveat: only 120 future
bars and dev-holdout (chop/decline) vs future (recovery) are different regimes, so 0/2 dev-GO is a
small sample — but the golden-disappears finding doesn't depend on sample size.

**Implication for the roadmap:** durable alpha remains UNPROVEN and the cross-pair GOLDEN tag is NOT
sufficient on its own (needs a truly-decorrelated universe + temporal validation, not just 5
correlated peers on one regime). Before trusting any tag: more scraped bases (independent assets),
walk-forward parameter-stability, and live paper-trading. Do NOT build the allocator (chunk R) on
the current tags. Full briefing: docs/evolutionary-strategy-findings-2026-06.md. See
[[first-golden-structural-edge]] (now REFUTED), [[chunk-o-cross-pair-robustness]],
[[search-overfits-not-strategy]], [[regime-adaptive-multiseed-sweep]].
