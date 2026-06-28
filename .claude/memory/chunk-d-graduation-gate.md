---
name: chunk-d-graduation-gate
description: "Chunk D built the graduation gate: graduate() runs the GA winner on a never-searched holdout tail + full fragility, returns a hard go/no-go report with reasons"
metadata: 
  node_type: memory
  type: project
  originSessionId: 79e6c999-dab4-4129-a585-7c03d70ff331
---

Chunk D (2026-06-28) — the graduation gate, per [[build-roadmap]]. The ONLY path from "GA winner"
to "live-eligible".

**Architecture:**
- `search/graduation.py` — `graduate(genome, holdout, taker_fee, *, fragility_runs=200,
  min_fraction_positive=0.9, min_trades=5)` → `GraduationReport(passed, reasons, …)`. Runs the
  genome once on the holdout, then the full Monte-Carlo fragility filter. Three hard gates, each
  appends a `reason` when it fails: holdout return > 0, ≥ `min_trades` holdout trades (kills the
  one-lucky-trade pass), fragility `fraction_positive ≥ min`. `passed = not reasons`. Buy & hold is
  computed + reported but NOT gated (chunk-A edge was risk-adjusted, not raw-return-beats-B&H).
- `data/candles.split_holdout(candles, fraction)` → `(search_head, holdout_tail)`, index-reset,
  fraction in (0,1). The tail is carved off *before* evolution so the winner faces genuinely
  unseen bars.
- `run_search` gained `holdout_fraction` (default 0.0 = unchanged chunk-C). When > 0: the GA
  scores only the search head and the winner is graduated on the tail; the chunk-C fragility
  post-filter is SKIPPED (graduation supersedes it, `fragility`/`passed_fragility` stay None,
  `SearchReport.graduation` is set). `fragility_runs or 200` so `--stress 0 --holdout 0.2` still
  gets a real fragility gate. CLI: `search --holdout FRACTION --graduate-min-trades N`.

**Gotcha found while testing:** RSIMeanReversion with `period=2` on a clean sine LOSES -97%
(micro-dip whipsaw compounds multiplicatively — bounded prices don't bound compounded round-trip
losses); `period=14` on the same series makes +847%. Test genomes need sane periods.

**Status:** 88 tests green; verified `graduate()` rejects garbage (no-trade/loser → NO-GO with
reasons) and passes a robust edge. **The real "graduation on live data" proof is a USER run**
(Docker DB up): `coinmon search --timeframe 1d --holdout 0.2 --stress 80`. Next: chunk E (feature
store, only if GA is compute-bound) or chunk F (live forward feed).
