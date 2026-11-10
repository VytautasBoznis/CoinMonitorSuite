# Strategy review and new proposals — 2026-11-10

Snapshot taken 2026-11-10 ~17:10 UTC from the cluster ledger (`bot_trades`), the dashboard API, and
Hyperliquid's public fill, candle and rate-limit records. Nothing was changed on the bots.

## Short version

- **All four bots are green, but on almost no evidence.** Every dollar came from four UTC days
  (10-29, 10-30, 11-08, 11-10), and all four were sharp V-shaped bounces. The one fill that did not
  bounce (ADA, 10-14) made a cent. No bot is near its N = 50 bar.
- **The live bot's take-profit is +1.2%, not 1.95%.** I could not find 1.95% anywhere in its rule,
  ledger or logs (see "The 1.95% question"). The instinct behind the complaint is still right: the
  existing 180-cell grid says a wider take-profit paid more at every hold time, in both the train
  years and the holdout years.
- **Recommended:** test the wider exit properly (R1 below) before touching the live rule.
  **Done the same day: R1 PASSED 3/3** (+6.8%/yr on the holdout, CI [+3.4, +10.5]). Next is a
  paper bot, not a live change.
- **Free improvement, owner's call:** the leverage set on the venue buys nothing at a $12 rung and
  puts a hard stop about 2.5–3% under each fill, which the backtest never had.
- **Six new probes proposed**, each with PASS/KILL written before any data is read.

## Where the bots stand

| Bot | Rule (bid / TP / hold) | Round trips | TP hits | Net | Mean net per trip | Backtest mean | Verdict |
|---|---|---|---|---|---|---|---|
| f8-ladder (live) | −2.5% / +1.2% / 60m | 8 | 7 | +$1.06 | +1.10% | +0.50% | too early |
| f8-twin (paper) | same | 5 | 5 | +$0.70 | +1.17% | +0.50% | measurement only |
| f8-wide (paper) | −1.5% / +2.0% / 240m | 12 (+1 open) | 11 | +$2.68 | +1.86% | +0.32% | too early |
| f8-trend (paper) | F8 + 30-day uptrend gate | 0 | – | $0 | – | +0.45% | idle |

- The live figure matches the venue: closed P&L $1.099, fees $0.035, funding +$0.0003.
- Live is running at roughly 19%/yr on the $72 it can deploy. That number is two cascades and means
  nothing yet.
- **Judging clock:** the paper bots first ran 2026-10-21 19:06 UTC, so the bar is read once on
  **2027-04-21**.

## The 1.95% question

The live rule sells at +1.2% from the fill, and 6 of its 7 take-profits filled at exactly that. The
seventh (SOL, today) sold at +1.76% because the price had already run past the target when the
order went in. Two readings of "1.95%" that fit the data:

1. **f8-wide's trades net +1.97% each** (its +2.0% target minus fees). If the point is "the paper
   bot gets 2% and the live one settles for 1.2%", that is exactly what happened.
2. **The Ladder panel's "x% from mid"** is the distance from a resting bid to the live price. It
   drifts between about 1.5% and 3.5% inside a minute and is not an exit.

Either way the question is the same: **is +1.2% too early?**

### What the live fills say

Price after each of the 7 live take-profit fills, from Hyperliquid 1m candles:

| Fill | Best gain within 5m | within 60m | within 240m | At 60m | Minutes to reach +2.0% |
|---|---|---|---|---|---|
| ETH 11-08 | +1.75% | +1.75% | +2.90% | +1.02% | 76 |
| DOGE 11-08 | +2.06% | +2.82% | +4.22% | +2.11% | 5 |
| XRP 11-08 | +1.94% | +2.40% | +3.25% | +1.46% | 7 |
| SOL 11-10 (first) | +2.54% | +2.92% | +3.49% | +1.70% | 1 |
| ETH 11-10 | +1.74% | +2.20% | +3.07% | +1.42% | 6 |
| XRP 11-10 | +2.04% | +2.40% | +2.50% | +0.93% | 5 |
| SOL 11-10 (second) | +2.09% | +2.48% | +3.04% | +1.26% | 5 |

A +2.0% target with the same 60m hold would have filled on 6 of 7 and time-exited ETH 11-08 at
about +1.0%: roughly **+13.0% gross summed over the seven, against the +9.0% actually taken**.

