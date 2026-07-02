import random

import pandas as pd

from coinmon.data.models import CANDLE_COLUMNS
from coinmon.data.surrogate import block_bootstrap_indices, surrogate_legs


def _leg(closes, start_time=0):
    """An OHLCV frame from a close series, with a fixed intrabar shape (open below, high above,
    low below close) so OHLC-validity and shape-preservation can be checked after resampling."""
    return pd.DataFrame(
        {
            "open_time": [start_time + i for i in range(len(closes))],
            "open": [c * 0.995 for c in closes],
            "high": [c * 1.02 for c in closes],
            "low": [c * 0.98 for c in closes],
            "close": list(closes),
            "volume": [100.0 + i for i in range(len(closes))],
        }
    )[list(CANDLE_COLUMNS)]


def _growth(frame):
    c = frame["close"].to_numpy(float)
    return [c[i + 1] / c[i] for i in range(len(c) - 1)]


# --- block_bootstrap_indices ---


def test_indices_length_and_range():
    idx = block_bootstrap_indices(50, 20, random.Random(0))
    assert len(idx) == 50
    assert all(0 <= i < 50 for i in idx)


def test_indices_one_block_is_contiguous_wraparound():
    # block_len >= n -> a single block from a random start, wrapping the end, so consecutive values
    # step by 1 (mod n): the within-block temporal order the bootstrap preserves.
    idx = block_bootstrap_indices(8, 100, random.Random(3))
    assert len(idx) == 8
    for a, b in zip(idx, idx[1:], strict=False):
        assert b == (a + 1) % 8


def test_indices_deterministic_in_seed():
    assert block_bootstrap_indices(30, 5, random.Random(7)) == block_bootstrap_indices(
        30, 5, random.Random(7)
    )


def test_indices_empty_for_nonpositive_n():
    assert block_bootstrap_indices(0, 5, random.Random(0)) == []


# --- surrogate_legs ---


def test_surrogate_preserves_shape_length_and_columns():
    legs = {"BTC/USDC": _leg([100 + i for i in range(20)])}
    out = surrogate_legs(legs, block_len=5, seed=1)
    frame = out["BTC/USDC"]
    assert list(frame.columns) == list(CANDLE_COLUMNS)
    assert len(frame) == 20


def test_surrogate_first_bar_is_anchored_to_the_original():
    legs = {"BTC/USDC": _leg([100 + i * 2 for i in range(15)])}
    out = surrogate_legs(legs, block_len=4, seed=2)["BTC/USDC"]
    assert out["close"].iloc[0] == 100.0
    assert out["open"].iloc[0] == 100.0 * 0.995


def test_surrogate_prices_positive_and_ohlc_valid():
    legs = {"BTC/USDC": _leg([100 * 1.01**i for i in range(30)])}
    out = surrogate_legs(legs, block_len=6, seed=4)["BTC/USDC"]
    assert (out[["open", "high", "low", "close"]] > 0).all().all()
    assert (out["high"] >= out[["open", "close"]].max(axis=1)).all()
    assert (out["low"] <= out[["open", "close"]].min(axis=1)).all()


def test_surrogate_resamples_real_returns():
    # Every surrogate close-to-close growth factor is one of the ORIGINAL growth factors — the
    # surrogate reuses real returns, it does not fabricate new ones.
    closes = [100 * 1.03**i if i % 2 else 100 * 0.97**i for i in range(24)]
    src = _leg(closes)
    original = set(round(g, 10) for g in _growth(src))
    out = surrogate_legs({"BTC/USDC": src}, block_len=1, seed=5)["BTC/USDC"]
    assert all(round(g, 10) in original for g in _growth(out))


def test_surrogate_reorders_time():
    # block_len=1 fully re-orders the returns, so the surrogate return sequence differs from the
    # original — the temporal signal a strategy keys on is destroyed.
    closes = [100 + i + (i % 3) * 5 for i in range(20)]
    src = _leg(closes)
    out = surrogate_legs({"BTC/USDC": src}, block_len=1, seed=6)["BTC/USDC"]
    assert _growth(out) != _growth(src)


def test_surrogate_is_deterministic_in_seed():
    legs = {"BTC/USDC": _leg([100 + i for i in range(18)])}
    a = surrogate_legs(legs, block_len=4, seed=9)["BTC/USDC"]
    b = surrogate_legs(legs, block_len=4, seed=9)["BTC/USDC"]
    assert a.equals(b)


def test_surrogate_different_seed_differs():
    legs = {"BTC/USDC": _leg([100 + i * 0.5 + (i % 4) for i in range(25)])}
    a = surrogate_legs(legs, block_len=3, seed=1)["BTC/USDC"]
    b = surrogate_legs(legs, block_len=3, seed=2)["BTC/USDC"]
    assert not a["close"].equals(b["close"])


def test_surrogate_preserves_cross_leg_correlation():
    # Two legs sharing the SAME returns (one is a scaled copy) get the SAME block sequence applied,
    # so their surrogate returns stay identical — cross-leg co-movement survives the resample.
    closes = [100 * 1.01**i for i in range(22)]
    legs = {"A/USDC": _leg(closes), "B/USDC": _leg([c * 7.0 for c in closes])}
    out = surrogate_legs(legs, block_len=5, seed=3)
    ga = _growth(out["A/USDC"])
    gb = _growth(out["B/USDC"])
    assert all(abs(x - y) < 1e-12 for x, y in zip(ga, gb, strict=True))


def test_surrogate_joint_over_common_time_only():
    # Legs overlapping on only part of their span are resampled over the shared window; the output
    # spans exactly the common open_times.
    a = _leg([100 + i for i in range(20)], start_time=0)
    b = _leg([50 + i for i in range(20)], start_time=5)  # shifted -> overlap is times 5..19
    out = surrogate_legs({"A/USDC": a, "B/USDC": b}, block_len=4, seed=1)
    assert list(out["A/USDC"]["open_time"]) == list(range(5, 20))
    assert list(out["B/USDC"]["open_time"]) == list(range(5, 20))


def test_surrogate_passthrough_when_too_few_common_bars():
    a = _leg([100.0], start_time=0)
    b = _leg([100.0], start_time=0)
    out = surrogate_legs({"A/USDC": a, "B/USDC": b}, block_len=4, seed=1)
    assert out["A/USDC"].equals(a)
