import pandas as pd
import pytest

from coinmon.backtest.engine import BacktestEngine, BarStepper
from coinmon.backtest.portfolio import PerpPortfolio, SpotPortfolio
from coinmon.data.models import Candle
from coinmon.feed import BarView
from coinmon.strategies.base import Strategy


class _AlwaysLong(Strategy):
    def on_bar(self, view: BarView) -> int:
        return 1


class _Scripted(Strategy):
    def __init__(self, targets):
        self._targets = list(targets)
        self._i = -1

    def on_bar(self, view: BarView) -> int:
        self._i += 1
        return self._targets[self._i]


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


def test_ledger_records_a_long_round_trip_with_times_and_return():
    # enter long at bar 1's open (10), exit at bar 2's open (11) -> +10% net, direction long.
    candles = _candles([(10, 10), (10, 11), (11, 11), (11, 11)])
    result = BacktestEngine(_Scripted([1, 0, 0, 0]), SpotPortfolio(10_000, 0.0)).run(candles)
    assert len(result.trades) == 1
    t = result.trades[0]
    assert (t.entry_time, t.exit_time, t.direction) == (1, 2, 1)
    assert t.net_return_pct == pytest.approx(0.10)


def test_ledger_count_matches_metrics_trades():
    # three full round trips; an open position at the end is not counted.
    candles = _candles([(10, 10), (10, 11), (11, 12), (12, 12), (12, 13), (13, 13)])
    result = BacktestEngine(_Scripted([1, 0, 1, 0, 1, 1]), SpotPortfolio(10_000, 0.0)).run(candles)
    assert len(result.trades) == int(result.metrics["trades"])
    assert len(result.trades) == 2  # third entry stays open at the end


def test_ledger_open_position_at_end_is_not_a_trade():
    candles = _candles([(10, 11), (11, 12), (12, 13)])
    result = BacktestEngine(_AlwaysLong(), SpotPortfolio(10_000, 0.0)).run(candles)
    assert result.trades == []
    assert result.metrics["trades"] == 0


def test_ledger_marks_a_short_trade_direction_and_profit_on_a_drop():
    # short at bar 1's open (100), cover at bar 2's open (90) -> +10% on a 1x perp, direction short.
    candles = _candles([(100, 100), (100, 90), (90, 90), (90, 90)])
    result = BacktestEngine(
        _Scripted([-1, 0, 0, 0]), PerpPortfolio(10_000, 0.0, leverage=1.0)
    ).run(candles)
    assert len(result.trades) == 1
    t = result.trades[0]
    assert (t.entry_time, t.exit_time, t.direction) == (1, 2, -1)
    assert t.net_return_pct == pytest.approx(0.10)  # shorted the drop


def test_ledger_return_matches_portfolio_pnl_fraction():
    candles = _candles([(10, 10), (10, 11), (11, 11), (11, 11)])
    portfolio = SpotPortfolio(10_000, 0.001)
    result = BacktestEngine(_Scripted([1, 0, 0, 0]), portfolio).run(candles)
    # ledger return fraction == the portfolio's realized PnL / entry collateral.
    assert result.trades[0].net_return_pct == pytest.approx(portfolio.trades[0] / 10_000)


def test_stop_out_produces_a_ledger_record():
    # long entered at 10; bar 2 low 8 pierces a 10% stop (level 9) -> forced flat mid-bar = a trade.
    candles = _candles([(10, 10), (10, 10), (10, 8), (8, 8)])
    stepper = BarStepper(_Scripted([1, 1, 1, 1]), SpotPortfolio(10_000, 0.0), stop_pct=0.10)
    for row in candles.itertuples(index=False):
        stepper.step(
            Candle(int(row.open_time), row.open, row.high, row.low, row.close, row.volume)
        )
    assert len(stepper.trades) == 1
    assert stepper.trades[0].direction == 1
    assert stepper.trades[0].net_return_pct == pytest.approx(-0.10)  # stopped at the 9 level
