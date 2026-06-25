import math

import pandas as pd
import pytest

from coinmon.backtest.engine import BacktestEngine
from coinmon.backtest.metrics import summarize
from coinmon.backtest.portfolio import SpotPortfolio
from coinmon.cli import _load_candles
from coinmon.feed import BarView
from coinmon.strategies.base import Strategy


class _AlwaysLong(Strategy):
    def on_bar(self, view: BarView) -> int:
        return 1


class _Scripted(Strategy):
    """Replays a fixed list of targets, one per bar."""

    def __init__(self, targets):
        self._targets = list(targets)
        self._i = -1

    def on_bar(self, view: BarView) -> int:
        self._i += 1
        return self._targets[self._i]


def _candles(rows):
    # rows: list of (open, close); high/low bound them, volume constant.
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


def test_spot_portfolio_round_trip_pays_two_taker_fees():
    p = SpotPortfolio(cash=100.0, taker_fee=0.01)
    p.rebalance(1, price=10.0)  # buy: 100 * 0.99 / 10 = 9.9 units
    assert p.units == pytest.approx(9.9)
    assert p.equity(10.0) == pytest.approx(99.0)
    p.rebalance(0, price=10.0)  # sell: 9.9 * 10 * 0.99 = 98.01
    assert p.units == 0.0
    assert p.equity(10.0) == pytest.approx(98.01)  # ~2% lost to two 1% fees


def test_rebalance_to_same_target_is_a_noop():
    p = SpotPortfolio(cash=100.0, taker_fee=0.5)
    p.rebalance(1, price=10.0)
    units = p.units
    p.rebalance(1, price=999.0)  # no second fee, no re-trade
    assert p.units == units


def test_closed_round_trip_records_realized_pnl():
    p = SpotPortfolio(cash=100.0, taker_fee=0.0)
    p.rebalance(1, price=10.0)  # buy 10 units
    p.rebalance(0, price=12.0)  # sell at 12 -> 120 cash
    assert p.trades == [pytest.approx(20.0)]  # +20 realized on the round-trip


def test_open_position_is_not_a_closed_trade():
    p = SpotPortfolio(cash=100.0, taker_fee=0.0)
    p.rebalance(1, price=10.0)  # entered, never exited
    assert p.trades == []  # unrealized, so no trade recorded


def test_engine_executes_at_next_bar_open_not_signal_bar_close():
    # Signal fires after bar 0 closes; it must fill at bar 1's OPEN (10), so the close-of-bar-0
    # jump to 20 is NOT captured — only the move from the next open onward is.
    candles = _candles([(10.0, 20.0), (10.0, 30.0)])
    portfolio = SpotPortfolio(cash=100.0, taker_fee=0.0)
    result = BacktestEngine(_AlwaysLong(), portfolio).run(candles)
    # Bought 10 units at open=10 on bar 1, marked at close=30 -> 300.
    assert result.equity_curve.iloc[0] == pytest.approx(100.0)  # bar 0: still flat
    assert result.equity_curve.iloc[-1] == pytest.approx(300.0)


def test_final_bar_signal_never_trades():
    # Flat the whole way, then a long signal on the very last bar: no bar t+1 exists to fill
    # it, so equity stays at the starting cash throughout.
    candles = _candles([(10.0, 10.0), (10.0, 10.0), (10.0, 50.0)])
    portfolio = SpotPortfolio(cash=100.0, taker_fee=0.0)
    result = BacktestEngine(_Scripted([0, 0, 1]), portfolio).run(candles)
    assert list(result.equity_curve) == pytest.approx([100.0, 100.0, 100.0])


def test_engine_rejects_empty_frame():
    with pytest.raises(ValueError):
        BacktestEngine(_AlwaysLong(), SpotPortfolio(100.0, 0.0)).run(_candles([]))


def test_engine_reports_trade_count_and_exposure():
    # Enter long (fills at bar 1's open=10), exit (fills at bar 2's open=15) -> one winning
    # round-trip. Held a position only during bar 1, so exposure = 1/4.
    candles = _candles([(10.0, 10.0), (10.0, 10.0), (15.0, 15.0), (15.0, 15.0)])
    result = BacktestEngine(_Scripted([1, 0, 0, 0]), SpotPortfolio(100.0, 0.0)).run(candles)
    assert result.metrics["trades"] == 1
    assert result.metrics["win_rate"] == pytest.approx(1.0)
    assert result.metrics["exposure"] == pytest.approx(0.25)


def test_buy_and_hold_has_no_closed_trades():
    # Always long never completes a round-trip: 0 trades, n/a win rate, ~full exposure.
    candles = _candles([(10.0, 10.0), (10.0, 20.0), (20.0, 30.0)])
    result = BacktestEngine(_AlwaysLong(), SpotPortfolio(100.0, 0.0)).run(candles)
    assert result.metrics["trades"] == 0
    assert math.isnan(result.metrics["win_rate"])
    assert math.isnan(result.metrics["profit_factor"])
    assert "n/a" in result.summary()  # rendered, not crashed


def test_metrics_curve_fields():
    curve = pd.Series([100.0, 120.0, 90.0, 108.0])
    m = summarize(curve, trades=[], exposure=0.5)
    assert m["total_return"] == pytest.approx(0.08)
    assert m["max_drawdown"] == pytest.approx(90.0 / 120.0 - 1.0)  # -0.25
    assert m["exposure"] == pytest.approx(0.5)


def test_metrics_per_trade_win_rate_and_profit_factor():
    m = summarize(pd.Series([100.0, 110.0]), trades=[30.0, -10.0, 20.0], exposure=1.0)
    assert m["trades"] == 3
    assert m["win_rate"] == pytest.approx(2 / 3)
    assert m["profit_factor"] == pytest.approx(50.0 / 10.0)  # gross 50 won / 10 lost


def test_load_candles_usdc_pair_reads_directly():
    seen = []

    def read(symbol):
        seen.append(symbol)
        return _candles([(10.0, 11.0)])

    _load_candles(read, "BTC/USDC")
    assert seen == ["BTC/USDC"]  # one direct read, no ratio synthesis


def test_load_candles_synthetic_ratio_reads_both_usdc_legs():
    legs = {
        "ETH/USDC": _candles([(200.0, 220.0)]),
        "BTC/USDC": _candles([(100.0, 110.0)]),
    }
    seen = []

    def read(symbol):
        seen.append(symbol)
        return legs[symbol]

    out = _load_candles(read, "ETH/BTC")
    assert seen == ["ETH/USDC", "BTC/USDC"]  # both legs loaded vs USDC
    assert out["close"].iloc[0] == pytest.approx(110.0 / 110.0 * 2.0)  # 220/110 = 2.0
