---
name: chunk-a-findings
description: "Chunk A real-data validation: the RSI-MR pulse is pair-specific (XRP ratios survive), and the fitness instability penalty is miscalibrated"
metadata: 
  node_type: memory
  type: project
  originSessionId: f44dbefc-0b14-4b6a-bfb6-8cd37902209e
---

Chunk A (2026-06-28) — first multi-pair real-data run with the DB live, purged walk-forward,
and `evaluate_fitness` together. Backfilled SOL/BNB/XRP USDC daily legs and scored the **fixed**
default RSI genome (14/30/50) out-of-sample across 8 daily series. Full write-up in
docs/lessons-learned.md ("Multi-pair + purged real-data run — chunk A").

**Two findings that change the GA design (the real deliverable):**

1. **Pair/universe selection dominates parameter selection.** The same untuned genome ranges
   from garbage (ETH/USDC −16% mean OOS, SOL/BTC −2.8%) to a strong fold-consistent edge
   (XRP/ETH +34% mean OOS, **positive in all 4 folds**; XRP/BTC +29%, 3/4). ETH/BTC — the pair
   the whole prior thread was built on — is one of the *weaker* ones. → **The genome must encode
   what to trade, not only how.** Feeds [[build-roadmap]] chunk B.

2. **The fitness instability penalty is miscalibrated.** `evaluate_fitness` docks the mean OOS
   return by symmetric `return_std × instability_weight(=1.0)`. XRP/ETH is green in every fold,
   +34% mean, fragility-robust — yet scores **fitness −0.06 (below zero)** purely from the std
   penalty. A symmetric std can't distinguish "always wins, varying amounts" from "swings
   negative," so the GA would **reject a real edge.** → **Replace with a downside / negative-fold
   penalty before the GA loop.** Relates to [[search-overfits-not-strategy]].
   **RESOLVED (chunk B, 2026-06-28):** `evaluate_fitness` now penalizes `downside_dev =
   sqrt(mean(min(0, foldₜ)²))` (zero when every fold ≥ 0) instead of symmetric std. Finding #1 (pair
   gene) is also addressed — `coinmon/search/genome.py` makes `pair` a gene with a `UNIVERSE` pool.

**Supporting results:**
- XRP/ETH fixed genome, full series: +127% return, −37% max DD (vs B&H +176% / −69%), Calmar
  **3.40 > B&H 2.55**, PF 1.94, 25% exposure. Fragility (80 perturbed runs): p5/p50/p95
  +121/+125/+128%, **100% of runs positive** — passes the [[fragility-stress-test]] kill-filter.
  It's a risk-adjusted edge (gives up raw upside, far less drawdown), not a return-maximizer.
- XRP/ETH itself is an *uptrend* (B&H +181%), so this is not the old "just dodge a downtrend"
  artifact that flattered the ETH/BTC result in [[daily-meanreversion-goes-positive]].
- Purged walk-forward (embargo 5) reconfirms the **search** overfits on real data (ETH/BTC
  in-sample +19.4% → OOS −15.6% total_return); fixed params remain the robust path.
- **Perf:** the O(n²) per-bar indicator recompute is now the binding GA constraint — a 300-run
  stress on one daily pair didn't finish in >11 min (dropped to 80). Chunk E feature-store is a
  hard prerequisite for real evolutionary search, per [[feature-store-seam]].

**DB state:** SOL/USDC, XRP/USDC (~1647 daily bars, 2021-12→), BNB/USDC (674 bars, lists
2024-08) are now persisted alongside BTC/ETH in the Timescale docker volume.

**Windows run note:** `summary()` prints a `→`; set `PYTHONIOENCODING=utf-8` or the CLI crashes
with a cp1252 UnicodeEncodeError (Docker/Linux is utf-8, unaffected).
