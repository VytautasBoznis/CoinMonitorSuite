# CoinMonitorSuite

Greenfield crypto backtesting + (later) automated trading on **Bybit** candles, quoted in
**USDC** (never USDT). Pure-Python engine; FastAPI + React come in later phases.

The backtest engine is a **black-box exchange**: a strategy talks only to a point-in-time
data feed (bars one at a time) plus an order API — the same contract a live adapter
implements — so going live later means swapping the simulator for the real Bybit adapter
with the strategy unchanged. See [.claude/plans/phase-1-backtester.md](.claude/plans/phase-1-backtester.md)
and [PROJECT_BRIEF.md](PROJECT_BRIEF.md).

**Docs:** [PROJECT_BRIEF.md](PROJECT_BRIEF.md) (what & why) · [docs/strategies.md](docs/strategies.md)
(signal layer) · [docs/lessons-learned.md](docs/lessons-learned.md) (findings from running the
rig) · [LEARNING.md](LEARNING.md) (study roadmap).

## Status

Phase 1 (backtester) + Phase 1.5 (fragility harness) — **built and runnable**. `coinmon
backtest` loads candles from TimescaleDB, replays a strategy vs a buy-and-hold benchmark, and
reports trade-level metrics; an optional stop-loss overlay (`--stop-loss`) and Monte Carlo
fragility kill-filter (`--stress`) layer on top. What the runs have shown so far —
including why no strategy beats buy-and-hold yet — is written up in
[docs/lessons-learned.md](docs/lessons-learned.md).

> Note: the **Layout** and **CLI** sections below are partly stale (they still mention the
> retired Parquet store / `fetch-data`); candles now come from the scraper's TimescaleDB.

## Layout

```
src/coinmon/
  config.py            # settings (exchange, USDC quote, fees, data dir)
  data/
    models.py          # Candle schema / common column contract
    store.py           # Parquet read/write per exchange/symbol/timeframe
    ratio.py           # synthetic coin/coin ratio from two USDC legs (ETH/BTC = ETH-USDC / BTC-USDC)
    adapters/          # ExchangeAdapter ABC + Bybit impl (ccxt)
  indicators/          # ema(), rsi() — pure functions
  strategies/          # Strategy ABC + EMACrossover, RSIMeanReversion
  backtest/            # engine, portfolio, execution, metrics, result, stress (Phase 1.5)
  cli.py               # `coinmon fetch-data` / `coinmon backtest`
tests/
```

## Setup

Requires **Python 3.12+**. The project is `uv`-managed (a plain `pip` venv also works).

```bash
uv sync --extra dev          # or: python -m venv .venv && pip install -e ".[dev]"
uv run ruff check .
uv run pytest
```

## CLI (once implemented)

```bash
coinmon fetch-data --symbol BTC/USDC --timeframe 1h --days 90
coinmon backtest  --strategy ema_crossover --symbol BTC/USDC --timeframe 1h
coinmon backtest  --strategy rsi_meanreversion --symbol ETH/BTC --timeframe 1h   # synthetic ratio
```
