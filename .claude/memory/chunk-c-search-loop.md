---
name: chunk-c-search-loop
description: "Chunk C built the GA: pure seed-deterministic mechanics (search/ga.py) + a runner that scores OOS and gates the winner with fragility as a post-filter"
metadata: 
  node_type: memory
  type: project
  originSessionId: 895e9579-1d92-4ee4-a977-f75f5f5e44a9
---

Chunk C (2026-06-28) — the evolutionary search loop, per [[build-roadmap]].

**Architecture (the deliberate split):**
- `coinmon/search/ga.py` — GA *mechanics only*: `random_genome`, `mutate` (param jitter + pair
  re-roll + low-rate family switch), `crossover` (uniform within family; one parent wholesale
  across families), `tournament_select`, `evolve` (elitism + per-generation fitness history).
  Purely a function of a seeded `random.Random` and a caller-supplied `fitness(genome)->float` —
  **no I/O, fully deterministic, DB-free unit-testable.** Fitness is memoized by genome identity
  (`(family, pair, sorted(params))`) so the expensive backtest isn't repeated for carried elites
  or duplicate children.
- `coinmon/search/runner.py` — wires the GA to real data: `CandleCache` (per-pair, resolves
  synthetic ratios through the extracted `data/candles.load_candles`), scores each genome with the
  OOS multi-fold `evaluate_fitness`, then `run_search` returns a `SearchReport`.

**Key design decision — fragility is a POST-FILTER gate, not in per-genome fitness.** The kill-
filter costs hundreds of backtests per genome and the O(n²) engine is the binding constraint
([[chunk-a-findings]]), so only the cheap OOS folds drive selection; the fragility stress runs on
the **winner only** (`fragility_verdict`: `fraction_positive >= min`, default 0.9). A genome whose
pair has too little data (or any scoring error) is assigned `-inf` so the GA discards it instead
of crashing. CLI: `coinmon search --timeframe 1d --population N --generations N --stress N ...`.

**Status:** 78 tests green; verified in unit tests that the GA climbs a synthetic objective and the
gate thresholds correctly. **The "reject garbage on real data" proof is still a USER run** — needs
Docker DB up (`COINMON_DB_DSN=...:5433`), e.g. `coinmon search --timeframe 1d --stress 80`. Expect
it to be slow on real daily series (the chunk-E feature store is the eventual unblock per
[[feature-store-seam]]). Carries forward to chunk D (graduation gate).

**Extraction note:** `cli._load_candles` moved to `coinmon/data/candles.load_candles` (public);
`tests/test_backtest.py` imports updated to match.
