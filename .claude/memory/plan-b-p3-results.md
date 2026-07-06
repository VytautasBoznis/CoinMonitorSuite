---
name: plan-b-p3-results
description: "Plan-B P3 cost-side probes (B9 maker limit-fill, B10 1h maker hurdle) BOTH RUN 2026-07-06 = FAIL. B10 1/5 majors; B9 1/7 GO winners flip positive under maker (need 5/10) → does NOT fund Z3. P3 tier CLOSED — confirms signal absence, not cost domination"
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

**B9 (fee-hurdle re-run under maker limit-fill) — RUN 2026-07-06 -> does NOT fund Z3 (1/7 flip).**
`probes/b9_maker_fee_hurdle.py` (log `runs/b9_maker_fee_hurdle.log`): GA-free on the 7 persisted GO
genomes, pooling each one's strictly-OOS ledger (same `select_eval_pairs`/`pool_trades` seams as
`certify`, eval_pairs 8, holdout 0.2, seed 0, bybit USDT) under (taker 10bps, Ideal) vs (**2bps
maker**, `MakerLimitExecution`). Only **1/7** flipped positive (BNB/GRT-4h, marginal -0.029%->
+0.132%); the rest stayed money-losers (ETH/SOL -2.35%, BNB/GRT-1d -1.87%, WLD -0.74%). Need 5/10
-> Z3 NOT funded. **KEY GOTCHA:** in 24/7 crypto consecutive bars are CONTIGUOUS (this bar's open
~= prior close), so a limit at the prior close fills on ESSENTIALLY EVERY bar at ~= the open ->
`N_maker == N_taker` for all 7 and every 1x delta is exactly +0.160% = 2x(0.001-0.0002). So on
daily/4h bars `MakerLimitExecution` degenerates to "same fills, lower fee"; the skip-on-gap path
never triggers. B9 here measures the FEE REDUCTION only, not a realistic limit-fill regime. Verdict
stands: halving the fee does not rescue the price-shape families -> signal absence, not cost
domination (same as B10 + the calibrated negative).

**P3 tier CLOSED (both FAIL).** With P1 (all FAIL) + P3 done, the remaining Plan-B hunt is P2
(B5 OI / B6 basis / B7 positioning / B8 listings, collector-gated on Z0) and P4 external
(B11 stablecoin supply / B12 BTC-dominance). Original deferral note (superseded) below:

_Infra as-built:_ `MakerLimitExecution` (backtest/execution.py, rests a limit at the
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
