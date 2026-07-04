---
name: portfolio-search-protocol
description: "How winner-finding works post-GA (2026-07-04) — no pair parameter, exhaustive small-grid enumeration with multiple-testing discipline, portfolio-level certification"
metadata: 
  node_type: memory
  type: project
  originSessionId: 30f1a354-ad20-4354-8b53-10fcc9d1bd2f
---

Protocol replacing the GA search, defined 2026-07-04 for [[cross-sectional-momentum-portfolio]]
(generalizes to other portfolio/structural strategies in [[execution-plan-2026-07]]).

**No pair parameter.** The tradeable unit is a portfolio over the universe of USDT-quoted
coins with liquidity/history floors — NOT the 861 synthetic ratio pairs (those were an
artifact of the per-pair GA search). One strategy, one equity curve. "Pair wins" is not a
concept anymore; certification is of the single portfolio.

**Search = exhaustive enumeration, not optimization.** Design grid: lookback {7,14,28,90d},
skip-recent-days {0,1}, slice width {top 10%, 20%}, long-only vs long-short, weighting
{equal, vol-scaled}, rebalance {weekly, biweekly}, liquidity floor. ~100-200 configs. Run
ALL, record ALL — the total tried feeds multiple-testing correction (deflated Sharpe /
reality-check style). Winner verified ONCE on an untouched holdout tail (~last 30% of
history). No selection pressure may hide tries — that is the Tier-0 anti-snooping rule.

**Certification adaptation:** N = pooled per-position outcomes (top-decile weekly over
~300 coins ≈ 30 outcomes/week — N≥300 reached in ~10 holdout weeks, unlike per-pair
strategies which died at 0-3 trades). Benchmark = equal-weight universe portfolio (crypto
beta), replacing per-pair buy-and-hold. Fragility = random 50% universe subsets +
rebalance-day jitter + fee bumps, ≥90% of runs must beat benchmark. Null model =
random-ranking portfolios with identical turnover; strategy must beat p95 of nulls.
Generalization (old golden/specialist tier) = factor must hold on disjoint universe halves.

**Fees are the main killer:** weekly full-turnover at 0.1% taker both ways ≈ 10%+/yr drag;
model fees before anything else, prefer configs with natural turnover limits.