That is two events, both bounces. On 11-10 every coin was back below its fill price four hours
later, so the wide exit only wins if the target is reached before the bounce fades.

### What the backtest says

The F8 grid (`runs/f8_param_grid.log`), bid depth held at 2.5%, account yield per year at 1x:

| TP | 60m hold, train | 60m hold, holdout | 240m hold, train | 240m hold, holdout |
|---|---|---|---|---|
| 0.6% | +10.4% | +5.1% | +14.8% | +7.9% |
| 0.8% | +15.8% | +7.1% | +20.8% | +10.5% |
| 1.0% | +17.1% | +9.4% | +23.9% | +12.8% |
| **1.2% (live)** | **+21.7%** | **+10.0%** | +28.2% | +13.0% |
| 1.6% | +26.4% | +13.9% | +36.7% | +16.8% |
| 2.0% | +30.4% | +16.9% | +38.4% | +19.1% |

Wider is better at every step, in both periods. The best cells sit on the edge of the grid, so the
true optimum may be wider still.

**Why this is not yet a verdict:** the pattern was noticed after the holdout was seen, and the only
formal test run so far (the grid's train pick against the live rule) had a difference CI of
[−8.3, +22.6] %/yr. A same-entry comparison of TP 2.0% against TP 1.2% has never been run. It
should be much tighter, because both rules buy the same fills. That test is R1.

## Review of each bot

### f8-ladder (live)

- **The mechanism is confirmed.** The venue tags 6 of the 8 entries as fills against a liquidation.
  The bot is buying from forced sellers, as designed.
- **Queue position, the "deciding unknown", is 5 for 5 so far.** Every fill the paper twin took,
  the live bot also got, at the same price (gap 0.001%). At a $12 rung this says nothing about
  larger size.
- **Live got two fills the simulation cannot see**, both SOL today:
  - One filled at 82.181, below the venue's own 1m candle low of 82.578. The second (82.538) was
    also below that low. Both are liquidation fills. Hypothesis, N = 2: Hyperliquid's candles leave
    out some liquidation prints, so candle-based touch-fills *undercount* real fills.
  - The second came from re-bidding 5 seconds after the first take-profit, inside the same minute.
    The backtest only re-bids on the next bar. This won once; it is also the falling-knife pattern
    (buying the same crash twice) and is unpriced by any probe.
- **Action budget:** 8,721 of 10,193 used, about 257 a day. It runs out around **2026-11-16**.
  After that the account gets one write per 10 seconds, which is 8,640 a day against the 257 it
  uses, so the throttle only bites in the cascade minute itself: six coins' orders queue up over
  about a minute. A take-profit that goes in after the price has passed its target simply sells at
  market (today's SOL: +1.76% minus a 0.03% higher fee).
- **Fill-to-exit lag:** today's first SOL fill was noticed 10 seconds after it happened (the cycle
  was busy re-pegging the other coins). It helped this time.
- **Reliability:** 294 failed cycles in 19 days (DNS and gateway errors), each one a skipped
  3-second cycle. I did not check whether any fell inside a cascade minute. The death alert is
  still owed.
- **Leverage (recorded once, not reopening the decision):** at the leverage currently set,
  liquidation sits 2.5–3.1% below the fill on four of the six coins. On 11-08 ETH dipped 2.2% after
  the fill, 0.85% short of liquidation. The backtest holds through such dips; its own table says
  17% of fills would breach at 20x against 0.5% at 3x. The rung is $12 whatever the leverage, so
  lower leverage only locks more idle margin (about $24 of the account at 3x) and gives up no
  return. This matters more if the hold gets longer.

### f8-twin (paper)

Doing its job. Keep it identical to the live rule: the moment the live rule changes, the twin must
change with it under a new name, or the live-versus-paper measurement breaks.

### f8-wide (paper)

- 11 of 12 take-profits against a backtest hit rate of 59%. That is the bounce regime, not skill.
  Its backtest mean is +0.32% per trip; it is showing +1.86%.
- Its −1.5% entry has no live twin, so nothing yet measures whether real fills at that depth match
  paper. If it reaches promotion, that is the first thing its micro-live run measures.

### f8-trend (paper)

- Zero trades: all six coins have been below their 30-day-ago price since the first run.
- Its own frozen baseline is +4.7%/yr, already under the 5% bar, with about 31 trips expected by
  the judging date. It will most likely miss on N alone and need the 12-month look.
- It costs nothing to leave running. Both live cascades happened in exactly the down-trend
  conditions it avoids, and both paid, which is two small points against the gate.

## Improvements, in order

1. **Test the wider exit (R1), then run it on paper beside the twin.** Do not edit the live rule
   in place.
2. **Reconsider leverage at the $12 rung** (owner's call; see above).
3. **Record the venue's liquidation tag on every fill** in the ledger. One nullable column; it is
   the cheapest new dataset available (R6).
4. **Decide the same-minute re-bid on purpose.** Today it is an accident of timing. Either price it
   (R1's replay can re-bid inside the bar) or hold the re-bid until the next minute so live matches
   what was tested.
5. **Build the death alert** before the throttle starts, since throttled exits are slower.

## New proposals

Rules for all of them: the PASS/KILL lines below are the pre-registration. Tuning is a small
exhaustive grid with every cell recorded, never a search. A pass earns a paper bot with a frozen
baseline, not money. Load times must be estimated before any backfill starts.

### R1 — F8 wide exit (answers the 1.95% question)

- **Idea:** same bids as the live rule, take-profit +2.0% instead of +1.2%, hold 60m.
- **Test:** paired difference in account yield, TP 2.0% minus TP 1.2%, on the same 6 coins, UTC-day
  bootstrap. Reported separately for train (2021 → 2024-09) and holdout (last 730 days).
- **PASS:** difference CI excludes zero in BOTH periods, and the 2.0% rule's worst calendar year is
  no worse than the live rule's worst year.
- **KILL:** either CI spans zero. Then +1.2% stays and the question is closed.
- **Declared post-hoc:** the holdout has been seen, so a pass is a reason to run a paper bot
  (`f8-tp20`, plus `f8-tp20-240` for the longer hold), not to move the live rule.
- **Data:** already in the local DB. Minutes to run.

**RESULT, run 2026-11-10: PASS 3/3** (`probes/r1_f8_wide_exit.py`, log `runs/r1_f8_wide_exit.log`;
the self-check reproduced the grid's two holdout rows exactly).

| Period | TP 2.0% | TP 1.2% (live) | Difference | 95% CI |
|---|---|---|---|---|
| Train, 2021 → 2024-09 | +55.7%/yr | +41.2%/yr | +14.5%/yr | [+7.2, +22.9] |
| Holdout, last 730 days | +16.8%/yr | +10.0%/yr | +6.8%/yr | [+3.4, +10.5] |

- The wider exit won in all six calendar years. Worst year (2026): +6.1% against +3.5%.
- With a 240m hold as well (diagnostic, not the verdict): holdout +19.1%/yr, difference +9.1%/yr,
  CI [+4.0, +15.0]; but its 2026 was +2.5%, below both 60m rules.
- **The cost:** the take-profit hits 77% of the time instead of 89%, and positions sit longer in
  the dip. Fills that would breach a 20x liquidation rise from 18.3% to 23.8% (10x: 7.6% to 9.4%;
  3x: 0.5% either way). The yields above are unlevered and assume no liquidation.
- **Still post-hoc.** The holdout was seen before this test was designed, and 2026 is weak for
  every rule. The pass licenses paper bots `f8-tp20` and `f8-tp20-240`, each with a frozen
  baseline at Hyperliquid fees, and nothing more.
- **Paper bots built 2026-11-10, not deployed** (`swarm.BOTS`; baselines in
  `runs/swarm_baselines.log`, same replay and window as the other bots, whose rows reproduced
  unchanged). Same promotion bar as f8-wide; each bot's six-month clock starts at its first run.

  | Bot | Rule | Trips/yr | Mean net | 95% CI | TP hit | Yield/yr |
  |---|---|---|---|---|---|---|
  | f8-tp20 | −2.5% / +2.0% / 60m | 116 | +0.88% | [+0.49, +1.25] | 73% | +17.1% |
  | f8-tp20-240 | −2.5% / +2.0% / 240m | 112 | +1.04% | [+0.64, +1.38] | 79% | +19.3% |

### R2 — F8 on coins it has never seen

- **Idea:** the frozen rule, unchanged, on the 20 largest Binance USDT-M perps (by 2024 volume)
  that are listed on Hyperliquid and were not among F8's ten.
- **Why:** it is the only truly out-of-sample test left that does not need waiting. It also decides
  whether the ladder can widen beyond six coins, which is the simplest way to more round trips.
- **PASS:** the original four frozen F8 rules on the new coins, plus recent-24-month account yield
  ≥ 5%/yr.
- **KILL:** any of the four fails. Then F8 is a majors effect and the coin set stays.
- **Data:** 1m perp history for 20 coins. Limit to the last 36 months and estimate first; if the
  estimate is over 30 minutes, cut to 10 coins.
- **Free first step:** the four already-tested coins (AVAX, NEAR, LINK, kSHIB) need no probe. Ten
  coins at $12 is $120 notional, so that widening needs at least 2x.

### R3 — Crash rung

- **Idea:** a second, deeper bid per coin at −5%, with its own +2.0% target and 240m hold.
- **Why:** F8's losers are the fills where the wick keeps going more than 2% past the bid
  (−0.30% per event on perps). A second rung buys that continuation at a better price. It also
  uses capital that is idle almost all the time.
- **Test:** replay of the two-rung book against the one-rung book, one grid of depth {4, 5, 6}% ×
  target {1.2, 2.0}%, all six cells recorded.
- **PASS:** the train pick adds ≥ 3 points of account yield on the holdout with the difference CI
  excluding zero, and the book's worst day is no worse than 1.5× the one-rung book's.
- **KILL:** otherwise.
- **Data:** already in the local DB.

### R4 — Volatility-scaled depth

- **Idea:** the bid sits at k × the coin's own recent 1m volatility instead of a flat 2.5%.
- **Why:** BTC touched −2.5% on 3 days in two years while ADA touched it on 33. A flat depth leaves
  the BTC rung dead and may be too shallow for the alts.
- **Test:** one knob, k ∈ {4 values chosen so the median depth across coins is 1.5, 2.0, 2.5,
  3.0%}, volatility = median absolute 1m return over the prior 24h. Pick on train, judge on
  holdout once.
- **PASS:** pick beats the flat rule on the holdout with the difference CI excluding zero.
- **KILL:** otherwise. Note this is the closest proposal to parameter tuning; one knob, four cells,
  and it stops there.
- **Data:** already in the local DB.

### R5 — Hyperliquid oracle gap (collector first)

- **Idea:** Hyperliquid's oracle is the median of other exchanges, refreshed every 3 seconds. In a
  cascade the local price can fall well below it. Bid relative to the oracle instead of the prior
  close, so the bot buys Hyperliquid-specific dislocation rather than a market-wide fall.
- **Why:** it is the reachable form of the cross-market idea. It needs no speed race, because the
  bid is already resting.
- **Step 1, now:** record mark, oracle, mid, funding and open interest for every coin once a minute
  (one public request covers all coins). Hyperliquid serves only about 3.5 days of 1m history, so
  this data exists only if we start collecting it.
- **Step 2, at 90 days of data:** write the PASS/KILL then, before reading it.
- **Cost:** one request a minute; no key.

### R6 — Liquidation-tagged fills (dataset, not yet a strategy)

- **Idea:** the venue tells us which of our fills came from a liquidation. Compare outcomes of
  tagged against untagged fills, and check whether tagged fills are the ones missing from candles.
- **Why:** if liquidation fills bounce harder, the hold and target could depend on the tag, and the
  bot knows the tag seconds after the fill.
- **Now:** store the tag. **Test** only once there are ≥ 30 fills of each kind; today there are
  6 and 2.

### Considered and not proposed

- **Short side of the bounce** (fade the rebound): F8S already showed squeezes keep running.
- **Stablecoin de-peg ladder:** same shape as F8 with a hard anchor, but perhaps 5–10 events in
  five years. It can never reach a meaningful N.
- **Hedged funding carry inside one account:** needs portfolio margin ($10k), which the owner has
  parked.
- **Cascade-breadth gating:** C1 says same-minute multi-coin fills are F8's worst; the two live
  events say the opposite. Tiny N both ways, no testable edge.
- **Extending the grid to wider targets and longer holds on the same data:** that is tuning on a
  holdout already seen. Wider variants go forward on paper instead.

## Suggested order

1. R1 (minutes, existing data, answers the open question).
2. R5 step 1 and R6's column (collectors first; the data cannot be backfilled).
3. R3 and R4 (existing data).
4. R2 (needs a bounded backfill).
