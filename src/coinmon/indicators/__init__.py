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


# --- Streaming O(1)/bar forms -------------------------------------------------
# The functions above recompute the whole series; a strategy that called them every
# bar was O(n^2) (the binding GA constraint since chunk A). The classes below update
# one bar at a time and are BIT-IDENTICAL to the functions' ``.iloc[-1]`` per bar:
# each replicates the exact arithmetic above so a streamed run matches a full recompute
# float-for-float (see test_indicators bit-parity tests). The same object drives backtest
# and live, so live-parity is preserved.

_NAN = float("nan")


class _WilderStream:
    """Streaming counterpart of ``_wilder_smooth``: SMA seed over the first ``period``
    fed values (numpy mean, matching the function), then the recursive update. Callers
    feed it from the first non-NaN input onward, so it warms up after ``period`` updates.
    """

    def __init__(self, period: int) -> None:
        self._period = period
        self._seed: list[float] = []
        self._value: float | None = None

    def update(self, x: float) -> float:
        if self._value is None:
            self._seed.append(x)
            if len(self._seed) < self._period:
                return _NAN
            self._value = float(np.asarray(self._seed, dtype="float64").mean())
            return self._value
        self._value = (self._value * (self._period - 1) + x) / self._period
        return self._value


class StreamingEMA:
    """Streaming ``ema``: ``ewm(span=period, adjust=False).mean()`` one value at a time.

    Replicates pandas' adjust=False recurrence exactly — seed on the first value, then
    ``weighted = old*prev + new*x; weighted /= (old + new)`` with ``old = 1-alpha``,
    ``new = alpha`` — so the streamed series is float-identical. Never NaN (like ``ema``).
    """

    def __init__(self, period: int) -> None:
        if period < 1:
            raise ValueError("period must be >= 1")
        alpha = 2.0 / (period + 1)
        self._old = 1.0 - alpha
        self._new = alpha
        self._value: float | None = None

    def update(self, x: float) -> float:
        if self._value is None:
            self._value = x
        else:
            self._value = self._old * self._value + self._new * x
            self._value /= self._old + self._new
        return self._value


class StreamingRSI:
    """Streaming ``rsi`` with Wilder smoothing. Returns NaN for the first ``period`` bars
    (warmup) and 100.0 over a no-loss window, matching ``rsi``."""

    def __init__(self, period: int = 14) -> None:
        if period < 1:
            raise ValueError("period must be >= 1")
        self._gain = _WilderStream(period)
        self._loss = _WilderStream(period)
        self._prev_close: float | None = None

    def update(self, close: float) -> float:
        if self._prev_close is None:
            self._prev_close = close
            return _NAN  # no prior close -> diff is NaN at bar 0
        delta = close - self._prev_close
        self._prev_close = close
        avg_gain = self._gain.update(max(delta, 0.0))
        avg_loss = self._loss.update(max(-delta, 0.0))
        if avg_gain != avg_gain:  # NaN during warmup
            return _NAN
        if avg_loss == 0.0:
            return 100.0  # no losses over the window
        rs = avg_gain / avg_loss
        return 100.0 - 100.0 / (1.0 + rs)


class StreamingATR:
    """Streaming ``atr`` with Wilder smoothing. The first bar has no prior close so its
    true range is skipped (NaN), and the first ``period`` outputs are NaN, matching ``atr``."""

    def __init__(self, period: int = 14) -> None:
        if period < 1:
            raise ValueError("period must be >= 1")
        self._tr = _WilderStream(period)
        self._prev_close: float | None = None

    def update(self, high: float, low: float, close: float) -> float:
        if self._prev_close is None:
            self._prev_close = close
            return _NAN  # no prior close for the first bar
        true_range = max(
            high - low, abs(high - self._prev_close), abs(low - self._prev_close)
        )
        self._prev_close = close
        return self._tr.update(true_range)
