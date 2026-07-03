import numpy as np
import pandas as pd
import pytest

from coinmon.data.funding import align_funding, attach_funding


def _funding(rows):
    # rows: list of (funding_time, rate)
    return pd.DataFrame(rows, columns=["funding_time", "rate"])


def _candles(times):
    return pd.DataFrame(
        {
            "open_time": times,
            "open": [100.0] * len(times),
            "high": [101.0] * len(times),
            "low": [99.0] * len(times),
            "close": [100.0] * len(times),
            "volume": [1.0] * len(times),
        }
    )


def test_settlements_land_in_their_bar_window():
    times = [0, 100, 200, 300]
    funding = _funding([(50, 0.01), (150, 0.02), (250, 0.03), (350, 0.04)])
    aligned = align_funding(funding, times)
    assert list(aligned) == pytest.approx([0.01, 0.02, 0.03, 0.04])


def test_multiple_settlements_in_one_bar_are_summed():
    times = [0, 100, 200]
    funding = _funding([(10, 0.01), (50, 0.02), (90, 0.03), (150, 0.05)])
    aligned = align_funding(funding, times)
    assert list(aligned) == pytest.approx([0.06, 0.05, 0.0])


def test_settlement_on_open_time_belongs_to_that_bar():
    times = [0, 100, 200]
    funding = _funding([(100, 0.07)])  # exactly on bar 1's open
    aligned = align_funding(funding, times)
    assert list(aligned) == pytest.approx([0.0, 0.07, 0.0])


def test_settlements_before_the_first_bar_are_dropped():
    times = [100, 200, 300]
    funding = _funding([(50, 0.09), (150, 0.01)])  # 50 pre-history dropped; 150 in bar 0 [100,200)
    aligned = align_funding(funding, times)
    assert list(aligned) == pytest.approx([0.01, 0.0, 0.0])


def test_far_future_settlements_beyond_the_last_bar_are_dropped():
    times = [0, 100, 200, 300]  # spacing 100 => last bar window ends at 400
    funding = _funding([(350, 0.02), (450, 0.09)])  # 350 kept, 450 beyond -> dropped
    aligned = align_funding(funding, times)
    assert list(aligned) == pytest.approx([0.0, 0.0, 0.0, 0.02])


def test_empty_funding_yields_all_zeros_aligned_to_candles():
    times = [0, 100, 200]
    aligned = align_funding(_funding([]), times)
    assert aligned.shape == (3,)
    assert list(aligned) == pytest.approx([0.0, 0.0, 0.0])


def test_output_aligns_one_to_one_with_candle_times():
    times = [0, 100, 200, 300, 400]
    funding = _funding([(120, 0.01)])
    aligned = align_funding(funding, times)
    assert isinstance(aligned, np.ndarray)
    assert len(aligned) == len(times)


# --- attach_funding (chunk W3 step 2c: the searchable-carry seam) --------------------------


def test_attach_funding_adds_aligned_column_for_a_direct_perp():
    frame = _candles([0, 100, 200])
    funding = _funding([(50, 0.01), (150, 0.02), (250, 0.03)])
    out = attach_funding(frame, "BTC/USDC", lambda pair: funding)
    assert "funding_rate" in out.columns
    assert list(out["funding_rate"]) == pytest.approx([0.01, 0.02, 0.03])


def test_attach_funding_skips_ratio_pairs_without_a_lookup():
    frame = _candles([0, 100, 200])
    looked_up: list[str] = []

    def read_funding(pair):
        looked_up.append(pair)
        return _funding([(50, 0.01)])

    out = attach_funding(frame, "ETH/BTC", read_funding)  # BTC quote != USDC -> not a perp
    assert "funding_rate" not in out.columns
    assert looked_up == []  # a ratio is never a perp, so no funding is fetched


def test_attach_funding_leaves_frame_unchanged_when_perp_has_no_funding():
    frame = _candles([0, 100, 200])
    out = attach_funding(frame, "BTC/USDC", lambda pair: _funding([]))
    assert "funding_rate" not in out.columns  # byte-unchanged path (no column, no feature)
