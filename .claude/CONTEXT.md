# CoinMonitorSuite — Project Context

Greenfield crypto monitoring + automated trading tool. Successor to the user's
bachelor's prototype in `C:\Dev\CoinMonitor` (.NET) — that prototype is a
**reference for patterns only**, not a codebase to port.

**Goal in one line:** trade coins efficiently — monitor markets, backtest
strategies, surface trade suggestions, and (eventually) execute automatically.

---

## Strategic decisions (firm)

- **Stack:** Python 3.12 for the engine. `FastAPI` for the control-plane API and
  React/TS for the UI *when those phases arrive*. Pure Python until then.
  (Chosen for the quant/backtest/exchange ecosystem; speed irrelevant pre-profit,
  rewrite acceptable later.)
- **Exchange:** **Bybit first**, accessed via `ccxt`. A per-exchange adapter
  abstraction keeps additional venues cheap later, but only Bybit is implemented now.
- **Spine = efficient coin trading, not an options play.** Bybit options
  (puts/calls) stay *available* but are not the focus, so we only need **candles**,
  not a historical options vol surface.
- **Working instrument assumption:** Bybit **linear USDT perpetuals** (leverage +
  shorting + deepest liquidity); spot comes free from the same candle data.
  *(Open — confirm before live phases.)*

## Roadmap (one Strategy interface flows through all three)

| Phase | Deliverable | Execution risk |
|-------|-------------|----------------|
| **1** | Multi-strategy **backtester** on Bybit candles | none (historical only) |
| **2** | Live **scanner** → ranked **trade suggestions** in a UI | none (human executes) |
| **3** | **Automated execution** under risk limits + kill-switches | real money |

---

## Architecture

Two planes, mirroring the prototype's good split:

- **Data/engine plane** — ingest candles, compute indicators, run strategies,
  backtest, (later) scan live + execute.
- **Control plane** — FastAPI + UI for configuration, results, and suggestions
  (Phase 2+).

### Component map (and prototype lineage)

| Component | Role | Prototype lineage |
|-----------|------|-------------------|
| `ExchangeAdapter` (ABC) → `BybitAdapter` | Fetch candles, normalize to common model | `MarketWatchManager` + `IDataFormatter` |
| Candle store | Persist/read OHLCV | Elasticsearch (replaced: Parquet → Timescale) |
| `indicators` | Pure functions over a candle frame (RSI, EMA, …) | "EcoIndex" managers (RSI/EMA/Force) |
| `Strategy` (ABC) | Signals from candles + state; **same class used in backtest & live** | (new) |
| `BacktestEngine` | Replay candles → simulate fills/fees → metrics | (new) |
| Scanner / Executor | Phase 2 / Phase 3 | `CexManager` trading (was a stub) |

### Storage strategy

- **Phase 1 (historical backtest):** Parquet files (via `pyarrow`), optionally
  queried with DuckDB. Zero infra, fast, good enough.
- **Phase 2+ (live):** PostgreSQL + TimescaleDB for streaming candles + state.

### Common candle model

`(exchange, symbol, timeframe, open_time, open, high, low, close, volume)` —
UTC, exchange-normalized symbol (e.g. `BTC/USDT`). One Parquet dataset per
`exchange/symbol/timeframe`.

---

## Key risks / notes

- **Backtest realism:** model fees (Bybit maker/taker), and avoid lookahead bias
  (a strategy at bar *t* may only use data ≤ *t*). This is the #1 way backtests lie.
- **Strategy/live parity:** the `Strategy` interface must be identical in backtest
  and live, or Phase 3 results won't match Phase 1. Design for this from day one.
- **Data gaps:** exchange candle history has holes/limits; the adapter must page
  and validate continuity.

See `.claude/plans/phase-1-backtester.md` for the concrete first build.
