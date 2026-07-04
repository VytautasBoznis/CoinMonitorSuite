---
name: ga-parked
description: "Decision (2026-07-04) — the GA search is PARKED; strategies are now hand-built from documented research, probe-first; the evidence/certification stack is the durable asset"
metadata: 
  node_type: memory
  type: project
  originSessionId: 30f1a354-ad20-4354-8b53-10fcc9d1bd2f
---

Decision confirmed by the user 2026-07-04: the GA is dead for now. Do not run more GA
sweeps, do not extend the genome registry, do not propose GA fixes. Reason: every sweep
ended 0 CERTIFIED; the searchable space (price-transform indicator permutations, see
[[no-more-rsi-ema-permutations]]) contains no edge, and the new strategy directions have
small hand-designable parameter spaces where a GA adds nothing.

**What survives:** the evidence stack — graduation gate (holdout + min-trades + fragility),
edge certificate (pooled per-trade expectancy, t_exp, Wilson bound), null models, walk-
forward. It is strategy-agnostic and is the mandatory quality gate for everything new.

**How strategies are implemented now:** research-sourced candidate → cheap hypothesis probe
(probes/h*.py pattern, yes/no) → hand-built module (src/coinmon/strategies/ or a new
portfolio layer for cross-sectional work) → backtest engine → certification gate → paper
trading → live per [[autotrading-rollout]]. Candidate order lives in
[[execution-plan-2026-07]]. GA code may stay in the repo as-is (don't delete without being
asked); it just isn't on any path.
