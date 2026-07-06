---
name: ga-parked
description: "HARD BAN (2026-07-04, re-affirmed & escalated 2026-07-06) — the GA/sweep architecture is BANNED for all further testing, not merely parked; NEVER run `coinmon sweep`/`search`, re-run old sweeps, or touch the genome registry to source candidates. Evidence/certification stack is the durable asset"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 30f1a354-ad20-4354-8b53-10fcc9d1bd2f
---

**BANNED — not "parked."** User directive, escalated (with emphasis) 2026-07-06 after a
session nearly re-ran Y's GA sweeps to source B9's genomes: **DO NOT USE THE GA ARCHITECTURE
FOR FURTHER TESTING.** This means, hard rules, no exceptions without an explicit new user
instruction:
- NEVER run `coinmon sweep` or `coinmon search` (these ARE the GA), nor re-run any old sweep,
  even to "just recover genomes" or "re-price existing candidates."
- NEVER extend/edit the genome registry or propose GA fixes.
- A frozen pre-registered probe rule does NOT override this. B9's "re-run Y's top-10 by t_exp"
  clause (plan-b §P3) predates the ban; the ban WINS. If a probe's letter needs the GA, run it
  GA-free on already-persisted artifacts (e.g. Y's saved `runs/go_winners_usdt*.json` GO
  genomes) or don't run it — surface the conflict, never quietly fire up the GA.

**Why:** every GA sweep ended 0 CERTIFIED; the searchable space (price-transform indicator
permutations, [[no-more-rsi-ema-permutations]]) has no edge, and the GA was only ever a
parameter-jitterer over hardcoded families ([[ga-architecture-reality]]), not a real
composition engine — so re-running it can only reproduce the same calibrated negative at
compute cost. Reaching for it again is the exact failure mode the user is guarding against.

**What survives:** the evidence stack — graduation gate (holdout + min-trades + fragility),
edge certificate (pooled per-trade expectancy, t_exp, Wilson bound), null models, walk-
forward. Strategy-agnostic, the mandatory quality gate for everything new.

**How strategies are implemented now:** research-sourced candidate → cheap hypothesis probe
(probes/*.py pattern, yes/no) → hand-built module (src/coinmon/strategies/ or a portfolio
layer) → backtest engine → certification gate → paper → live per [[autotrading-rollout]].
Candidate order lives in [[execution-plan-2026-07]]. GA code may stay in the repo as-is (don't
delete without being asked); it just isn't on any path. See [[honest-status-reporting]].
