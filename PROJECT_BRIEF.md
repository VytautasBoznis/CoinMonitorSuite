# CoinMonitorSuite — Project Brief

*A self-contained summary written so another LLM (or person) can understand the project
and offer an opinion. No external context required.*

---

## What it is

CoinMonitorSuite is a greenfield crypto **monitoring + automated trading** tool, built
solo. It is the successor to an earlier .NET/C# bachelor's-thesis prototype that polled
exchange tickers and computed basic indicators (RSI/EMA) but never executed trades. The
prototype's *patterns* (per-exchange adapters, data-plane vs control-plane split,
pluggable indicator modules) are reference only — this is a clean rebuild, not a port.

The single guiding idea: **trade coins efficiently.** It is explicitly *not* an options
play (full options trading was considered and rejected as too extreme on top of crypto
volatility). Only candle (OHLCV) data is needed — no historical volatility surface.

## Stack & platform decisions (firm)

- **Language: Python.** Chosen for the quant / backtesting / exchange ecosystem and the
  volume of examples. Raw execution speed is considered irrelevant before the system is
  profitable; a rewrite later is acceptable. The strategy engine is pure Python.
  FastAPI (control-plane API) and React/TypeScript (UI) come in later phases.
- **Exchange: Bybit as the initial target**, behind an exchange-agnostic adapter
  abstraction so more venues are cheap to add later. Access via the `ccxt` library.
  Only Bybit is implemented for now.
- **Quote currency: USDC** — a *hard constraint*, not a preference. The developer is in
  the EU, where USDT is effectively unavailable on compliant venues (MiCA-driven
  delistings). Default symbols are `*/USDC` (e.g. `BTC/USDC`). USDT must never be
  reintroduced.

## Core strategic thesis

The developer believes the tradable edge, if it exists, lives in **coin/coin (ratio)
pairs** (e.g. ETH/BTC), **not** in direct coin-vs-fiat/stablecoin pegs (e.g. BTC/USDC).

Rationale: when everything is quoted in USDC, almost every coin is dominated by its
**beta to BTC** — the whole market trends together with the macro USD–crypto tide, which
is hard to mean-revert. A **ratio like ETH/BTC strips out that common beta** and leaves
the *relative* behaviour of the two assets, which tends to be more stationary /
mean-reverting — the regime where mean-reversion strategies actually have an edge. This
is the classic statistical-arbitrage / pairs-trading rationale.

Two implementation notes that follow from this:
- **Ratios are synthesized, not traded as listed pairs.** `ETH/BTC` is computed as
  `(ETH/USDC) ÷ (BTC/USDC)`. This sidesteps thin coin/coin spot liquidity, reuses deep
  USDC liquidity on both legs, and — crucially — a synthetic ratio is "just another
  OHLCV series," so it feeds the existing engine and strategies with no interface change.
- **Spot only allows *rotation*** (hold coin A *or* coin B, whichever is relatively
  strong). True **market-neutral** pairs trading (long A *and* short B simultaneously)
  requires perpetual futures and is deferred.

## Spot vs perpetual futures (decided: spot first)

- **Phase 1 trades spot, long/flat only.** Simplest honest baseline; requires no
  funding-rate data.
- Spot and perp prices move in lockstep (the perp funding mechanism tethers them), so
  switching instruments does **not** create a lead/lag signal — the same candles produce
  the same signal either way. Only the position/fee accounting (the `Portfolio`) differs.
- **Perpetuals come later** as a `PerpPortfolio` implementing the same `Portfolio`
  interface: enables shorting/leverage and must model 8-hourly funding payments.
  Genuine derivatives-only signals (funding rate, open interest, long/short ratio) are a
  later candidate but need data feeds beyond candles.

## Developer's approach ("the edge is the test rig, not the math")

The developer has a deep IT/dev background (10+ yrs: development, networking, security,
diagnostics) but **limited quant math**, and is explicit about it. The deliberate strategy:
don't try to hand-derive profitable trading math — instead build a **rigorous, adversarial
evaluation environment** (the black-box backtester + fragility harness) and let *search*
surface strategies, with the harness as the bullshit detector. The leverage is the
**honesty of the test rig**, not bespoke alpha. This framing explains many decisions below
(black-box engine, fragility-as-kill-filter, the long-term evolutionary search).

## Phased roadmap

A single `Strategy` interface flows through every phase:

1. **Phase 1 — Backtesting** *(current focus)*: pull Bybit candle history, run pluggable
   strategies over it, report performance vs a buy-and-hold baseline.
1.5. **Phase 1.5 — Fragility stress test**: Monte Carlo perturbation (latency / inter-leg
   gap / slippage / fill-failure) on top of the Phase 1 `ExecutionModel` seam, as a
   kill-filter for thin-margin strategies. Built once the clean baseline works.
2. **Phase 2 — Trade suggestions**: generate live trade ideas from the same strategies.
3. **Phase 3 — Full automation**: execute trades automatically.

