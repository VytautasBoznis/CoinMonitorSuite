---
name: walk-forward-stability-harness
description: "Chunk S: coinmon stability re-runs the full search on rolling time windows and measures selection agreement (do winners recur?) + forward persistence (does a window's GO survive the next window's unseen bars?). The rolling generalization of the nested-holdout refutation; diagnostic only, no new gate."
metadata: 
  node_type: memory
  type: project
  originSessionId: c389612d-44bd-4f9d-9b5b-6effa8abf561
---

2026-06-28. Built `search/stability.py` + CLI `coinmon stability` to answer the open question the
nested holdout exposed ([[nested-holdout-refutes-golden]]): is a "passed the gate" winner a stable
edge or a holdout-luck artifact? It generalizes that one-shot finding into a ROLLING diagnostic.

**What it does:** `run_stability` slices the data into rolling fractional windows
(`window_bounds(size, step, n)`, default 60% wide advancing 20% → ~3 panes) and re-runs the ENTIRE
selection process on each — the UNCHANGED `run_search` (GA → graduation), so parity is by
construction. Each window is the `[lo, hi)` slice of every series via a windowed read; `run_search`
carves that window's own holdout tail as its graduation span. Then two metrics:
- **Selection agreement** (`_selection_summary`): distinct families/pairs/directions across windows,
  modal recurrence, and `param_drift(a, b)` — normalized `|Δparam|/range` between consecutive
  same-family winners (0 = identical, 1 = opposite corners). A curve-fit hops; an edge recurs.
- **Forward persistence** (`_forward_summary`): each window's frozen winner re-graduated with the
  same `graduate()` on the NEXT window's holdout (genuinely later, unseen bars). Of the winners that
  GO'd on their own window, how many still GO one window forward? This is the metric the nested
  holdout failed 0/2 — "passed the gate on window i" must buy a GO on window i+1 or it means nothing.

**Discipline:** adds NO new gate and changes NO verdict — a diagnostic ON the already-validated
judge, not another filter. Reuses run_search/graduate/split_holdout/CandleCache; no engine changes.

**Status:** code done, 231 tests green, ruff clean. NOT yet run live. CLI: `coinmon stability
--timeframe 1d --holdout 0.2 --window 0.6 --step 0.2 [--windows N] [--stress N] [--cross-pair off]`.
Caveats: fraction-of-series windows are a coarse probe (like the old RSI `walk_forward`), and the
current 5-base DB yields only ~3 windows on one broad regime — a clean read still needs more scraped
bases (the standing [[nested-holdout-refutes-golden]] prerequisite). See [[build-roadmap]] chunk S.
