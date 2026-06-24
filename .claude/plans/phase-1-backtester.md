# Phase 1 Plan — Multi-strategy backtester on Bybit candles

**Objective:** a working backtester that pulls Bybit candle history, runs pluggable
strategies over it, and reports performance vs a buy-and-hold baseline. This is the
foundation Phases 2 (suggestions) and 3 (automation) plug into via the same
`Strategy` interface.

**Out of scope for Phase 1:** live data, live order execution, options, UI,
multi-exchange, multi-symbol portfolios, parameter optimization.

---

## Architectural principle: the engine is a black-box exchange

**Driving idea.** The strategy never touches raw history. The engine exposes the **same
contract a live exchange adapter implements** — a point-in-time data feed (bars delivered
one at a time, nothing past the current bar) plus an order-submission API — and the
strategy talks *only* to that. In Phase 1 the simulator implements that contract; "going
live" later means swapping in the real Bybit adapter behind the same interface, with the
strategy code unchanged. Consequences:

- **No-lookahead is structural, not a convention** — the strategy *cannot* see the future
  because the black box never hands it over.
- **Live-swap parity** — sim and live are interchangeable behind one interface.
- **Event-driven, not vectorized** — required for live parity and for later spawning many
  strategy instances (evolutionary search) against the same interface. *(The evolutionary
  / GA strategy search itself is a far-future phase — only the black-box seam is built now,
  so nothing paints us into a corner.)*

**Orders are sequential, not instant or atomic.** A synthetic-ratio rotation (ETH→BTC) is
**two separate orders** — sell ETH/USDC, then buy BTC/USDC — filled in sequence with a gap
between them. (On Bybit these are internal matching-engine fills, ~instant and **not** per-
trade on-chain settlements; blockchain confirmations apply only to deposits/withdrawals, or
to a DEX venue later.) The gap still bites: between the two fills the second leg's price
drifts, so the **achieved ratio ≠ the signalled ratio**, and a leg can partially fill or
fail (leaving a half position in USDC). The order API models a rotation as **two sequential
fills**; baseline = same bar / zero gap, **Phase 1.5** adds inter-leg latency, per-leg
slippage, and partial/failed-leg risk.

---

## Proposed repo layout

```
CoinMonitorSuite/
  pyproject.toml            # deps + tooling (ruff, pytest); uv-managed
  README.md
  src/coinmon/
    config.py               # symbols, timeframes, paths, fees (pydantic-settings)
    data/
      models.py             # Candle schema / column contract
      store.py              # Parquet read/write per exchange/symbol/timeframe
      ratio.py              # synthetic ratio frame from two USDC legs
                            #   ETH/BTC = (ETH-USDC) / (BTC-USDC) -> OHLCV-like series
      adapters/
        base.py             # ExchangeAdapter ABC: fetch_ohlcv(symbol, tf, since, until)
        bybit.py            # Bybit impl via ccxt (paged, gap-validated)
    indicators/
      __init__.py           # ema(), rsi(), ... pure fns over a DataFrame (ported from prototype)
    strategies/
      base.py               # Strategy ABC: generate_signals(candles) -> signal series
      ema_crossover.py
      rsi_meanreversion.py
    backtest/
      portfolio.py          # Portfolio ABC + SpotPortfolio (long/flat, both legs charged).
                            #   PerpPortfolio (long/short + funding) is a future impl.
      execution.py          # ExecutionModel ABC + IdealExecution (next-bar open, no slip).
                            #   StochasticExecution (latency/slippage/fill-fail) = Phase 1.5.
      engine.py             # black-box exchange: point-in-time feed + order API;
                            #   event-driven, no lookahead; ExecutionModel injected
      stress.py             # Phase 1.5: Monte Carlo runner + fragility metric
      metrics.py            # return, win rate, max drawdown, profit factor, Calmar, Sharpe
      result.py             # result container + text summary (+ optional plot)
    cli.py                  # `coinmon fetch-data` / `coinmon backtest`
  tests/
    test_indicators.py
    test_backtest.py
  data/                     # parquet output (gitignored)
```

**Dependencies:** `ccxt`, `pandas`, `numpy`, `pyarrow`, `pydantic-settings`,
`pytest`, `ruff`. (Indicators hand-rolled to match the prototype + stay lean; add
`pandas-ta` only if it pays off. `matplotlib` optional for plots.)

---

## Build steps (each with a verification gate)

1. **Scaffold** — repo layout, `pyproject.toml`, config, tooling.
   *Verify:* `pip install -e .` works; `ruff` + empty `pytest` run clean.

