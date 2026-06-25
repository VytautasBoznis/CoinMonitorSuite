import numpy as np
import pandas as pd
import pytest

from coinmon.backtest.engine import BacktestEngine
from coinmon.backtest.portfolio import SpotPortfolio
from coinmon.backtest.stress import StochasticExecution, run_monte_carlo
from coinmon.feed import BarView
from coinmon.strategies.base import Strategy


class _AlwaysLong(Strategy):
    def on_bar(self, view: BarView) -> int:
        return 1


def _candles(rows):
    return pd.DataFrame(
        {
            "open_time": range(len(rows)),
            "open": [o for o, _ in rows],
            "high": [max(o, c) for o, c in rows],
            "low": [min(o, c) for o, c in rows],
            "close": [c for _, c in rows],
            "volume": [1.0] * len(rows),
        }
    )


def test_stochastic_fill_is_adverse_by_side():
    ex = StochasticExecution(max_slippage=0.01, fail_prob=0.0, rng=np.random.default_rng(0))
    assert ex.fill_price(1, 100.0) >= 100.0  # a buy fills no better than reference
    assert ex.fill_price(-1, 100.0) <= 100.0  # a sell fills no better than reference


def test_stochastic_fill_can_fail():
    ex = StochasticExecution(max_slippage=0.01, fail_prob=1.0, rng=np.random.default_rng(0))
    assert ex.fill_price(1, 100.0) is None


def test_stochastic_is_seed_reproducible():
    def draws(seed):
        ex = StochasticExecution(0.01, 0.1, np.random.default_rng(seed))
        return [ex.fill_price(1, 100.0) for _ in range(20)]

    assert draws(42) == draws(42)  # same seed -> identical fill sequence
    assert draws(42) != draws(7)  # different seed -> different draws


def test_failed_fills_keep_portfolio_flat():
    # fail_prob=1 -> no order ever lands -> equity never moves off the starting cash, even
    # though the strategy wants to be long the whole time.
    candles = _candles([(10.0, 10.0), (10.0, 20.0), (20.0, 30.0)])
    ex = StochasticExecution(0.0, 1.0, np.random.default_rng(0))
    result = BacktestEngine(_AlwaysLong(), SpotPortfolio(100.0, 0.0), ex).run(candles)
    assert list(result.equity_curve) == pytest.approx([100.0, 100.0, 100.0])


def test_zero_friction_monte_carlo_matches_ideal_run():
    candles = _candles([(10.0, 10.0), (10.0, 20.0), (20.0, 30.0)])
    ideal_result = BacktestEngine(_AlwaysLong(), SpotPortfolio(100.0, 0.0)).run(candles)
    ideal = ideal_result.metrics["total_return"]
    mc = run_monte_carlo(
        lambda: _AlwaysLong(),
        lambda: SpotPortfolio(100.0, 0.0),
        candles,
        runs=5,
        max_slippage=0.0,
        fail_prob=0.0,
    )
    assert mc.runs == 5
    assert all(r == pytest.approx(ideal) for r in mc.returns)  # no friction => identical to ideal


def test_monte_carlo_reports_fragility_fractions():
    candles = _candles([(10.0, 10.0), (10.0, 20.0), (20.0, 30.0)])
    mc = run_monte_carlo(
        lambda: _AlwaysLong(),
        lambda: SpotPortfolio(100.0, 0.001),
        candles,
        runs=30,
        max_slippage=0.005,
        fail_prob=0.05,
        seed=1,
        benchmark_return=0.0,
    )
    assert mc.runs == 30
    assert 0.0 <= mc.fraction_positive <= 1.0
    assert 0.0 <= mc.fraction_beating_benchmark <= 1.0
    assert "% runs beat B&H" in mc.summary()
