import math

import pandas as pd
import pytest

from coinmon.backtest import walkforward
from coinmon.backtest.walkforward import walk_forward


def _oscillating_candles(n):
    # A saw-tooth close so a short-period RSI actually crosses oversold/exit and trades,
    # making the stitched-return invariant non-trivial rather than all-flat.
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


def test_walk_forward_rejects_too_short_series():
    with pytest.raises(ValueError):
        walk_forward(_oscillating_candles(6), taker_fee=0.0, train_bars=5, test_bars=3)


def test_walk_forward_folds_are_contiguous_and_back_to_back():
    candles = _oscillating_candles(14)
    result = walk_forward(candles, taker_fee=0.0, train_bars=5, test_bars=3)

    # s = 5, 8, 11 -> three folds; test segments [5:8], [8:11], [11:14] are back-to-back.
    assert len(result.folds) == 3
    starts = [f.test_start for f in result.folds]
    assert starts == [5, 8, 11]
    for f in result.folds:
        assert f.test_end == f.test_start + 2  # test_bars=3 -> last open_time is start+2


def test_walk_forward_stitches_oos_by_compounding(monkeypatch):
    # A tiny low-period grid so RSI warms up inside short windows and produces real trades.
    monkeypatch.setattr(
        walkforward, "RSI_GRID", {"period": [2], "oversold": [40.0], "exit_level": [60.0]}
    )
    candles = _oscillating_candles(14)
    result = walk_forward(candles, taker_fee=0.0, train_bars=5, test_bars=3)

    expected_oos = math.prod(1.0 + f.oos_return for f in result.folds) - 1.0
    expected_bh = math.prod(1.0 + f.bh_return for f in result.folds) - 1.0
    assert result.oos_return == pytest.approx(expected_oos)
    assert result.bh_return == pytest.approx(expected_bh)
    # Single grid point -> every fold must select it.
    assert {f.params for f in result.folds} == {(2.0, 40.0, 60.0)}
