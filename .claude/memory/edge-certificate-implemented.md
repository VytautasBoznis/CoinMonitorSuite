---
name: edge-certificate-implemented
description: "chunk U — per-trade OOS ledger + search/evidence.py Edge Certificate (Wilson/bootstrap/regime), coinmon certify; C4 null + C6 fragility deferred"
metadata: 
  node_type: memory
  type: project
  originSessionId: a7996c43-fde2-4753-970e-c25b77749929
---

Chunk U landed the **Edge Certificate** — the project-level definition of alpha
([[alpha-definition-edge-certificate]]) — replacing the one-holdout-equity graduation verdict with
a **pooled per-trade** judgement (the only way past the sample-starvation noise floor that produced
every refuted GO, [[nested-holdout-refutes-golden]]).

**Trade ledger (additive, metrics byte-identical):** `BacktestResult.trades: list[TradeRecord]`
where `TradeRecord = (entry_time, exit_time, direction, net_return_pct)`. Portfolios record a
`ClosedTrade(direction, net_return_pct)` in lockstep with the existing PnL `trades: list[float]`
(so `metrics.summarize` is unchanged); the engine's `BarStepper._harvest` pairs each new
`ClosedTrade` with the bar times it knows — robust to flips (harvest under the OLD entry time before
the new leg overwrites it), stops, and liquidation. Invariant: `len(result.trades) ==
metrics["trades"]`.

**`search/evidence.py`:** `wilson_lower_bound` (C2 one-sided 95%), `block_bootstrap_ci` (C3 —
moving *circular* blocks ~√N over the TIME-ORDERED pooled returns, because pooled trades are
cross-pair correlated → gives expectancy CI + `t_exp = expectancy/boot_std`), `_regime_expectancies`
(C5 — disjoint equal-*time* buckets by entry_time), `build_evidence` (pure → unit-testable),
`certify` (six criteria), `pool_trades` + `select_eval_pairs` (reuse chunk O
`pick_decorrelated_pairs` + chunk S `window_bounds` + chunk D `split_holdout`).

**Verdict logic:** CERTIFIED (all six PASS) / REFUTED (N≥300 AND any of C2–C6 fail) / UNPROVEN (the
honest "keep collecting" — N<300, or a PENDING criterion with the rest clean). **C4 (null) and C6
(fragility) are optional args — `None` = PENDING, which BLOCKS a CERTIFIED verdict but never forces
REFUTED.** So `coinmon certify` alone can never say CERTIFIED; it needs chunk V's null + a fragility
number (wired at the sweep, chunk Y). This is deliberate: certify is the exam, never tuned to pass.

CLI: `coinmon certify --family --pair --params '{…}' [--direction --leverage --trend-period --stop
--eval-pairs --holdout --window --step --regimes]`. Genome is given on the CLI (no winner-file
persistence yet — same gap chunk F noted).

**Not yet:** the [[train-usdt-certify-usdc]] split is honored only by CONFIG (run `search` with a
USDT `quote_currency`, `certify` with USDC) — there is no single train-on-USDT / certify-on-USDC
command; that fuller plumbing is chunk Y. **Acceptance is a LIVE user run:** certify the refuted
BNB/ETH RSI(2) golden and confirm REFUTED/UNPROVEN. Next: V (nulls) or W1 (ratio_momentum,
T0-promoted). See [[build-roadmap]].
