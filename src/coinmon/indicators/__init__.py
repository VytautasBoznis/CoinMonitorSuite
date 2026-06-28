from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential moving average (recursive, ``adjust=False``).

    Seeds on the first value and updates ``ema[i] = a*x[i] + (1-a)*ema[i-1]`` with
    ``a = 2/(period+1)`` — the streaming form a live feed can update one bar at a time.
    """
    if period < 1:
        raise ValueError("period must be >= 1")
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index with Wilder smoothing.

    The first ``period`` averages seed on the simple mean of the opening ``period`` price
    changes (Wilder's method, as used by most charting tools); thereafter the averages are
    smoothed recursively. The first ``period`` outputs are NaN (insufficient history).
    A flat-or-rising window (no losses) yields RSI = 100.
    """
    if period < 1:
        raise ValueError("period must be >= 1")
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = _wilder_smooth(gain, period)
    avg_loss = _wilder_smooth(loss, period)
    rs = avg_gain / avg_loss
    out = 100.0 - 100.0 / (1.0 + rs)
    out[avg_loss == 0.0] = 100.0  # no losses over the window → RSI 100
    return out


def atr(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> pd.Series:
    """Average True Range with Wilder smoothing.

    True range is ``max(high-low, |high-prev_close|, |low-prev_close|)``; the first bar has no
    prior close so its TR is NaN (warmup), and the first ``period`` outputs are NaN — the same
    leading-NaN convention as ``rsi``. A volatility measure in price units, used for the ATR
    channel's no-trade band.
    """
    if period < 1:
        raise ValueError("period must be >= 1")
    prev_close = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    true_range.iloc[0] = np.nan  # no prior close for the first bar
    return _wilder_smooth(true_range, period)


def _wilder_smooth(values: pd.Series, period: int) -> pd.Series:
    """Wilder's smoothed average: SMA seed over the first ``period`` values, then recursive.

    ``values`` is expected to carry a leading NaN (it comes from ``Series.diff()``), so the
    seed averages positions ``1..period`` and lands at position ``period``.
    """
    arr = values.to_numpy(dtype="float64")
    n = len(arr)
    out = np.full(n, np.nan)
    if n <= period:
        return pd.Series(out, index=values.index)
    prev = arr[1 : period + 1].mean()
    out[period] = prev
    for i in range(period + 1, n):
        prev = (prev * (period - 1) + arr[i]) / period
        out[i] = prev
    return pd.Series(out, index=values.index)
