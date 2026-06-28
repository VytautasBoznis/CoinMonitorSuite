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


# --- N5a: Tier-1 indicator library (EMA/momentum + volume families) -----------
# Each indicator below ships as a full-series reference function (the canonical math,
# the bit-parity oracle in tests) AND a streaming O(1)/bar class (what strategies and
# the future bounded-genome P will consume) — same contract as ema/rsi/atr above. The
# EMA-derived forms reuse StreamingEMA, so they inherit its proven adjust=False parity;
# the streaming arithmetic is written to match the reference float-for-float.


def dema(series: pd.Series, period: int) -> pd.Series:
    """Double EMA: ``2*EMA - EMA(EMA)`` — an EMA with reduced lag. Never NaN (like ema)."""
    e1 = ema(series, period)
    return 2.0 * e1 - ema(e1, period)


def tema(series: pd.Series, period: int) -> pd.Series:
    """Triple EMA: ``3*e1 - 3*e2 + e3`` (eₖ = ema applied k times). Even less lag than dema."""
    e1 = ema(series, period)
    e2 = ema(e1, period)
    e3 = ema(e2, period)
    return 3.0 * e1 - 3.0 * e2 + e3


def macd(
    series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """MACD: ``(macd_line, signal_line, histogram)``.

    ``macd_line = EMA(fast) - EMA(slow)``; ``signal_line = EMA(macd_line, signal)``;
    ``histogram = macd_line - signal_line``. All three are full-length (EMAs never NaN).
    """
    macd_line = ema(series, fast) - ema(series, slow)
    signal_line = ema(macd_line, signal)
    return macd_line, signal_line, macd_line - signal_line


def trix(series: pd.Series, period: int = 15) -> pd.Series:
    """TRIX: 1-bar percent rate-of-change of a triple-smoothed EMA, ``*100``.

    Triple-EMA the price, then ``100 * (e3[i] - e3[i-1]) / e3[i-1]``. The first bar is NaN
    (no prior). An oscillator around zero that filters price noise via the triple smoothing.
    """
    e3 = ema(ema(ema(series, period), period), period)
    prev = e3.shift(1)
    return 100.0 * (e3 - prev) / prev


def tsi(series: pd.Series, long: int = 25, short: int = 13) -> pd.Series:
    """True Strength Index: ``100 * EMA(EMA(Δ,long),short) / EMA(EMA(|Δ|,long),short)``.

    Δ is the 1-bar price change; the double EMA smooths momentum and its magnitude. The
    first bar is NaN (Δ undefined). A momentum oscillator bounded roughly in [-100, 100].
    """
    delta = series.diff()
    double = ema(ema(delta, long), short)
    abs_double = ema(ema(delta.abs(), long), short)
    return 100.0 * double / abs_double


def elder_ray(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 13
) -> tuple[pd.Series, pd.Series]:
    """Elder Ray: ``(bull_power, bear_power)`` = ``high - EMA(close)``, ``low - EMA(close)``.

    Bull/bear power measure how far the bar's extremes reach above/below the EMA trend.
    Both are full-length (the EMA never NaN).
    """
    trend = ema(close, period)
    return high - trend, low - trend


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-Balance Volume: a running sum that adds the bar's volume on an up-close and
    subtracts it on a down-close (unchanged close adds nothing). Starts at 0; the first
    bar has no prior close so it contributes 0."""
    direction = np.sign(close.diff().to_numpy())
    direction[0] = 0.0  # no prior close (diff is NaN -> sign NaN)
    return pd.Series((direction * volume.to_numpy()).cumsum(), index=close.index)


def ad(
    high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series
) -> pd.Series:
    """Accumulation/Distribution line (Chaikin): running sum of money-flow volume
    ``((close-low) - (high-close)) / (high-low) * volume``. A bar with high==low
    contributes 0 (no range)."""
    rng = high - low
    mfm = ((close - low) - (high - close)) / rng
    mfm = mfm.where(rng != 0, 0.0)
    return (mfm * volume).cumsum()


def pvt(close: pd.Series, volume: pd.Series) -> pd.Series:
    """Price-Volume Trend: running sum of ``volume * (close - prev_close) / prev_close``.
    Starts at 0; the first bar contributes 0 (no prior close)."""
    prev = close.shift(1)
    roc = (close - prev) / prev
    return (volume * roc).fillna(0.0).cumsum()


def force_index(close: pd.Series, volume: pd.Series, period: int = 13) -> pd.Series:
    """Elder's Force Index: ``EMA( (close - prev_close) * volume, period )``. The first
    bar is NaN (no prior close), so the EMA seeds on the second bar."""
    raw = close.diff() * volume
    return ema(raw, period)


class StreamingDEMA:
    """Streaming :func:`dema`, bit-identical via two ``StreamingEMA``\\ s. Never NaN."""

    def __init__(self, period: int) -> None:
        self._e1 = StreamingEMA(period)
        self._e2 = StreamingEMA(period)

    def update(self, x: float) -> float:
        e1 = self._e1.update(x)
        return 2.0 * e1 - self._e2.update(e1)


class StreamingTEMA:
    """Streaming :func:`tema`, bit-identical via three chained ``StreamingEMA``\\ s."""

    def __init__(self, period: int) -> None:
        self._e1 = StreamingEMA(period)
        self._e2 = StreamingEMA(period)
        self._e3 = StreamingEMA(period)

    def update(self, x: float) -> float:
        e1 = self._e1.update(x)
        e2 = self._e2.update(e1)
        e3 = self._e3.update(e2)
        return 3.0 * e1 - 3.0 * e2 + e3


class StreamingMACD:
    """Streaming :func:`macd`. ``update`` returns ``(macd_line, signal_line, histogram)``."""

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9) -> None:
        self._fast = StreamingEMA(fast)
        self._slow = StreamingEMA(slow)
        self._signal = StreamingEMA(signal)

    def update(self, close: float) -> tuple[float, float, float]:
        macd_line = self._fast.update(close) - self._slow.update(close)
        signal_line = self._signal.update(macd_line)
        return macd_line, signal_line, macd_line - signal_line


class StreamingTRIX:
    """Streaming :func:`trix`. Returns NaN on the first bar (no prior triple-EMA value)."""

    def __init__(self, period: int = 15) -> None:
        self._e1 = StreamingEMA(period)
        self._e2 = StreamingEMA(period)
        self._e3 = StreamingEMA(period)
        self._prev: float | None = None

    def update(self, x: float) -> float:
        e3 = self._e3.update(self._e2.update(self._e1.update(x)))
        if self._prev is None:
            self._prev = e3
            return _NAN
        out = 100.0 * (e3 - self._prev) / self._prev
        self._prev = e3
        return out


class StreamingTSI:
    """Streaming :func:`tsi`. Returns NaN on the first bar (Δ undefined)."""

    def __init__(self, long: int = 25, short: int = 13) -> None:
        self._d1 = StreamingEMA(long)
        self._d2 = StreamingEMA(short)
        self._a1 = StreamingEMA(long)
        self._a2 = StreamingEMA(short)
        self._prev_close: float | None = None

    def update(self, close: float) -> float:
        if self._prev_close is None:
            self._prev_close = close
            return _NAN
        delta = close - self._prev_close
        self._prev_close = close
        double = self._d2.update(self._d1.update(delta))
        abs_double = self._a2.update(self._a1.update(abs(delta)))
        if abs_double == 0.0:
            return _NAN
        return 100.0 * double / abs_double


class StreamingElderRay:
    """Streaming :func:`elder_ray`. ``update`` returns ``(bull_power, bear_power)``."""

    def __init__(self, period: int = 13) -> None:
        self._ema = StreamingEMA(period)

    def update(self, high: float, low: float, close: float) -> tuple[float, float]:
        trend = self._ema.update(close)
        return high - trend, low - trend


class StreamingOBV:
    """Streaming :func:`obv`. Starts at 0; the first bar contributes 0 (no prior close)."""

    def __init__(self) -> None:
        self._obv = 0.0
        self._prev_close: float | None = None

    def update(self, close: float, volume: float) -> float:
        if self._prev_close is not None:
            if close > self._prev_close:
                self._obv += volume
            elif close < self._prev_close:
                self._obv -= volume
        self._prev_close = close
        return self._obv


class StreamingAD:
    """Streaming :func:`ad` (Accumulation/Distribution line). A zero-range bar adds 0."""

    def __init__(self) -> None:
        self._ad = 0.0

    def update(self, high: float, low: float, close: float, volume: float) -> float:
        rng = high - low
        mfm = ((close - low) - (high - close)) / rng if rng != 0 else 0.0
        self._ad += mfm * volume
        return self._ad


class StreamingPVT:
    """Streaming :func:`pvt`. Starts at 0; the first bar contributes 0 (no prior close)."""

    def __init__(self) -> None:
        self._pvt = 0.0
        self._prev_close: float | None = None

    def update(self, close: float, volume: float) -> float:
        if self._prev_close is not None:
            roc = (close - self._prev_close) / self._prev_close
            self._pvt += volume * roc
        self._prev_close = close
        return self._pvt


class StreamingForceIndex:
    """Streaming :func:`force_index`. Returns NaN on the first bar (no prior close)."""

    def __init__(self, period: int = 13) -> None:
        self._ema = StreamingEMA(period)
        self._prev_close: float | None = None

    def update(self, close: float, volume: float) -> float:
        if self._prev_close is None:
            self._prev_close = close
            return _NAN
        raw = (close - self._prev_close) * volume
        self._prev_close = close
        return self._ema.update(raw)
