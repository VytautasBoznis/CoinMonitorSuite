---
name: perp-short-capability
description: "Directional expansion: the downtrend-holdout NO-GO is fixed by ADDING a leveraged perp short (profit when price falls), not by relaxing the gate; PerpPortfolio + 3-state engine + ShortWhenFlat landed (G1), genome/search wiring still to do (G2)"
metadata:
  node_type: memory
  type: project
  originSessionId: continue-2026-06-28
---

**The decision (user, 2026-06-28).** Faced with the [[first-live-search-graduation]] open
question — every GA winner beats B&H on the downtrend holdout but is absolutely negative, so the
absolute-return gate NO-GO's all of them — the user chose **none of the gate-softening options**.
Instead: *"currently you can only work with spot pricing, so in a downtrend market can't really
perform … introduce puts with leverage at the moment you would want to sell and we have a new game."*
So the **graduation gate stays absolute/honest** (never bless a money-losing strategy); the fix is
to give the engine a **bearish leg** that profits from the drop.

**Modeling choice (user picked): leveraged USDT-perp short.** The scraper stores only spot candles
— no options chain / IV in the DB. Of {leveraged perp short, synthetic capped-loss put, real
options chain}, the user chose the **perp short**: directly modelable from spot candles, directly
tradable on Bybit, fits the [[project-direction]] "not options-first" stance. ("puts with leverage"
was the intent = a leveraged bearish bet; the perp models that without an options data source.)

**Chunk G1 — directional engine capability (LANDED, 106 tests green).**
- `PerpPortfolio(cash, taker_fee, leverage)` in `backtest/portfolio.py`: long/flat/short, isolated
  **all-in** leverage (whole account is the margin for one position), taker fee on the full notional
  each leg, `units` signed (short gains as price falls). `equity()` latches an **isolated-margin
  liquidation** the first bar the mark hits 0 (collateral gone, position force-closed, loss booked
  as a trade, account dead for the run). Fulfills the `PerpPortfolio` seam the `Portfolio` ABC
  already named.
- Engine/`BarStepper` generalized to a **3-state position** (-1/0/+1): fill side = buy if target >
  position else sell (a long→short flip sells, short→flat buys); exposure uses `abs(position)`.
  The 0/1 spot path is byte-unchanged — parity preserved, all prior tests green.
- `strategies/directional.py::ShortWhenFlat(base)`: turns a long/flat strategy's `0` (exit-to-cash)
  into `-1` (short); +1 and an existing -1 pass through. Leverage lives in the portfolio, not here.
  This *is* "at the moment you'd sell, short instead." Proof test: same falling series, long/flat
  spot bleeds while ShortWhenFlat+PerpPortfolio profits.

**Model simplifications (honest, first-pass):** liquidation checked on the bar CLOSE only (intrabar
wick that liquidates-then-recovers is missed); no maintenance-margin buffer (liq at mark ≤ 0,
marginally generous); no funding; an all-in long→short flip is one fill at one open price (not two
sequential legs). On liquidation the engine's tracked `_position` desyncs from the portfolio (engine
still thinks it holds; portfolio refuses to trade) — practically the run just stays dead at ~0
equity, which is the honest outcome. The eval rig (OOS fitness + fragility + holdout) is what
punishes reckless leverage, not a hand-tuned cap.

**Chunk K2 — direction is a gene (LANDED 2026-06-28, 113 tests green, ruff clean).** The GA now
*chooses* directionality. `Genome` gained `short: bool` + `leverage: float` (both default to the
long/flat spot book, so a chunk-B genome is byte-unchanged); `LEVERAGE = ParamSpec(1.0, 5.0)` is the
modest sampled range (the eval rig prunes reckless leverage, not a hand cap). `decode` wraps the
family in `ShortWhenFlat` when `short`; a NEW sibling `decode_portfolio(genome) -> (cash, fee) ->
Portfolio` yields the perp-vs-spot book (kept separate from `decode` because the rig builds strategy
and book at different points/capital). Threaded the factory through everything that used to hard-build
`SpotPortfolio`: `evaluate_fitness` gained an optional `make_portfolio=` (defaults to spot →
back-compat for tests/walk-forward), and `search/runner` (`_score_genome` + the fragility post-filter)
+ `graduation` now pass `decode_portfolio(genome)`. GA `random_genome`/`mutate`/`crossover` sample and
move the direction genes; `_key` includes them so a long and a short twin don't collide in the fitness
memo. Report summaries print `[Lx perp short | long/flat spot]`. CLI `search` explores direction by
default — no new flag. Synthetic proof test: the same RSI genome run as a 2x perp short out-returns
its spot twin and graduates **GO** on a downtrend.

**Still open (user run, not code):** the *real* downtrend-holdout GO is unproven against the live DB —
`coinmon search --timeframe 1d --holdout 0.2 --stress 80` (Docker DB up). Note: a clean synthetic
mean-reverter still profits long at zero fees, so the unit test asserts "short out-returns long + GOs"
rather than forcing the long to NO-GO; the documented long-NO-GO was on real data
([[first-live-search-graduation]]). Tie back to [[build-roadmap]] — chunk K is now done; next is
chunk **G** (suggestions service), *blocked on delivery channel*.
