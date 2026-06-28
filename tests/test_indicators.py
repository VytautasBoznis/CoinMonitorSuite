import math

import pandas as pd
import pytest

from coinmon.indicators import atr, ema, rsi


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


def test_atr_wilder_known_values():
    # TR (first bar NaN: no prior close); prev_close = [-, 9, 11, 10]:
    #   idx1 max(12-9, |12-9|, |9-9|)=3, idx2 max(11-10, |11-11|, |10-11|)=1,
    #   idx3 max(13-11, |13-10|, |11-10|)=3
    # period=2 Wilder: seed @ idx2 = (3+1)/2 = 2.0, idx3 = (2.0*1 + 3)/2 = 2.5
    high = pd.Series([10.0, 12.0, 11.0, 13.0])
    low = pd.Series([8.0, 9.0, 10.0, 11.0])
    close = pd.Series([9.0, 11.0, 10.0, 12.0])
    out = atr(high, low, close, period=2)
    assert [math.isnan(v) for v in out[:2]] == [True, True]
    assert out.iloc[2] == pytest.approx(2.0)
    assert out.iloc[3] == pytest.approx(2.5)


def test_period_must_be_positive():
    with pytest.raises(ValueError):
        ema(pd.Series([1.0, 2.0]), period=0)
    with pytest.raises(ValueError):
        rsi(pd.Series([1.0, 2.0]), period=0)
    with pytest.raises(ValueError):
        atr(pd.Series([1.0]), pd.Series([1.0]), pd.Series([1.0]), period=0)
