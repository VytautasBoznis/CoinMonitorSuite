---
name: strategy-lab-model
description: "The post-GA answer to \"how do we test many strategy options\" (2026-07-04) — a strategy lab: one-command evaluation gauntlet + three candidate sources; the evaluator is the product, not the search"
metadata: 
  node_type: memory
  type: project
  originSessionId: 30f1a354-ad20-4354-8b53-10fcc9d1bd2f
---

Agreed model (2026-07-04) for maximizing testable strategy options after the GA's failure
([[ga-parked]], [[ga-architecture-reality]]):

**The evaluator is the product.** The genuinely working asset is the evaluation gauntlet:
walk-forward OOS fitness, holdout graduation gate, fragility Monte-Carlo, null models, edge
certificate. Package it as one command that takes ANY module implementing the Strategy
interface and returns a verdict. A strategy idea should go from description to verdict in
under a day.

**Three candidate sources, in order of hit-rate:**
1. Research-documented effects — the [[execution-plan-2026-07]] five; literature pre-filters
   noise for free.
2. Exhaustive enumeration — per idea, a SMALL param grid run completely with multiple-testing
   deflation per [[portfolio-search-protocol]]; all configs recorded, none hidden.
3. Model-authored strategies — an LLM session turns a paper/user idea into a module + probe;
   composition with economic reasoning attached, replacing GP's random mutation. Every
   candidate must state WHY it should work (whose money it takes) before being run.

**The real option multiplier is data, not math:** each new feature column (OI, taker delta,
liquidations, funding) times every strategy shape grows the space in information; composing
more transforms of close-price grows only curve-fit capacity — the proven dead end.

**Chunk-letter decoder** (user references old lettered plans): B = genome encoding,
C = GA search loop (B+C ARE the parameter-tuner GA), A = pair-as-gene, W1/W3/W4 =
ratio_momentum / funding_carry / donchian families (new families, same tuner frame),
P = bounded indicator_combo, O = gate hardening, V = null-model machinery, H1-H6 = probes.
No chunk ever implemented strategy composition.

**CRITICAL namespace distinction:** chunks B/C (code, above) ≠ **Plans B/C** — those are
`.claude/plans/alpha-hunt-plan-b.md` (pre-registered fallback probe pack B1-B12 on NEW
inputs, frozen 2026-07-03 before the Y sweeps; trigger = calibrated negative, which HAS now
fired) and the plan-c-onchain-ideation repo memory (DEX/on-chain moonshot, ideation only,
user-gated). Plans B/C were never implemented BY DESIGN (pre-registration discipline), not
by neglect. The repo memory at CoinMonitorSuite/.claude/memory/ is authoritative.
