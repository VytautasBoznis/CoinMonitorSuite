---
name: chunk-v-null-calibration
description: "chunk V null calibration (certificate C4) COMPLETE: V1 random-genome + V2 exposure-matched random-entry + V3 surrogate-data nulls all DONE (search/nullmodel.py, data/surrogate.py, coinmon nullcheck --mode)"
metadata: 
  node_type: memory
  type: project
  originSessionId: ed661ccc-75e6-45aa-8a0f-34dc6b68634b
---

Chunk V builds the Edge Certificate's C4 ("beats the null") — the piece that turns "beats zero"
into "beats chance" and prices the multiple-comparisons burden of a big search
([[alpha-definition-edge-certificate]], [[edge-certificate-implemented]]). Split V1/V2/V3, cheapest
first, like N was.

**V1 DONE (2026-07-02) — the random-genome null.** `src/coinmon/search/nullmodel.py`:
- `NullResult` (mode, candidate_score, null_scores, percentile, quantile, beaten) + `to_dict`/
  `from_dict` for JSON.
- Pure `null_from_scores(candidate_score, sample_scores)` = **bootstrapped MAXIMUM** null: each
  resample draws M scores with replacement and keeps the max, approximating the sampling
  distribution of the best-of-M random tries. **Why the max, not a random draw:** the real search
  SELECTS its winner from thousands of genomes, so the fair null for a SELECTED statistic is the
  distribution of the max (White's Reality Check correction). The 95th-pctile of the bootstrapped
  max ≈ the sample max, so the bar is effectively "beat the single best random genome" — correctly
  harsh. No finite sample → threshold +inf, never beaten (a genome whose peer set all failed can't
  sneak a C4 pass).
- `random_genome_null(...)` orchestration: sample M random genomes (`ga.random_genome`), score each
  by the SAME pooled-ledger `t_exp` (chunk U's `pool_trades` + `build_evidence`) over the SAME
  `eval_pairs` and window/holdout grid as the candidate — identical protocol = fair comparison.
  `score_genome` is injectable so the whole thing is unit-testable with NO DB.

**Doubles as the plan §4 audit:** "is the GA even beating random search?" At ≤10 dims, if evolved
winners don't clear best-of-M-random under equal budget, run random search and save the compute.

**CLI:** `coinmon nullcheck` pools the candidate + N random genomes and writes a genome-stamped JSON
(`{genome, timeframe, null}`). `certify --null FILE` loads it, **refuses a mismatched
genome/timeframe** (can't apply the wrong null), and feeds `beaten` into C4 → **C4 is now
operational** (was permanently PENDING since chunk U). Shared `_genome_from_args`/`_genome_spec`
keep certify+nullcheck genomes in lockstep.

274 tests green (+10, all DB-free), ruff clean. Real pooling path smoke-verified end-to-end on
synthetic candles (not just the injected scorer).

**V2 DONE (2026-07-02) — the exposure-matched random-entry null** (the direct antidote to "beta
dressed as alpha": profitable only by being long a bull tail / short a bleed — the failure mode
behind every prior GO). `nullmodel.random_entry_null(candidate_expectancy, segments,
build_portfolio, taker_fee, resamples=1000)`: for each of R draws, replay every one of the
candidate's OWN closed trades keeping its **segment + direction + holding-duration** but drawing a
fresh RANDOM entry bar, pool the synthetic returns, take that pool's expectancy; the candidate's
expectancy must clear the 95th pct of that distribution.
- `null_from_distribution` = the DIRECT empirical percentile (NOT V1's best-of-M max): V2 does no
  selection, so the fair null is the matched distribution's own upper tail. Statistic compared is
  **expectancy** (per plan §V.2), not `t_exp`.
- `_synthetic_return` computes each matched trade through the genome's OWN `decode_portfolio` —
  reuses the real Spot/Perp economics (leverage, both fee legs, isolated-margin liquidation latched
  on a held bar's close), so NO re-derived return formula can drift from the engine. Fresh portfolio
  per trade → the scale-free per-collateral return the ledger records. Mirrors `BarStepper`: fill at
  entry bar's open, mark closes[entry .. entry+dur-1], close at exit bar's open.
- New `evidence.EvalSegment` (opens, closes, per-trade (direction, duration_bars)) + `pool_segments`.
  Refactor: `pool_trades` and `pool_segments` now share one private `_iter_segments` grid loop, so
  the leakage-critical OOS-only slicing lives in ONE place and `pool_trades` output is byte-identical.
- CLI `nullcheck --mode random|matched` (+ `--resamples`, default 1000); same genome-stamped JSON
  `certify --null` consumes (C4 is mode-agnostic — just reads `beaten`).
299 tests green (+10, all DB-free), ruff clean.

**V3 DONE (2026-07-02) — the surrogate-data null** (the definitive "is 51% real or MINED?", the
White's-Reality-Check analogue). New `src/coinmon/data/surrogate.py`:
- `block_bootstrap_indices(n, block_len, rng)` = moving circular-block index sequence (mirrors
  `evidence.block_bootstrap_ci`'s block logic): within-block order kept (short-range structure ≤
  block_len survives), block ORDER randomized (longer-range temporal signal dies).
- `surrogate_legs(legs, block_len=20, seed=0)` = **JOINT** block bootstrap of the DIRECT legs'
  returns. Aligns all legs on their shared `open_time`, draws ONE index sequence, applies it to
  EVERY leg identically → same historical instants copied across all coins at once, so **cross-leg
  correlation survives** while each leg's temporal predictability is destroyed. Each surrogate bar
  keeps its source bar's close-to-close return + intrabar OHLC geometry (open/high/low as ratios to
  its own close) so fills/stops stay realistic; close rebuilt by compounding from the true first
  close; ORIGINAL calendar open_time kept (window/regime geometry unchanged). Ratios rebuild
  downstream via `load_candles` → **zero search/engine edits**. Passthrough if <2 shared bars
  (CAVEAT: legs with disjoint date ranges → tiny/empty common span → degenerate passthrough; a
  live-run data-quality watch, not a code bug).
- `nullmodel.surrogate_null(candidate_score, score_surrogate, n_surrogates=20, seed)` reducer:
  `score_surrogate(seed)->float` runs the FULL search on ONE surrogate universe and returns its
  winner's pooled `t_exp`; judges the candidate against the **DIRECT** 95th pct of those
  best-on-noise scores (`null_from_distribution`, like V2 — each surrogate is already a
  search-SELECTED max, so no extra best-of-M bootstrap). `score_surrogate` injected → DB-free
  unit-testable.
- CLI `nullcheck --mode surrogate` (+ `--surrogates` 20, `--block` 20, `--pop` 100, `--gens` 30):
  loads direct legs once, per surrogate block-bootstraps them, runs `run_search`
  (holdout_fraction=0, fragility OFF — only need the GA winner; pool_trades carves its own OOS
  windows, so no 200-run graduation paid per surrogate), pools + scores the winner. Same
  genome-stamped JSON `certify --null` consumes (C4 mode-agnostic).
317 tests green (+18: test_surrogate.py 14 + surrogate_null 4), ruff clean. **End-to-end verified
on synthetic legs** (no DB): the search mined a **+2.31 t_exp out of pure noise** across 4
surrogates → exactly the point of V3 (a real candidate must clear the score a search extracts from
signal-destroyed data). **Not yet run live.** Chunk V is now COMPLETE. Standing discipline: never
tune anything to pass the null — it is the exam, not the training set ([[search-overfits-not-strategy]]).
