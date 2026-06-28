---
name: chunk-o-cross-pair-robustness
description: "Chunk O cross-pair robustness — a TAGGER (golden/specialist), not a kill gate; re-graduates a GO genome on K-of-N decorrelated peers to tell structural edge from pair-specific curve-fit"
metadata: 
  node_type: memory
  type: project
  originSessionId: 4c217b22-d983-4b37-9d64-ce180afcc114
---

Chunk O (2026-06-28). `search/robustness.py` is the trust-DISCRIMINATOR that sits after the
chunk-D graduation gate. The gate proves a genome held up on its OWN pair's unseen holdout, but
chunk A showed edges are often pair-specific and the N6 sweep's GOs hopped pairs by seed like
lottery tickets — so a single-pair GO can't tell a structural edge from a holdout-luck curve-fit.

**What it does:** after a winner GRADUATES GO, re-run the SAME genome with its pair gene overridden
(`dataclasses.replace`) on K-of-N randomly-picked DECORRELATED peer pairs, then TAG it:
- `golden` — held up on ≥ `cross_pair_min` (default K=3) of N (default 5) → structural, core trust.
- `specialist` — own pair only → pair-tailored, conditional trust (rescues chunk-A's XRP ratios).

**Hard design choices (all deliberate):**
- It is a **classifier, NOT a kill filter** — only runs on a GO and NEVER flips the go/no-go. A
  trust label, so real pair-specific alpha is kept (tagged) instead of discarded.
- Metric = **sign/profitability persistence**, reusing `graduate()`'s exact gate per peer (positive
  return + fragility-positive + min-trades). NOT a magnitude/±10% band — returns don't match across
  pairs of different volatility, so a band would reject genuinely robust edges (the metric-correction
  note was right).
- **Decorrelation matters:** `pick_decorrelated_pairs` seeds an RNG, shuffles, greedily accepts a
  peer only if |holdout-return correlation| with every already-chosen peer ≤ `max_corr` (0.7); tops
  up if short so a small/correlated universe still runs. Three majors crashing together = ONE test,
  not three. Flat/no-overlap series → corr treated as 0 (decorrelated).

**Wiring:** `run_search(cross_pair_n=, cross_pair_min=, cross_pair_max_corr=)` (0 = chunk-N behavior
unchanged) → `SearchReport.robustness: RobustnessReport | None` + summary; CLI `search --cross-pair N
--cross-pair-min K` (needs `--holdout`). 169 tests green (+9), ruff clean.

**NOT yet run live** — the golden-vs-specialist proof is a user run (`search --timeframe 1d --holdout
0.2 --stress 80 --cross-pair 5`). **Caveat:** the current ~15-pair DB has only ~14 non-own candidates
and the majors are highly correlated, so a clean 5-decorrelated set really needs more scraped bases
(this is exactly the throughput that N4 enables). Obvious next add: sweep-level tier aggregation
(count golden vs specialist across seeds). This is the "meaner judge" that had to exist before P/Q
([[build-roadmap]]); the tier is what P/Q and the future allocator (chunk R) will trust.
See [[chunk-a-findings]], [[regime-adaptive-multiseed-sweep]], [[n6-multiseed-sweep-convergence]].
