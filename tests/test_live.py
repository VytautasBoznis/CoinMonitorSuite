import math

import pandas as pd
import pytest

from coinmon.backtest.engine import BacktestEngine
from coinmon.backtest.portfolio import SpotPortfolio
from coinmon.feed import BarView
from coinmon.live.feed import LiveFeed, frame_to_candles
from coinmon.live.runner import ForwardRunner
from coinmon.strategies.base import Strategy
from coinmon.strategies.rsi_meanreversion import RSIMeanReversion


class _Scripted(Strategy):
    """Replays a fixed list of targets, one per bar (mirrors test_backtest's helper)."""

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


def _sine_candles(n):
    # A sharply oscillating close series so RSIMeanReversion(period=5) actually round-trips
    # (RSI crosses oversold/exit), not just stays flat — otherwise parity is vacuous.
    closes = [100.0 + 30.0 * math.sin(i / 2.0) for i in range(n)]
    rows = [(closes[i], closes[i]) for i in range(n)]
    return _candles(rows)


def test_forward_replay_matches_backtest_scripted():
    candles = _candles([(10, 10), (10, 12), (12, 9), (9, 11), (11, 11), (11, 14)])
    targets = [1, 0, 1, 0, 0, 1]

    pf_bt = SpotPortfolio(100.0, 0.01)
    bt = BacktestEngine(_Scripted(targets), pf_bt).run(candles)

    pf_fwd = SpotPortfolio(100.0, 0.01)
    runner = ForwardRunner(_Scripted(targets), pf_fwd)
    sigs = runner.feed(frame_to_candles(candles))

    assert [s.equity for s in sigs] == pytest.approx(list(bt.equity_curve.to_numpy()))
    assert pf_fwd.trades == pytest.approx(pf_bt.trades)


def test_forward_replay_matches_backtest_real_strategy():
    candles = _sine_candles(120)

    pf_bt = SpotPortfolio(100.0, 0.001)
    bt = BacktestEngine(RSIMeanReversion(period=5), pf_bt).run(candles)

    pf_fwd = SpotPortfolio(100.0, 0.001)
    runner = ForwardRunner(RSIMeanReversion(period=5), pf_fwd)
    sigs = runner.feed(frame_to_candles(candles))

    assert len(pf_fwd.trades) > 0  # the series must actually round-trip for this to mean anything
    assert [s.equity for s in sigs] == pytest.approx(list(bt.equity_curve.to_numpy()))
    assert pf_fwd.trades == pytest.approx(pf_bt.trades)


def test_forward_is_batch_invariant():
    # Bars delivered across several polls (incl. an empty poll) must yield the same decisions and
    # equity as a single-shot replay — i.e. strategy/portfolio state persists across polls.
    candles = _sine_candles(60)
    cs = frame_to_candles(candles)

    one_shot = ForwardRunner(RSIMeanReversion(period=5), SpotPortfolio(100.0, 0.001))
    a = one_shot.feed(cs)

    batched = ForwardRunner(RSIMeanReversion(period=5), SpotPortfolio(100.0, 0.001))
    b = batched.feed(cs[:20]) + batched.feed([]) + batched.feed(cs[20:37]) + batched.feed(cs[37:])

    assert [s.target for s in a] == [s.target for s in b]
    assert [s.equity for s in a] == pytest.approx([s.equity for s in b])


def test_livefeed_returns_only_new_bars():
    store = {"BTC/USDC": _candles([(10, 10), (10, 11)])}
    feed = LiveFeed(lambda s: store[s], "BTC/USDC")

    assert [c.open_time for c in feed.poll()] == [0, 1]
    assert feed.poll() == []  # nothing new closed yet

    store["BTC/USDC"] = _candles([(10, 10), (10, 11), (11, 13)])  # scraper appended a bar
    new = feed.poll()
    assert [c.open_time for c in new] == [2]
    assert feed.last_open_time == 2


def test_livefeed_resolves_synthetic_ratio():
    legs = {"ETH/USDC": _candles([(200.0, 220.0)]), "BTC/USDC": _candles([(100.0, 110.0)])}
    feed = LiveFeed(lambda s: legs[s], "ETH/BTC")
    candles = feed.poll()
    assert candles[0].close == pytest.approx(2.0)  # 220 / 110


def test_latest_is_none_before_any_bar():
    runner = ForwardRunner(_Scripted([]), SpotPortfolio(100.0, 0.0))
    assert runner.latest is None
