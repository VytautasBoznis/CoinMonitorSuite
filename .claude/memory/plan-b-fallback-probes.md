---
name: plan-b-fallback-probes
description: "Plan B pre-registered 2026-07-03 (BEFORE Y ran): if Y ends in the calibrated negative, probe NEW INPUTS (OI/positioning/basis/events/maker-costs), never search the old space harder; collectors (Z0) start immediately because exchange lookback is limited"
metadata:
  node_type: memory
  type: project
---

`.claude/plans/alpha-hunt-plan-b.md`, frozen 2026-07-03 — before chunk Y produced any result,
so the fallback can't be shaped by the outcome (same pre-registration discipline as T0).

**Trigger:** ONLY the calibrated negative (Y: zero CERTIFIED and nulls explain the best score).
Not an invitation to probe early — running Plan-B signal probes before Y would leak into Plan-A
family tuning. **Exception: chunk Z0 collectors start NOW** (open interest, long/short ratio,
perp candles for basis, listing-date snapshots): Bybit serves limited lookback for non-candle
series, so uncollected history is lost forever; collection has no statistical cost.

**Shape:** 12 frozen probes (B1–B12) in 4 tiers — P1 free on post-T data (post-shock reversal,
volume shock, cross-venue lead-lag, rebalancing premium), P2 on new collectors (OI, basis,
positioning, listing drift), P3 cost-side (maker-fee re-run of Y's top-10, 1h maker hurdle;
diagnostic only — fill models lie optimistically), P4 external (stablecoin supply, dominance
rotation). PASS funds a Z-chunk (Z1 event-strategy seam, Z2 flow features, Z3 honest maker
execution, Z4 macro overlay); every funded family still faces the full certificate + all three
nulls. Z5 = the pivot decision if everything fails (calibrated-negative writeup, Phase-2 scanner
product, carry as yield, new input class only as a conscious user decision).

**Why:** the calibrated negative would already price the whole price-shape space; the only
follow-up worth its multiple-comparisons bill is one that changes the INPUTS (data class, event
shape, or cost model). Forbidden responses restated in the plan §0: more GA budget, relaxed
thresholds, more seeds, early probe-peeking.

**How to apply:** if Y certifies something, Plan B stays parked (collectors keep running). If Y
is negative, run P1+P3 first, fund Z-chunks only from PASSes, never adjust a frozen rule after
seeing its result. See [[alpha-definition-edge-certificate]], [[build-roadmap]],
[[no-strategy-preference]], [[train-usdt-certify-usdc]].
