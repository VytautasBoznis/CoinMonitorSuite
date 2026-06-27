import statistics

import pandas as pd
import pytest

from coinmon.backtest.fitness import _fold_bounds, evaluate_fitness
from coinmon.strategies.rsi_meanreversion import RSIMeanReversion


def _oscillating_candles(n):
    # Saw-tooth close so a short-period RSI crosses oversold/exit and produces real trades.
    closes = [100.0 + (10.0 if i % 2 else -10.0) for i in range(n)]
    return pd.DataFrame(
        {
            "open_time": range(n),
            "open": closes,
            "high": [c + 1 for c in closes],
            "low": [c - 1 for c in closes],
            "close": closes,
            "volume": [1.0] * n,
        }
    )


def _make_rsi():
    return RSIMeanReversion(period=2, oversold=40.0, exit_level=60.0)


def test_fold_bounds_are_contiguous_then_embargo_carves_the_tail_segments():
    # No embargo: segments tile the series exactly, back-to-back, last one absorbs the remainder.
    assert _fold_bounds(20, 4, 0) == [(0, 5), (5, 10), (10, 15), (15, 20)]
    # Embargo drops bars from the START of every fold after the first.
    assert _fold_bounds(20, 4, 2) == [(0, 5), (7, 10), (12, 15), (17, 20)]


def test_fitness_arithmetic_matches_its_components():
    candles = _oscillating_candles(40)
    r = evaluate_fitness(
        candles, _make_rsi, taker_fee=0.0, folds=4, min_trades=20, instability_weight=1.0
    )

    assert len(r.fold_returns) == 4
    assert r.total_trades == sum(r.fold_trades)
    assert r.mean_oos_return == pytest.approx(statistics.fmean(r.fold_returns))
    assert r.return_std == pytest.approx(statistics.pstdev(r.fold_returns))
    assert r.instability_penalty == pytest.approx(r.return_std)  # weight 1.0
    expected_trade_pen = max(0.0, 1.0 - r.total_trades / 20)
    assert r.trade_penalty == pytest.approx(expected_trade_pen)
    assert r.fitness == pytest.approx(
        r.mean_oos_return - r.instability_penalty - r.trade_penalty
    )


def test_low_trade_count_is_penalized_high_count_is_not():
    candles = _oscillating_candles(40)
    # min_trades far above what this genome produces -> a positive trade penalty.
    penalized = evaluate_fitness(candles, _make_rsi, taker_fee=0.0, folds=4, min_trades=1000)
    assert penalized.trade_penalty > 0.0
    # min_trades at/below the actual count -> no trade penalty.
    satisfied = evaluate_fitness(
        candles, _make_rsi, taker_fee=0.0, folds=4, min_trades=penalized.total_trades
    )
    assert satisfied.trade_penalty == pytest.approx(0.0)


def test_single_fold_has_no_instability_penalty():
    candles = _oscillating_candles(40)
    r = evaluate_fitness(candles, _make_rsi, taker_fee=0.0, folds=1, min_trades=0)
    assert r.return_std == 0.0
    assert r.instability_penalty == 0.0


def test_instability_weight_docks_inconsistent_genomes_more():
    candles = _oscillating_candles(40)
    light = evaluate_fitness(candles, _make_rsi, taker_fee=0.0, folds=4, instability_weight=0.0)
    heavy = evaluate_fitness(candles, _make_rsi, taker_fee=0.0, folds=4, instability_weight=5.0)
    # Same genome/data: only the instability weight differs. If returns vary across folds at
    # all, the heavier weight must produce the lower fitness.
    if heavy.return_std > 0:
        assert heavy.fitness < light.fitness


def test_embargo_too_large_for_fold_size_raises():
    with pytest.raises(ValueError):
        evaluate_fitness(
            _oscillating_candles(40), _make_rsi, taker_fee=0.0, folds=4, embargo_bars=10
        )
