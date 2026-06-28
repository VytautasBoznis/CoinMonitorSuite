import math

import pandas as pd
import pytest

from coinmon.indicators import (
    StreamingAD,
    StreamingATR,
    StreamingDEMA,
    StreamingElderRay,
    StreamingEMA,
    StreamingForceIndex,
    StreamingMACD,
    StreamingOBV,
    StreamingPVT,
    StreamingRSI,
    StreamingTEMA,
    StreamingTRIX,
    StreamingTSI,
    ad,
    atr,
    dema,
    elder_ray,
    ema,
    force_index,
    macd,
    obv,
    pvt,
    rsi,
    tema,
    trix,
    tsi,
)


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


# --- Streaming bit-parity -----------------------------------------------------
# The streaming O(1)/bar forms must match the full-series recompute float-for-float,
# bar by bar (the N1 perf rewrite preserves the exact numbers, not just close ones).


def _ohlc(n: int) -> tuple[list[float], list[float], list[float]]:
    """A deterministic, jagged price walk (varied gains/losses, no NaNs)."""
    closes, highs, lows = [], [], []
    price = 100.0
    for i in range(n):
        price *= 1.0 + 0.05 * math.sin(i * 1.3) - 0.03 * math.cos(i * 0.7)
        closes.append(price)
        highs.append(price * (1.0 + 0.01 * abs(math.sin(i * 2.1))))
        lows.append(price * (1.0 - 0.01 * abs(math.cos(i * 1.7))))
    return highs, lows, closes


def _assert_bit_equal(streamed: list[float], reference) -> None:
    ref = reference.tolist()
    assert len(streamed) == len(ref)
    for s, r in zip(streamed, ref, strict=True):
        if math.isnan(r):
            assert math.isnan(s)
        else:
            assert s == r  # exact, not approx


@pytest.mark.parametrize("period", [2, 3, 5, 14, 40])
def test_streaming_ema_bit_parity(period):
    _, _, closes = _ohlc(120)
    stream = StreamingEMA(period)
    streamed = [stream.update(c) for c in closes]
    _assert_bit_equal(streamed, ema(pd.Series(closes), period))


@pytest.mark.parametrize("period", [2, 3, 14, 40])
def test_streaming_rsi_bit_parity(period):
    _, _, closes = _ohlc(120)
    stream = StreamingRSI(period)
    streamed = [stream.update(c) for c in closes]
    _assert_bit_equal(streamed, rsi(pd.Series(closes), period))


def test_streaming_rsi_no_loss_window_is_100():
    closes = [1.0, 2.0, 3.0, 4.0, 5.0]
    stream = StreamingRSI(3)
    streamed = [stream.update(c) for c in closes]
    _assert_bit_equal(streamed, rsi(pd.Series(closes), 3))
    assert streamed[-1] == 100.0


@pytest.mark.parametrize("period", [2, 3, 14, 40])
def test_streaming_atr_bit_parity(period):
    highs, lows, closes = _ohlc(120)
    stream = StreamingATR(period)
    streamed = [
        stream.update(h, low, c)
        for h, low, c in zip(highs, lows, closes, strict=True)
    ]
    _assert_bit_equal(
        streamed, atr(pd.Series(highs), pd.Series(lows), pd.Series(closes), period)
    )


# --- N5a Tier-1 library: bit-parity (streaming == full-series, float-for-float) ----


def _volume(n: int) -> list[float]:
    """A deterministic, always-positive volume walk to pair with ``_ohlc``."""
    return [1000.0 + 400.0 * math.sin(i * 0.9) + 5.0 * i for i in range(n)]


@pytest.mark.parametrize("period", [2, 3, 14, 40])
def test_streaming_dema_bit_parity(period):
    _, _, closes = _ohlc(120)
    stream = StreamingDEMA(period)
    streamed = [stream.update(c) for c in closes]
    _assert_bit_equal(streamed, dema(pd.Series(closes), period))


@pytest.mark.parametrize("period", [2, 3, 14, 40])
def test_streaming_tema_bit_parity(period):
    _, _, closes = _ohlc(120)
    stream = StreamingTEMA(period)
    streamed = [stream.update(c) for c in closes]
    _assert_bit_equal(streamed, tema(pd.Series(closes), period))


