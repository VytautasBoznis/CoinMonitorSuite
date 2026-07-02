---
name: chunk-v-null-calibration
description: "chunk V null calibration (certificate C4): V1 random-genome best-of-M null + V2 exposure-matched random-entry null both DONE; V3 surrogate-data pending"
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

**Still pending:** V3 surrogate-data null (the definitive "is 51% mined": stationary block-bootstrap
each leg's log returns JOINTLY across legs so cross-pair correlation survives while temporal signal
dies, rebuild ratios, re-run the FULL search on ≥20 surrogate universes). Slots into the same
`nullcheck --mode` CLI + JSON seam. Standing discipline: never tune anything to pass the null — it is
the exam, not the training set ([[search-overfits-not-strategy]]).
