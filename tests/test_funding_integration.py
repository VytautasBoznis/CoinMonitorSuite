"""Chunk W3 step 2c: threading real funding through the search rig — the seam that turns the
funding_carry family from REACHABLE (registered) into SEARCHABLE (scored with real funding).

Covers the three integration points: the engine auto-extracts a ``funding_rate`` column (single
seam, parity vs the explicit arg), ``CandleCache`` attaches funding for direct perps only, and the
fitness fold loop carries the column through its slices so a carry genome actually harvests the
premium during scoring."""

from __future__ import annotations

import pandas as pd
import pytest

from coinmon.backtest.engine import BacktestEngine
from coinmon.backtest.fitness import evaluate_fitness
from coinmon.backtest.portfolio import CarryPortfolio
from coinmon.search.genome import Genome, decode, decode_portfolio, decode_stop
from coinmon.search.runner import CandleCache
from coinmon.strategies.funding_carry import FundingCarry


def _flat_candles(n):
    # Constant price so a CarryPortfolio's equity moves ONLY with funding (price legs cancel) —
    # isolating the funding cashflow this chunk wires in.
    return pd.DataFrame(
        {
            "open_time": list(range(n)),
            "open": [100.0] * n,
            "high": [101.0] * n,
            "low": [99.0] * n,
            "close": [100.0] * n,
            "volume": [1.0] * n,
        }
    )


def _carry_engine():
    # A carry book that hedges the moment it has a 2-bar window (threshold=0 -> positive mean rate).
    return BacktestEngine(FundingCarry(window=2, threshold=0.0), CarryPortfolio(10_000.0, 0.001))


# --- engine auto-extract (the single seam) -------------------------------------------------


def test_engine_extracts_funding_column_bit_identical_to_explicit_arg():
    candles = _flat_candles(10)
    rates = [0.005] * 10
    from_arg = _carry_engine().run(candles, funding=rates)
    from_col = _carry_engine().run(candles.assign(funding_rate=rates))
    assert from_col.equity_curve.tolist() == from_arg.equity_curve.tolist()
    assert from_col.metrics == from_arg.metrics


def test_no_funding_column_leaves_the_run_byte_unchanged():
    candles = _flat_candles(10)
    plain = _carry_engine().run(candles)  # no column, no explicit arg
    zeroed = _carry_engine().run(candles, funding=[0.0] * 10)
    # No funding feature -> the carry strategy never hedges -> flat equity at initial capital.
    assert plain.equity_curve.tolist() == zeroed.equity_curve.tolist()
    assert plain.metrics["trades"] == 0
    assert plain.equity_curve.iloc[-1] == pytest.approx(10_000.0)


def test_funding_column_is_charged_so_carry_harvests_the_premium():
    candles = _flat_candles(10)
    funded = _carry_engine().run(candles.assign(funding_rate=[0.005] * 10))
    flat = _carry_engine().run(candles)  # same bars, no funding feature
    # With funding the hedge turns on and collects the premium each held bar; without it, flat.
    assert funded.equity_curve.iloc[-1] > flat.equity_curve.iloc[-1]
    assert funded.equity_curve.iloc[-1] > 10_000.0  # premium beat the entry fee legs


# --- CandleCache attaches funding for direct perps only ------------------------------------


def test_candle_cache_attaches_funding_for_direct_perp_only():
    frames = _flat_candles(3)

    def read(_symbol):
        return frames.copy()

    def read_funding(_pair):
        return pd.DataFrame({"funding_time": [0, 1, 2], "rate": [0.005, 0.005, 0.005]})

    cache = CandleCache(read, read_funding)
    assert "funding_rate" in cache.get("BTC/USDC").columns  # direct perp -> funding attached
    assert "funding_rate" not in cache.get("ETH/BTC").columns  # ratio -> no funding


def test_candle_cache_without_funding_reader_is_candle_only():
    frames = _flat_candles(3)
    cache = CandleCache(lambda _s: frames.copy())  # no read_funding (existing behavior)
    assert "funding_rate" not in cache.get("BTC/USDC").columns


# --- the fold loop carries the column (searchability end-to-end) ---------------------------


def test_evaluate_fitness_scores_carry_with_funding_from_the_column():
    n = 60
    genome = Genome("funding_carry", "BTC/USDC", {"window": 20, "threshold": 0.0})
    common = dict(
        make_portfolio=decode_portfolio(genome),
        stop_pct=decode_stop(genome),
        folds=1,  # one fold so the 20-bar warmup leaves plenty of bars to harvest funding
        min_trades=0,
    )
    funded = evaluate_fitness(
        _flat_candles(n).assign(funding_rate=[0.005] * n), decode(genome), 0.001, **common
    )
    candle_only = evaluate_fitness(_flat_candles(n), decode(genome), 0.001, **common)
    # Fold slices carry the funding column, so the carry genome earns a positive median OOS return;
    # without funding it is flat (0). This is the un-searchable -> searchable proof.
    assert funded.median_oos_return > candle_only.median_oos_return
    assert candle_only.median_oos_return == pytest.approx(0.0)
