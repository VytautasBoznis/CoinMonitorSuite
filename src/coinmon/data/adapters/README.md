# Adding an exchange adapter

This is a self-contained spec for bootstrapping a new venue. Implement the
`ExchangeAdapter` contract in [base.py](base.py) and **nothing downstream changes** —
the scraper, DB layer, and backtester all talk to candles through this seam.
[bybit.py](bybit.py) is the worked reference; copy its structure.

## The contract

Subclass `ExchangeAdapter` and set `name` (short id, e.g. `"binance"`, stored on every
candle). Implement three methods; `fetch_ohlcv` is provided for free by the base class
(it pages over `fetch_raw`).

| Method | Input | Output | Must guarantee |
|--------|-------|--------|----------------|
| `market_symbol(symbol)` | common `BASE/QUOTE` (e.g. `"BTC/USDC"`) | the exchange's native symbol | the **only** place symbols are remapped |
| `fetch_raw(symbol, timeframe, since, until)` | common symbol, tf, epoch-ms bounds | `RawBatch` | one page, oldest-first, payload **untouched** |
| `to_candles(raw)` | a `RawBatch` | DataFrame | exactly `CANDLE_COLUMNS`, closed bars, contiguous |

### Invariants (these are load-bearing — backtest honesty depends on them)

- **`to_candles` returns exactly `CANDLE_COLUMNS`** (`open_time, open, high, low, close,
  volume`) from [models.py](../models.py). `open_time` = the bar's **open** timestamp in
  **epoch milliseconds, UTC**, dtype `int64`; OHLCV are `float64`.
- **Oldest-first, strictly monotonic, no gaps.** Sort, drop duplicate `open_time`, then
  call `validate_continuity(df, timeframe)` (in `base.py`) — it raises on any gap or dupe.
- **Closed bars only.** Drop the in-progress bar: keep rows where
  `open_time + timeframe_to_ms(tf) <= raw.fetched_at`. Re-polling corrects nothing silently.
- **`fetch_raw` stores the payload verbatim.** `RawBatch.rows` is archived to `raw_candles`
  as-is for provenance/replay — do not normalize, filter, or reorder it before returning.
- **One page per `fetch_raw` call.** Return up to the venue's max rows from `since`; the
  base `fetch_ohlcv` and the scraper both advance the cursor and call again.

## Hard project constraints

- **Quote currency is USDC, never USDT** (EU/MiCA — USDT must never be reintroduced).
  Default series are `*/USDC`.
- Symbols travel through the system in the common `BASE/QUOTE` form. Native quirks
  (Bybit category, Binance `BTCUSDC`, etc.) stay hidden inside `market_symbol`.

## Checklist

1. Add `src/coinmon/data/adapters/<venue>.py` with the subclass (see `bybit.py`).
2. Implement `market_symbol`, `fetch_raw`, `to_candles`; reuse `timeframe_to_ms` and
   `validate_continuity` from `base.py`.
3. Wire it where the adapter is selected (currently `BybitAdapter()` in
   [../../scraper/service.py](../../scraper/service.py) — make it config-driven if you add a
   second venue).
4. **Copy the normalization unit test** (`tests/test_scraper.py::test_to_candles_*`): feed a
   sample raw payload, assert columns/dtypes, monotonic UTC ms, and that the in-progress bar
   is dropped. No network.
5. Live smoke test (gated/skippable): `fetch_ohlcv("BTC/USDC", "1h", since=...)` returns a
   sane row count with no gaps.

**Definition of done for an adapter:** the normalization test passes offline, a live fetch
returns contiguous closed candles, and the scraper ingests it with **zero** changes to
`db.py` / `service.py` / `schema.sql`.
