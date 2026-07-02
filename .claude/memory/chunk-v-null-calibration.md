---
name: chunk-v-null-calibration
description: "chunk V1 random-genome null — bootstrapped best-of-M null makes the certificate's C4 operational; also the standing GA-vs-random audit; V2/V3 pending"
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

**Still pending:** V2 exposure-matched random-entry null (per-candidate; needs per-pair
holding-duration + direction-mix mechanics — kills "beta dressed as alpha": long the bull tail /
flat through the bleed). V3 surrogate-data null (the definitive "is 51% mined": stationary
block-bootstrap each leg's log returns JOINTLY across legs so cross-pair correlation survives while
temporal signal dies, rebuild ratios, re-run the FULL search on ≥20 surrogate universes). Both slot
into the same `nullcheck --mode` CLI + JSON seam V1 established. Standing discipline: never tune
anything to pass the null — it is the exam, not the training set ([[search-overfits-not-strategy]]).