2. **Bybit data adapter** — `ExchangeAdapter` ABC + `BybitAdapter.fetch_ohlcv`
   (paged through ccxt, normalized to the common candle model), written to Parquet
   via `store.py`.
   *Verify:* pull `BTC/USDC` 1h for ~90 days → sane row count, monotonic UTC
   timestamps, **no gaps** (log + reject bad/incomplete data), round-trips through Parquet.
   (~90 days is a **smoke-test gate only** — the adapter must fetch **arbitrary-length
   history** so later multi-cycle / out-of-sample research isn't blocked.)

3. **Synthetic ratio pairs** — `ratio.py` builds a coin/coin OHLCV-like frame from
   two USDC legs (e.g. `ETH/BTC` = `ETH/USDC` ÷ `BTC/USDC`), aligned on a shared
   timestamp index. Output conforms to the same candle column contract so it feeds the
   engine and strategies unchanged. This is the form where the edge is expected
   (ratios strip the common BTC/USD beta → more mean-reverting than fiat pegs).
   *Verify:* `ETH/BTC` frame aligns leg timestamps (inner-join, no NaN rows), close ≈
   ETH-USDC/BTC-USDC, and round-trips the candle contract.

4. **Indicators** — `ema()`, `rsi()` as pure functions over a candle frame (port
   the prototype's logic; use Wilder smoothing for RSI to be correct).
   *Verify:* unit tests on hand-computed known inputs.

5. **Strategy interface + 2 examples** — `Strategy` ABC; `EMACrossover` and
   `RSIMeanReversion`. Signals use only data ≤ current bar (no lookahead).
   *Verify:* each emits a sensible signal series on sample candles; a lookahead
   guard test passes.

6. **Backtest engine** — bar-by-bar replay: strategy → orders → `ExecutionModel` →
   `portfolio` → equity curve. `metrics` computes total return, win rate, max drawdown,
   profit factor, Calmar, and Sharpe (reported, not trusted).
   - **`Portfolio` is an interface from day one.** Phase 1 ships **one** concrete impl,
     `SpotPortfolio`: long/flat only (short signals clamp to flat).
   - **Both legs charged, sequentially.** A rotation (e.g. ETH→BTC) is **two sequential
     taker fills** — sell leg→USDC, buy USDC→leg — so the synthetic ratio drives the
     *signal* but PnL charges a taker fee on **each leg**. (Under-charging ~doubles
     apparent fee edge.) Baseline fills both at the same next-bar open (zero inter-leg
     gap); inter-leg drift / partial-fill risk is added in Phase 1.5.
   - **`ExecutionModel` is an injectable seam.** Phase 1 default = `IdealExecution`:
     fills at the **next bar's open** (never the signal bar's close — same no-lookahead
     discipline as step 4), no slippage. Stochastic stress variant added in **Phase 1.5**.
   - `PerpPortfolio` (long/short + 8h funding deductions, requires a separate
     funding-rate fetch) is a **future impl of the same interface**, not built in Phase 1.
   - Crypto returns are fat-tailed → trust **max drawdown / Calmar / profit factor**;
     **Sharpe is low-signal** on a single ~90-day 1h sample.
   *Verify:* full backtest of each strategy runs end-to-end, prints a metrics summary,
   and is compared against a **buy-and-hold baseline**.

---

## Definition of done

`coinmon fetch-data` populates Parquet, and `coinmon backtest --strategy ema_crossover
--symbol BTC/USDC --timeframe 1h` prints an equity curve + metrics vs buy-and-hold —
with at least two strategies swappable via one flag, and tests green. The same
`--symbol ETH/BTC` resolves to a **synthetic ratio** (built from the two USDC legs)
and backtests as a spot rotation, exercising the coin/coin path end-to-end.

---

## Phase 1.5 — Fragility stress test (Monte Carlo)

Built on the Phase 1 `ExecutionModel` seam once the clean baseline works.

`StochasticExecution` implements the same `ExecutionModel` seam with **seedable** knobs:
**latency** (signal→fill delay, drawn per trade), **inter-leg gap** (drift between a
rotation's two sequential fills → achieved ratio ≠ signalled ratio), **slippage** (adverse
bps per fill), and **fill failure** (a leg partially fills or fails, leaving a half
position in USDC). A runner replays the strategy **N times** with
different seeds and reports a **distribution** (return / max DD / profit factor
percentiles) plus a **sensitivity sweep** (edge vs increasing mean latency). Yields a
**fragility metric** — e.g. *"% of runs still beating buy-and-hold"* — to flag
too-thin-margin strategies before they're ever considered for live use.

- **Off by default**; the Phase 1 baseline stays deterministic and clean.
- It's a **kill filter, not a validation badge**: failing = clear red flag; passing
  ≠ live-ready. **Do not** tune parameters to pass it (that's overfitting the noise model).
- Note: in a historical backtest, "data lag" and "execution lag" are the *same*
  mechanism (acting later on a stale, worse-known price) — modeled once, not twice.

*Verify:* a strategy with a known thin edge degrades to ≤ buy-and-hold under modest
simulated latency/slippage, and the fragility metric reflects it.

## Resolved: instrument choice

- **Phase 1 = spot (long/flat).** Simplest honest baseline; needs no funding-rate data.
- Spot and perp prices move in lockstep (funding tethers them), so this is **not** a
  lead/lag signal — same candles produce the same signal either way. The data
  pipeline (steps 2–4) is instrument-agnostic; only the `Portfolio` impl forks.
- **Perps later** = a `PerpPortfolio` implementing the same interface (long/short +
  funding). Genuine derivatives signals (funding rate, open interest, long/short ratio)
  are a **Phase 2** candidate — they need feeds beyond candles, out of Phase 1 scope.
