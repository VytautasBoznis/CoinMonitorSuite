---
name: plan-b-p3-results
description: "Plan-B P3 cost-side probes (B9 maker limit-fill, B10 1h maker hurdle): B10 RUN 2026-07-06 = FAIL (1/5 majors); B9 infra built but DEFERRED unrun (lower priority than W3 3c)"
metadata: 
  node_type: memory
  type: project
  originSessionId: b74a3a98-2baf-46d6-ab1c-f5df1fde6b6e
---

Plan-B tier P3 (the cost side — "did the FEE hurdle, not signal absence, kill the families?"),
status 2026-07-06. Both probes are informational only — a maker "edge" here funds infra work
(Z3 honest maker execution model), never a certificate (queue position + adverse selection are
un-modelled; see [[plan-b-fallback-probes]] §P3 caveat).

**B10 (1h maker hurdle) — RUN → FAIL.** `probes/b10_maker_hurdle_1h.py`: median |close-to-close|
per 1h bar vs 2× maker round-trip (2×0.001) on the 5 majors (Binance USDT). Cleared the hurdle
on only 1/5 (SOL 2.60×; BTC 1.19×, ETH/BNB 1.61×, XRP 1.82×) — need ≥3. Even the *maker*
round-trip dominates the median 1h bar move on 4/5 majors. Consistent with fee-domination.

**B9 (fee-hurdle re-run under maker limit-fill) — INFRA BUILT, RUNNER DEFERRED.** The seam is in
place and committed with B10: `MakerLimitExecution` (backtest/execution.py — rests a limit at the
prior close, fills only if the bar trades through `low<=prev_close<=high`, else skips the trade),
`prev_close` threaded through `BarStepper`, and `execution=` threaded through `pool_trades`
(search/evidence.py). No runner script yet. When resumed:
- Run **GA-free** on the 7 persisted GO genomes in `runs/go_winners_usdt*.json` (1d:1, 1d-heavy:2,
  4h:4). B9's frozen "top-10 by t_exp" clause needs the banned GA to rank — [[ga-parked]] WINS, so
  use the persisted GO winners and report it as informational, not the literal top-10.
- Maker-side fee = **2 bps (0.0002, Bybit VIP0 maker)** per user 2026-07-06; taker baseline stays
  the config 10 bps. NOTE config.py has `maker_fee == taker_fee == 0.001` (placeholder) — the
  runner must pass 0.0002 explicitly or the fee side of the comparison collapses.
- Per candidate: pool OOS trades under (taker, Ideal) vs (2bps maker, MakerLimitExecution) with
  identical eval_pairs; report expectancy delta. Plan funds Z3 if ≥5/10 flip expectancy-positive.

Deferred because W3 carry step 3c (certify → first winner) outranks P3 per
[[mission-find-edge-ship-ui]]. See [[plan-b-p1-results]] for the P1 tier.
