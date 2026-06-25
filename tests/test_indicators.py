import math

import pandas as pd
import pytest

from coinmon.indicators import ema, rsi


def test_ema_known_values():
    # period=3 -> alpha = 2/4 = 0.5, adjust=False, seeds on the first value.
    out = ema(pd.Series([1.0, 2.0, 3.0, 4.0, 5.0]), period=3)
    assert out.tolist() == pytest.approx([1.0, 1.5, 2.25, 3.125, 4.0625])


def test_rsi_wilder_known_values():
    # period=3 on [10, 11, 10, 12, 13, 12]:
    #   deltas  -> +1, -1, +2, +1, -1
    #   seed @ idx3: avg_gain = (1+0+2)/3 = 1.0, avg_loss = (0+1+0)/3 = 1/3 -> RS=3 -> 75.0
    out = rsi(pd.Series([10.0, 11.0, 10.0, 12.0, 13.0, 12.0]), period=3)
    assert [math.isnan(v) for v in out[:3]] == [True, True, True]
    assert out.iloc[3] == pytest.approx(75.0)
    assert out.iloc[4] == pytest.approx(81.818181, abs=1e-4)
    assert out.iloc[5] == pytest.approx(58.064516, abs=1e-4)


def test_rsi_all_gains_is_100():
    out = rsi(pd.Series([1.0, 2.0, 3.0, 4.0, 5.0]), period=3)
    assert out.iloc[-1] == pytest.approx(100.0)


def test_period_must_be_positive():
    with pytest.raises(ValueError):
        ema(pd.Series([1.0, 2.0]), period=0)
    with pytest.raises(ValueError):
        rsi(pd.Series([1.0, 2.0]), period=0)