**Long-term north star (far future, *not* being built now):** an **evolutionary / genetic-
programming strategy search** — spawn many bots against the black-box exchange, with
profitability *and robustness under the fragility harness* as the fitness function, so
overfit/fragile genomes die. Only the black-box seam is built today so nothing blocks it
later. Caveat the developer is aware of: a naive GA is an overfitting machine, so any GA
work is gated on strict out-of-sample / walk-forward validation plus fragility-as-fitness,
and the harness must be proven to *reject* deliberate garbage before it's trusted.

## Phase 1 plan (the part being built now)

**Goal:** a working backtester that fetches Bybit candles, runs pluggable strategies,
and reports metrics vs buy-and-hold. Foundation for Phases 2–3 via one `Strategy`
interface.

**Out of scope for Phase 1:** live data, *live* order execution, options, UI,
multi-exchange, multi-symbol portfolios, parameter optimization, the fragility stress test
(→ Phase 1.5), evolutionary strategy search (→ far future).

**Driving architectural principle — the engine is a black-box exchange.** The strategy
never touches raw history; it talks only to a point-in-time data feed (bars one at a time)
+ an order API — the *same contract a live exchange adapter implements*. Going live later =
swapping the simulator for the real Bybit adapter, strategy unchanged. This makes
no-lookahead structural, and is the seam a future evolutionary/GA strategy search would
spawn many bots against. **Orders are sequential, not atomic:** a synthetic-ratio rotation
is two separate orders (sell ETH/USDC, then buy BTC/USDC) with a gap — the second leg
drifts, legs can partially fill or fail. (On a CEX these are internal fills, not on-chain
settlements; block confirmations only apply to deposits/withdrawals or a DEX venue.)

**Shape of the system:**
- Data layer: `ExchangeAdapter` ABC + a Bybit implementation (paged via ccxt, normalized
  to a common candle model, gap-validated), persisted to Parquet.
- A synthetic-ratio builder turns two USDC legs into a coin/coin OHLCV-like frame
  (e.g. ETH/BTC) so the ratio thesis is testable from day one.
- Pure-function indicators (`ema`, `rsi` with Wilder smoothing).
- `Strategy` ABC (single-bar push `on_bar(candle) -> int`, strategy owns its rolling state,
  no lookahead by construction) with two examples (EMA crossover, RSI mean-reversion).
  Strategies are **cost-aware**: a `CostModel` is injected (fees from config in backtest, the
  live adapter live) and each applies a **no-trade band** — switch only when the expected
  move clears the round-trip taker cost, so they don't churn fees on noise. The strategy
  *decides* on estimated cost; the portfolio *charges* realized cost (never let realized
  slippage feed the decision — that's lookahead).
- Backtest engine: bar-by-bar replay through an injectable `ExecutionModel` (default
  `IdealExecution` = fill at **next bar's open**, no slippage) and a `Portfolio`
  interface. Phase 1 ships one `SpotPortfolio` (long/flat). A spot rotation is **two
  taker fills** (sell leg→USDC, buy USDC→leg), so both legs are charged.
- Metrics: total return, win rate, max drawdown, **profit factor, Calmar**, and Sharpe
  (Sharpe reported but distrusted — crypto returns are fat-tailed and the sample is thin).
- **Fragility stress test (Phase 1.5, Monte Carlo):** a `StochasticExecution` variant adds
  seedable **latency / inter-leg gap / slippage / fill-failure**, run N times to produce a
  distribution + a fragility metric (e.g. "% of runs still beating buy-and-hold"). Off by
  default. It's a **kill-filter** for too-thin-margin strategies, not a validation badge —
  failing is a red flag; passing is not a live-ready green light. In a historical backtest,
  "data lag" and "execution lag" are the same mechanism (acting later on a stale price), so
  it's modeled once.

**Done when:** a CLI command like
`coinmon backtest --strategy ema_crossover --symbol BTC/USDC --timeframe 1h`
prints an equity curve + metrics vs buy-and-hold, with strategies swappable via one
flag and tests green; and `--symbol ETH/BTC` resolves to a synthetic ratio and
backtests as a spot rotation, exercising the coin/coin path end-to-end.

## Known open considerations (good fodder for a second opinion)

- **Two-leg execution cost.** A spot rotation is inherently *two* taker fills (sell
  leg→USDC, buy USDC→leg) crossing the spread twice; fees eat mean-reversion alive below
  daily timeframes. Phase 1 charges both legs explicitly. The remaining gap vs live is
  temporary leg imbalance / partial fills, which the fragility stress test probes.
- **Sample size / overfitting.** A single symbol over ~90 days of 1h candles is a thin,
  noisy sample (~90 days is only a smoke-test gate — the adapter pulls arbitrary-length
  history). Regimes break hard (Luna, FTX, 2022 bear); pairs that look stationary diverge
  for months. Walk-forward, multiple pairs, regime detection, and multi-cycle
  out-of-sample are **deliberately deferred** to later phases — mandatory before any
  automation, not present in Phase 1.
- **Is the coin/coin thesis sound** for retail-scale spot rotation under USDC-only
  constraints and Bybit fees? That's the central bet worth challenging.

---

*Questions this brief is meant to invite: Is the spot-first / ratio-focused / Python +
Bybit + USDC approach reasonable? Is "build a brutally honest test rig and let search find
the edge" a sound bet for someone without deep quant math, or a trap? What's being
underestimated? What would you change before writing code?*
