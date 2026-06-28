import pytest

from coinmon.data.models import Candle
from coinmon.feed import BarView, CostModel
from coinmon.strategies.atr_channel import ATRChannelBreakout
from coinmon.strategies.base import Strategy
from coinmon.strategies.ema_crossover import EMACrossover
from coinmon.strategies.rsi_meanreversion import RSIMeanReversion
from coinmon.strategies.stop_loss import StopLoss

ZERO_COST = CostModel(taker_fee=0.0)


def _views(closes, features_seq=None):
    out = []
    for i, c in enumerate(closes):
        feats = features_seq[i] if features_seq is not None else {}
        candle = Candle(open_time=i, open=c, high=c, low=c, close=c, volume=1.0)
        out.append(BarView(candle=candle, features=feats))
    return out


def _run(strategy, views):
    return [strategy.on_bar(v) for v in views]


def test_ema_goes_long_on_uptrend_and_flat_on_downtrend():
    closes = [10.0] * 5 + [float(p) for p in range(11, 40)] + [float(p) for p in range(39, 10, -1)]
    targets = _run(EMACrossover(ZERO_COST, fast=3, slow=8), _views(closes))
    assert 1 in targets  # entered long during the rally
    assert targets[-1] == 0  # exited flat by the end of the decline


def test_ema_cost_band_suppresses_churn():
    # Tiny oscillations around a flat level: the EMA spread never clears the round-trip
    # cost, so a banded strategy must stay flat the whole way.
    closes = [100.0 + (0.05 if i % 2 else -0.05) for i in range(60)]
    views = _views(closes)
    banded = EMACrossover(CostModel(taker_fee=0.001), fast=3, slow=8)  # band = 0.002 (20 bps)
    assert set(_run(banded, views)) == {0}
    # With zero cost the same wiggles do flip the target at least once (band is what helps).
    assert set(_run(EMACrossover(ZERO_COST, fast=3, slow=8), _views(closes))) != {0}


def test_rsi_enters_oversold_exits_on_recovery():
    closes = [float(p) for p in range(40, 20, -1)] + [float(p) for p in range(21, 45)]
    targets = _run(RSIMeanReversion(period=5, oversold=30.0, exit_level=50.0), _views(closes))
    assert 1 in targets  # bought the dip
    assert targets[-1] == 0  # released after recovery


def test_no_lookahead_a_target_depends_only_on_past():
    # The decision at bar t must be identical whether or not future bars exist: running a
    # fresh strategy on the prefix [0..t] reproduces the full-run target at t.
    closes = [float(p) for p in range(40, 20, -1)] + [float(p) for p in range(21, 45)]
    full = _run(RSIMeanReversion(period=5), _views(closes))
    for t in (10, 20, 30, len(closes) - 1):
        prefix = _run(RSIMeanReversion(period=5), _views(closes[: t + 1]))
        assert prefix[-1] == full[t]


def _ohlc_views(rows):
    # rows: (high, low, close); open unused by the channel strategy.
    return [
        BarView(candle=Candle(open_time=i, open=c, high=h, low=lo, close=c, volume=1.0))
        for i, (h, lo, c) in enumerate(rows)
    ]


def test_atr_channel_enters_breakout_exits_breakdown():
    # Tight consolidation around 100 (no breakout), then a sharp rally above the upper band,
    # then a collapse below the lower band.
    consol = [(101.0, 99.0, 100.0 + (0.5 if i % 2 else -0.5)) for i in range(16)]
    rally = [(c + 1.0, c - 1.0, float(c)) for c in (108, 116, 126, 138, 150)]
    crash = [(c + 1.0, c - 1.0, float(c)) for c in (130, 100, 70, 50, 40)]
    targets = _run(ATRChannelBreakout(period=5, mult=1.5), _ohlc_views(consol + rally + crash))
    assert set(targets[:16]) == {0}  # stayed flat through the consolidation
    assert 1 in targets  # entered on the breakout
    assert targets[-1] == 0  # released after the breakdown


