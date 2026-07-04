---
name: ga-architecture-reality
description: "What the GA actually was vs what the user intended (documented 2026-07-04) — a parameter jitterer over 7 hardcoded families, NOT the composition engine the user envisioned"
metadata: 
  node_type: memory
  type: project
  originSessionId: 30f1a354-ad20-4354-8b53-10fcc9d1bd2f
---

Documented 2026-07-04 after the user discovered the gap. The user's intent for the GA was a
**generalized composition engine**: plug in any implemented primitive (e.g. RSI(UNDER x)) and
have the search compose and iterate conditions freely — i.e. genetic programming over
pluggable building blocks.

What was actually built (src/coinmon/search/ga.py + genome.py): seven hardcoded strategy
classes where the genome is only their numeric knobs. Mutation = Gaussian jitter on 2-3
params per family + re-rolls of pair/direction/leverage/regime-MA/stop. Cross-family
crossover doesn't compose — it inherits one parent wholesale. The sole bounded exception was
`indicator_combo` (N indicator/op/threshold clauses joined by AND/OR), which performed among
the worst.

**Why this matters:** (1) Never describe the parked GA as a strategy-discovery engine — it
was an indicator parameter tuner, the most extreme way of implementing RSI permutations.
(2) If search is ever revived, the user's actual vision is GP-style composition over
primitives — with the LEARNING.md Tier-3 caveat that naive GP overfits catastrophically.
(3) Full GP would NOT have fixed the 0-CERTIFIED wall anyway: all available primitives
transform the same close-price series; composition adds curve-fitting capacity, not
information. The wall was informational — hence the pivot to new data sources in
[[execution-plan-2026-07]], see [[ga-parked]].
