---
name: chunk-y-ensemble-certification
description: "chunk Y ensemble code — certify a top-k decorrelated PORTFOLIO of winners as its own Edge-Certificate unit (small edges reach N≥300 only aggregated); payoff sweep RUN still the user's"
metadata: 
  node_type: memory
  type: project
  originSessionId: c939165b-2ba7-415d-b958-b03e0f23a9be
---

Chunk Y step 2 (the ensemble) code landed 2026-07-03 — `search/ensemble.py` + CLI
`coinmon certify-ensemble --genomes FILE --k N`. Pure composition of existing seams, so it
inherits the whole [[edge-certificate-implemented]] pipeline unchanged.

**What it does:** `certify_ensemble(candidates, …)` treats a PORTFOLIO of frozen winners as the
deployment unit ([[alpha-definition-edge-certificate]] §Y.2). Per candidate: `select_eval_pairs`
→ `pool_trades` gives its own strictly-OOS ledger; rank by individual `t_exp`;
`pick_decorrelated_members` greedily keeps up to `k` whose `daily_pnl` streams have |corr| ≤
max_corr (reuses chunk O `_abs_corr`); UNION the kept ledgers; `build_evidence`+`certify` the pool.

**Two decisions worth remembering (judgment calls, not in the plan verbatim):**
- Decorrelation basis = each member's **daily realized P&L** (per-trade `net_return_pct` summed
  into the trade's `exit_time` UTC day), NOT the equity level (trivially autocorrelated). open_time
  is epoch **ms** → day = `t // 86_400_000`.
- "Equal-weight the pooled ledger" = **union of members' trades**, every trade one per-trade sample
  regardless of member — identical semantics to how chunk U already pools across pairs (no reweight
  by trade count). The point: two members individually N<300 clear C1 only aggregated.

**Deliberately PENDING:** C4 (null) + C6 (fragility) for the ensemble — an ensemble-level null is
out of scope, so it can't reach CERTIFIED unaided (same honest gap as single-genome `certify`
without `--null`).

**Still the user's payoff RUN:** the heavy §Y.1 sweep, certifying each winner + the ensemble, and
the §Y.3 two-outcome read (CERTIFIED → chunk G / unpark Q; calibrated negative → pivot) are a live
run under the USDT-train/USDC-certify split ([[train-usdt-certify-usdc]]). Loose end: `sweep
--certify` ranking (roadmap U.3) is unbuilt — user hand-picks GO genomes into the genomes JSON for
now. See [[build-roadmap]] chunk Y.