def test_streaming_macd_bit_parity():
    _, _, closes = _ohlc(120)
    stream = StreamingMACD(12, 26, 9)
    streamed = [stream.update(c) for c in closes]
    ref_macd, ref_signal, ref_hist = macd(pd.Series(closes), 12, 26, 9)
    _assert_bit_equal([s[0] for s in streamed], ref_macd)
    _assert_bit_equal([s[1] for s in streamed], ref_signal)
    _assert_bit_equal([s[2] for s in streamed], ref_hist)


@pytest.mark.parametrize("period", [2, 3, 15, 40])
def test_streaming_trix_bit_parity(period):
    _, _, closes = _ohlc(120)
    stream = StreamingTRIX(period)
    streamed = [stream.update(c) for c in closes]
    _assert_bit_equal(streamed, trix(pd.Series(closes), period))


@pytest.mark.parametrize("long,short", [(25, 13), (5, 3), (40, 20)])
def test_streaming_tsi_bit_parity(long, short):
    _, _, closes = _ohlc(120)
    stream = StreamingTSI(long, short)
    streamed = [stream.update(c) for c in closes]
    _assert_bit_equal(streamed, tsi(pd.Series(closes), long, short))


@pytest.mark.parametrize("period", [2, 13, 40])
def test_streaming_elder_ray_bit_parity(period):
    highs, lows, closes = _ohlc(120)
    stream = StreamingElderRay(period)
    streamed = [
        stream.update(h, low, c) for h, low, c in zip(highs, lows, closes, strict=True)
    ]
    ref_bull, ref_bear = elder_ray(
        pd.Series(highs), pd.Series(lows), pd.Series(closes), period
    )
    _assert_bit_equal([s[0] for s in streamed], ref_bull)
    _assert_bit_equal([s[1] for s in streamed], ref_bear)


def test_streaming_obv_bit_parity():
    _, _, closes = _ohlc(120)
    vols = _volume(120)
    stream = StreamingOBV()
    streamed = [stream.update(c, v) for c, v in zip(closes, vols, strict=True)]
    _assert_bit_equal(streamed, obv(pd.Series(closes), pd.Series(vols)))


def test_streaming_ad_bit_parity():
    highs, lows, closes = _ohlc(120)
    vols = _volume(120)
    stream = StreamingAD()
    streamed = [
        stream.update(h, low, c, v)
        for h, low, c, v in zip(highs, lows, closes, vols, strict=True)
    ]
    _assert_bit_equal(
        streamed,
        ad(pd.Series(highs), pd.Series(lows), pd.Series(closes), pd.Series(vols)),
    )


def test_streaming_pvt_bit_parity():
    _, _, closes = _ohlc(120)
    vols = _volume(120)
    stream = StreamingPVT()
    streamed = [stream.update(c, v) for c, v in zip(closes, vols, strict=True)]
    _assert_bit_equal(streamed, pvt(pd.Series(closes), pd.Series(vols)))


@pytest.mark.parametrize("period", [2, 13, 40])
def test_streaming_force_index_bit_parity(period):
    _, _, closes = _ohlc(120)
    vols = _volume(120)
    stream = StreamingForceIndex(period)
    streamed = [stream.update(c, v) for c, v in zip(closes, vols, strict=True)]
    _assert_bit_equal(streamed, force_index(pd.Series(closes), pd.Series(vols), period))


def test_obv_known_values():
    # closes 10, 11, 11, 9, 10 ; vols all 100 -> +100, 0 (flat), -100, +100
    out = obv(pd.Series([10.0, 11.0, 11.0, 9.0, 10.0]), pd.Series([100.0] * 5))
    assert out.tolist() == [0.0, 100.0, 100.0, 0.0, 100.0]


def test_pvt_known_values():
    # bar1: 100*(11-10)/10 = 10 ; bar2: +100*(12-11)/11 = 10 + 9.0909...
    out = pvt(pd.Series([10.0, 11.0, 12.0]), pd.Series([100.0, 100.0, 100.0]))
    assert out.iloc[0] == 0.0
    assert out.iloc[1] == pytest.approx(10.0)
    assert out.iloc[2] == pytest.approx(10.0 + 100.0 * 1.0 / 11.0)
