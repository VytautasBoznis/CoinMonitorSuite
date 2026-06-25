# Strategy engine — indicators, synthetic ratios & the bar-view contract

The signal layer that sits between stored candles and the (still-to-build) backtest engine:
pure-function indicators, the synthetic coin/coin ratio builder, the point-in-time
`BarView`/`CostModel` contract a strategy talks to, and two example strategies. This is
build steps 3–5; the engine that replays bars through it is step 6 (not built yet).

---

## What's built

```
candles ─► (ratio.build_ratio: two USDC legs ─► synthetic ETH/BTC) ─┐
                                                                     ▼
        engine (step 6) ─► BarView{candle, features} ─► Strategy.on_bar ─► target (0/1)
                                │                              │
                                │                       indicators (feature absent)
                                └─ CostModel ──────────────► no-trade band
```

| Piece | File | Role |
|-------|------|------|
| Indicators | [src/coinmon/indicators/__init__.py](../src/coinmon/indicators/__init__.py) | `ema` (recursive, `adjust=False`) and `rsi` (Wilder smoothing). Pure functions over a `pd.Series`. |
| Synthetic ratio | [src/coinmon/data/ratio.py](../src/coinmon/data/ratio.py) | `build_ratio(base_leg, quote_leg)` → coin/coin OHLCV frame from two USDC legs (e.g. ETH/BTC). |
| Feed contract | [src/coinmon/feed.py](../src/coinmon/feed.py) | `BarView` (current candle + point-in-time feature map) and `CostModel` (taker fee schedule the strategy decides on). |
| Strategy ABC | [src/coinmon/strategies/base.py](../src/coinmon/strategies/base.py) | `on_bar(view) -> int`: +1 long / 0 flat. Same class runs backtest & live. |
| EMA crossover | [src/coinmon/strategies/ema_crossover.py](../src/coinmon/strategies/ema_crossover.py) | Long when fast EMA leads slow, with a cost-band on the relative spread. |
| RSI mean-reversion | [src/coinmon/strategies/rsi_meanreversion.py](../src/coinmon/strategies/rsi_meanreversion.py) | Long when oversold, flat once recovered (hysteresis band). |
| Tests | [tests/test_indicators.py](../tests/test_indicators.py), [tests/test_ratio.py](../tests/test_ratio.py), [tests/test_strategies.py](../tests/test_strategies.py) | Hand-computed indicator values, ratio contract/alignment, no-lookahead + churn + feature-bypass. Offline. |

**Config** ([config.py](../src/coinmon/config.py)): `taker_fee` / `maker_fee` feed `CostModel`.

## How to run

```bash
# Offline, no DB/network:
pytest -q          # indicators, ratio, strategies
ruff check .
```

---

## Lessons learned / key decisions

- **EMA is the recursive `adjust=False` form, seeded on the first value.** `ema[i] = a*x[i] +
  (1-a)*ema[i-1]`, `a = 2/(period+1)`. That's the *streaming* shape a live feed updates one
  closed bar at a time — same math in backtest and live, no warmup NaN.

- **RSI uses canonical Wilder smoothing (SMA seed, then recursive).** The first `period`
  averages seed on the simple mean of the opening `period` deltas — what charting tools show
  — so a ported strategy's RSI matches what a human sees. First `period` outputs are NaN; a
  no-loss window returns 100. (A plain `ewm` would seed differently and silently disagree.)

- **Indicators are pure functions recomputed on the strategy's buffer each bar — settled the
  open sub-decision** (pure-fn-on-buffer vs O(1) stateful classes). It reuses the tested
  functions, ~2k bars is trivial, and it's exactly the cost the future indicator engine
  optimizes away by precomputing into `BarView.features`. O(n)/bar, revisit only if it bites.

- **Synthetic ratio: inner-join, and OHLC bound the *true* extremes.** Legs join on
  `open_time` so only bars present in both survive (no NaN rows). `high = base.high /
  quote.low` and `low = base.low / quote.high` — the ratio peaks when the numerator is high
  and the denominator low — **not** the naïve `high/high`. Volume is the **min** of the two
  legs: a rotation can only move as much size as the thinner leg supports (raw volumes aren't
  additive across a ratio).

- **`BarView` is a cache, not a new contract — this is the load-bearing decision.** A strategy
  reads a precomputed indicator (`ema_<period>`, `rsi_<period>`) when the feed supplies it,
  else computes from its own buffer. So it works identically with or without a future
  indicator engine, and backtest/live parity holds. Because the feed only ever carries values
  derived from bars ≤ now, **no-lookahead stays structural** even with precomputed features.
  See the `feature-store-seam` memory for the full rationale + why the engine is deferred.

- **Decision vs accounting are separate.** The strategy decides using `CostModel`
  (`round_trip_cost` = 2× taker, both rotation legs) — *estimable-at-now* cost. The portfolio
  (step 6) charges the *realized* cost after the fill. Realized cost must never feed the
  decision; that would be lookahead.

- **The no-trade band lives where the signal is continuous.** EMACrossover applies a real
  cost-band: it only switches when `(fast-slow)/close` clears the round-trip cost, so noise
  near the crossover can't churn fees. RSIMeanReversion's oversold→exit hysteresis (30→50)
  *is* its band — structural in RSI space — so **no `CostModel` is injected there** (a price-
  cost band would be redundant). Deliberate deviation from "inject into each example"; revisit
  if the GA wants uniform cost-hurdles.

- **No-lookahead is tested, not just asserted.** The guard test runs a fresh strategy on the
  prefix `[0..t]` and checks the last target equals the full-run target at `t` — proving the
  decision at `t` can't depend on future bars.

## Known limitations / follow-ups

- **Step 6 is built** — `BacktestEngine.run` (next-open fills, no-lookahead), `SpotPortfolio`
  (two-taker-fee round trip), `metrics.summarize` and `result.summary` are implemented, and
  `coinmon backtest` wires strategy + buy-and-hold benchmark through the same engine, loading
  candles from **TimescaleDB** via `db.read_candles` (where the scraper stores them; the
  Parquet `store.py` path is retired). A real run just needs the scraper stack up to populate
  the DB. The engine is covered offline in [tests/test_backtest.py](../tests/test_backtest.py).
- **`BarView.features` is never populated yet** — no indicator engine exists, so Phase 1
  always takes the recompute path. The feature path is exercised only by a unit test.
- **RSI is not cost-aware** (see above) — fine for now, flagged for the GA phase.
- **Indicator recompute is O(n)/bar.** Acceptable at Phase 1 scale; the feature store is the
  intended fix when it matters.
