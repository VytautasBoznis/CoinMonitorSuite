---
name: f8-cascade-ladder-result
description: "F8 liquidation-cascade ladder proxy PASSED 4/4 frozen rules on 1m Binance SPOT (2026-10-04, +0.54%/event) AND on USDT-M PERP (2026-10-08, +0.51%/event, N=2261). Recent-24mo clears the yield hurdle only on touch-fills; any trade-through requirement puts it back under/at 5%/yr with CI touching zero. Queue position is now the deciding unknown."
metadata:
  node_type: memory
  type: project
  originSessionId: 2037ad27-4d88-4989-b811-caa6ea20fa15
  modified: 2026-10-08T18:01:05.742Z
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

**SPOT → PERP: TESTED 2026-10-08, PERP PASSES 4/4 too.** Kill rule pre-registered in the probe
docstring before any perp bar loaded. `probes/z1_backfill_1m.py --perp` loaded Binance USDT-M perp 1m
for the same 10 coins (SHIB as `1000SHIB/USDT:USDT`), 2021-01 → 2026-09, stored as
`binance / <COIN>/USDT:USDT / 1m`. `f8_cascade_ladder_proxy.py --perp`, log
`runs/f8_cascade_ladder_proxy_perp.log`. N=**2261** (+11% vs spot: deeper wicks = more fills, as
predicted), mean **+0.509%**/event, CI [+0.360%, +0.649%], 6/6 years positive (2025 +0.27% vs spot
+0.05%). One-account full-sample +20.0%/yr.
- **Continuation risk worse on perp, as predicted:** wick >2% through the bid −0.30%/event (spot −0.12%,
  N 342 vs 258). Isolated-liq breach 3x 0.5% / 5x 1.8% / 10x 6.7% / **20x 17.0%** (D-F, perp-native now).
- **Recent regime: perp better than spot, but NOT a credible hurdle clear.** On spot's exact window
  (checked ad hoc, so the one-month window shift doesn't confound it): perp acct +6.59%/yr vs spot +5.15%,
  CI just ex-zero vs touching. New diagnostic **D-G (recent 24mo × trade-through)**, in both logs:
  perp touch-fill +6.99%/yr CI [+0.03%, +0.82%] → **0.1% trade-through +5.22%/yr, CI touches zero** →
  0.25% +3.32% → 0.5% +2.02%. Spot: 5.15 / 3.65 / 2.18 / 0.54. Perp is ~+1.5pp/yr better at every
  strictness, but the hurdle clear rests entirely on touch-fills, and a Binance print says nothing about
  queue position on Bybit. **[[live-yield-hurdle]] verdict unchanged: not deployable; the license
  (collector + micro-live) survives.**
- Spot rerun with D-G appended was byte-identical to the committed spot log (reproducible).

**Collector DONE 2026-10-08** → [[bybit-liquidation-collector]] (built, verified, RUNNING locally).
Correction to the old NEXT line: the collector measures forced flow, it does NOT settle queue position.
**Bybit-native rerun: SKIPPED by owner 2026-10-08, NEVER RUN.** Pre-registered (G1 venue
replication, H1 hurdle on >=1-tick trade-throughs) in the probe docstring with `--bybit` code, but the
Bybit 1m REST backfill was ~2-3h and the owner killed it ([[no-multi-hour-data-loads]]). Partial
`bybit` 1m rows (BTC 2021-01 → ~2025) sit in the local DB; no probe read them. Queue position stays
open — only the live book settles it now.
