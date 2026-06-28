import math
import statistics

import pandas as pd
import pytest

from coinmon.backtest.fitness import (
    _downside_dev,
    _fold_bounds,
    _robust_center,
    evaluate_fitness,
)
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
    assert r.median_oos_return == pytest.approx(statistics.median(r.fold_returns))
    assert r.mean_oos_return == pytest.approx(statistics.fmean(r.fold_returns))
    assert r.return_std == pytest.approx(statistics.pstdev(r.fold_returns))
    assert r.downside_dev == pytest.approx(_downside_dev(r.fold_returns))
    assert r.instability_penalty == pytest.approx(r.downside_dev)  # weight 1.0
    expected_trade_pen = max(0.0, 1.0 - r.total_trades / 20)
    assert r.trade_penalty == pytest.approx(expected_trade_pen)
    assert r.fitness == pytest.approx(
        r.median_oos_return - r.instability_penalty - r.trade_penalty
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


def test_downside_dev_ignores_upside_but_bites_losses():
    # The chunk-A fix: all-positive folds pay nothing even when they vary a lot in size, while
    # negative folds drive the penalty by their depth. A symmetric std would penalize the first.
    assert _downside_dev([0.1, 0.2, 0.3]) == 0.0
    assert _downside_dev([0.0, 0.0]) == 0.0
    assert _downside_dev([-0.1, -0.1]) == pytest.approx(0.1)
    assert _downside_dev([0.3, -0.2]) == pytest.approx(math.sqrt((0.2**2) / 2))


def test_instability_weight_docks_downside_genomes_more():
    candles = _oscillating_candles(40)
    light = evaluate_fitness(candles, _make_rsi, taker_fee=0.0, folds=4, instability_weight=0.0)
    heavy = evaluate_fitness(candles, _make_rsi, taker_fee=0.0, folds=4, instability_weight=5.0)
    # Same genome/data: only the instability weight differs. If any fold loses money at all, the
    # heavier weight must produce the lower fitness; if every fold is green it must NOT (the fix).
    if heavy.downside_dev > 0:
        assert heavy.fitness < light.fitness
    else:
        assert heavy.fitness == pytest.approx(light.fitness)


def test_robust_center_ignores_a_single_lucky_fold():
    # The live-search overfit: a +355% fold dragged the mean to +94% while the median stays sober.
    assert _robust_center([0.19, -0.35, 0.39, 3.55]) == pytest.approx((0.19 + 0.39) / 2)
    # One extreme fold cannot move the median off the body of the distribution.
    assert _robust_center([0.10, 0.10, 0.10, 100.0]) == pytest.approx(0.10)
    # A genome positive in every fold is rewarded its typical fold, not dampened.
    assert _robust_center([0.20, 0.20, 0.20, 0.20]) == pytest.approx(0.20)


def test_embargo_too_large_for_fold_size_raises():
    with pytest.raises(ValueError):
        evaluate_fitness(
            _oscillating_candles(40), _make_rsi, taker_fee=0.0, folds=4, embargo_bars=10
        )