def test_atr_channel_precomputed_features_bypass_internal_compute():
    # Feed supplies ema/atr features: the channel is mid +/- 1.5*atr = 100 +/- 3, so a close
    # above 103 enters long without any internal recompute.
    closes = [100.0, 105.0, 110.0]
    feats = [{"ema_5": 100.0, "atr_5": 2.0} for _ in closes]
    targets = _run(ATRChannelBreakout(period=5, mult=1.5), _views(closes, feats))
    assert targets == [0, 1, 1]


class _ScriptedInner(Strategy):
    """Inner strategy that replays fixed targets and counts how often it's consulted."""

    def __init__(self, targets):
        self.targets = list(targets)
        self.i = -1
        self.calls = 0

    def on_bar(self, view):
        self.i += 1
        self.calls += 1
        return self.targets[self.i]


def _bar(close, low=None):
    low = close if low is None else low
    candle = Candle(open_time=0, open=close, high=close, low=low, close=close, volume=1.0)
    return BarView(candle=candle)


def test_stop_loss_exits_when_low_breaches_threshold():
    sl = StopLoss(_ScriptedInner([1, 1, 1]), stop_pct=0.05)  # entry 100 -> stop at 95
    assert sl.on_bar(_bar(100.0)) == 1  # enter long
    assert sl.on_bar(_bar(98.0, low=96.0)) == 1  # low 96 > 95, hold
    assert sl.on_bar(_bar(97.0, low=94.0)) == 0  # low 94 <= 95, stopped out


def test_stop_loss_does_not_self_trigger_on_entry_bar():
    # The entry bar's own low (already past) must not stop the position it just opened.
    sl = StopLoss(_ScriptedInner([1, 1]), stop_pct=0.05)
    assert sl.on_bar(_bar(100.0, low=80.0)) == 1  # enters despite a low far below the stop
    assert sl.on_bar(_bar(100.0, low=100.0)) == 1  # still long next bar


def test_stop_loss_suppresses_reentry_until_inner_resets():
    inner = _ScriptedInner([1, 1, 1, 0, 1])  # keeps wanting long across the stop, then resets
    sl = StopLoss(inner, stop_pct=0.05)
    assert sl.on_bar(_bar(100.0)) == 1  # enter
    assert sl.on_bar(_bar(97.0, low=94.0)) == 0  # stop out
    assert sl.on_bar(_bar(97.0)) == 0  # inner still long -> suppressed
    assert sl.on_bar(_bar(97.0)) == 0  # inner flat -> resets the suppression
    assert sl.on_bar(_bar(97.0)) == 1  # inner long again -> fresh entry allowed


def test_stop_loss_passes_through_inner_exit():
    sl = StopLoss(_ScriptedInner([1, 1, 0]), stop_pct=0.5)
    assert sl.on_bar(_bar(100.0)) == 1
    assert sl.on_bar(_bar(101.0)) == 1
    assert sl.on_bar(_bar(101.0)) == 0  # no breach, but inner went flat


def test_stop_loss_always_feeds_inner():
    inner = _ScriptedInner([1, 1, 1, 1])
    sl = StopLoss(inner, stop_pct=0.05)
    for bar in (_bar(100.0), _bar(97.0, low=94.0), _bar(97.0), _bar(97.0)):
        sl.on_bar(bar)
    assert inner.calls == 4  # consulted every bar, even while overriding its signal


def test_stop_loss_rejects_out_of_range_pct():
    for bad in (0.0, 1.0, -0.1, 1.5):
        with pytest.raises(ValueError):
            StopLoss(_ScriptedInner([0]), stop_pct=bad)


def test_precomputed_features_bypass_internal_compute():
    # A feed that supplies ema features drives the same decision as internal computation;
    # here the features are crafted so fast leads slow -> long.
    closes = [100.0, 100.0, 100.0]
    feats = [
        {"ema_3": 100.0, "ema_8": 100.0},
        {"ema_3": 105.0, "ema_8": 100.0},
        {"ema_3": 110.0, "ema_8": 100.0},
    ]
    targets = _run(EMACrossover(ZERO_COST, fast=3, slow=8), _views(closes, feats))
    assert targets[-1] == 1
