---
name: f8-cascade-ladder-result
description: "F8 liquidation-cascade ladder proxy (2026-10-04) PASSED 4/4 frozen rules on 10 symbols of 1m Binance SPOT — +0.54%/event, CI ex-zero, 6/6 years — but recent-24mo per-event CI touches zero, deep wicks lose, and it is untested on PERP data, which is what the live book trades."
metadata:
  node_type: memory
  type: project
  originSessionId: 2037ad27-4d88-4989-b811-caa6ea20fa15
  modified: 2026-10-04T19:45:06.663Z
---

Idea 8 of [[fable-batch-10-probe-queue]], run 2026-10-04. Code `probes/f8_cascade_ladder_proxy.py`,
log `runs/f8_cascade_ladder_proxy.log`. Data: `probes/z1_backfill_1m.py` loaded 1m Binance **spot**
for BTC/ETH/SOL/DOGE/AVAX/NEAR/LINK/SHIB/ADA/XRP, 2021-01 → 2026-08 (99.96% minute coverage).
Rule: resting bid at prior close −2.5%, TP +1.2% from fill within 60 min else exit at minute 60,
maker 2bp both legs, one position per symbol at a time.

**FROZEN RULE: PASS 4/4.** N=2038 events, 506 distinct UTC days. Mean **+0.541%/event**, 95% CI
[+0.396%, +0.678%] (cluster bootstrap by UTC day), TP hit 86.6%, positive in 6/6 years
(2021 +0.66, 2022 +0.22, 2023 +0.62, 2024 +0.53, **2025 +0.05**, 2026 +0.38). Taker on time-stop
exits barely moves it (+0.536%). Fill-at-wick-low upper bound +0.927% (not the verdict).

**Pre-run fix (declared in docstring):** bootstrap originally clustered by (symbol, day), which let
one cross-asset cascade count once per symbol, against the frozen "BY DAY" text. Fixed before any
multi-symbol output existed (the earlier smoke test was BTC-only, where the two are identical).

**Post-verdict diagnostics (not frozen):**
- **Queue risk is smaller than feared on the SAME venue:** with price-time priority, any print
  below your bid means your level was cleared, so the fill is guaranteed on that venue. Requiring a
  trade-through of 0.1% / 0.25% / 0.5% leaves +0.50% / +0.44% / +0.31% per event, all CI ex-zero;
  1.0% → +0.15%, CI touches zero.
- **Continuation risk (short-vol shape confirmed):** PnL by wick depth through the bid falls
  monotonically: <0.5% ≈ +0.8%, 0.5-1% +0.56%, 1-2% +0.32%, **>2% −0.12%** (258 events).
- **One account, 10 slices, 1x: +19.5%/yr full-sample, but 2021 alone is +71.6%.** 2025 +0.67%/yr,
  2026 +3.6%/yr. **Recent 24mo: +5.15%/yr account, per-event CI [−0.08%, +0.82%] touches zero**
  (N=266, 78 days). Same premium-decay disease as [[f1-tail-gated-carry-result]] and
  [[w3-carry-first-live-diagnosis]], so it does NOT credibly clear [[live-yield-hurdle]] on recent data.
- Not concentrated: top-5 days 10.1% of PnL, top-20 33.9%. Zero events follow a data gap.
- **MAE vs isolated liquidation (spot wicks = a FLOOR for perp):** median −1.16%, 5th pct −10.8%,
  worst −62.6% (ADA, 2025-10-10). Fills breaching liq: 3x 0.2%, 5x 1.4%, **10x 5.8%, 20x 16.0%**.
  Worst prints are real crash days (2025-10-10, 2021-05-19, LUNA 2022-05-11), not bad ticks. This is
  data for reading the live book's fills, not a leverage recommendation; the owner's leverage call
  stands ([[cursed-100-eur-live-ladder]]).

**What the PASS licenses:** the Bybit `allLiquidation` collector and the micro-live ladder ONLY.
Never a deployment or a certificate ([[alpha-definition-edge-certificate]]).

**Biggest untested assumption: SPOT → PERP.** The live book rests bids on Bybit perps; perp wicks run
deeper (more fills, more continuation, more liquidations). Next falsification step: re-run the same
frozen rule on **Binance USDT-M perp 1m dumps** (`data.binance.vision/data/futures/um/monthly/klines`,
free; same ETL, different base URL). Kill if the perp run fails any of R1-R4.
