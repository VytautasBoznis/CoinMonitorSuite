import pandas as pd

from coinmon.data.models import CANDLE_COLUMNS
from coinmon.data.ratio import build_ratio


def _frame(rows):
    return pd.DataFrame(rows, columns=list(CANDLE_COLUMNS))


def test_build_ratio_close_and_contract():
    eth = _frame(
        [
            [1, 2000.0, 2100.0, 1900.0, 2050.0, 10.0],
            [2, 2050.0, 2200.0, 2000.0, 2150.0, 12.0],
        ]
    )
    btc = _frame(
        [
            [1, 40000.0, 41000.0, 39000.0, 40500.0, 5.0],
            [2, 40500.0, 42000.0, 40000.0, 41000.0, 8.0],
        ]
    )
    out = build_ratio(eth, btc)

    assert list(out.columns) == list(CANDLE_COLUMNS)
    assert out["close"].tolist() == [2050.0 / 40500.0, 2150.0 / 41000.0]
    assert out["open"].tolist() == [2000.0 / 40000.0, 2050.0 / 40500.0]
    # high = base.high / quote.low ; low = base.low / quote.high
    assert out["high"].iloc[0] == 2100.0 / 39000.0
    assert out["low"].iloc[0] == 1900.0 / 41000.0
    assert (out["high"] >= out["low"]).all()
    # volume = min of the two legs (binding liquidity)
    assert out["volume"].tolist() == [5.0, 8.0]


def test_build_ratio_inner_join_drops_unaligned_bars():
    eth = _frame(
        [
            [1, 2000.0, 2100.0, 1900.0, 2050.0, 10.0],
            [2, 2050.0, 2200.0, 2000.0, 2150.0, 12.0],
            [3, 2150.0, 2250.0, 2100.0, 2200.0, 9.0],
        ]
    )
    btc = _frame(
        [
            [2, 40500.0, 42000.0, 40000.0, 41000.0, 8.0],
            [3, 41000.0, 43000.0, 40500.0, 42000.0, 7.0],
        ]
    )
    out = build_ratio(eth, btc)

    assert out["open_time"].tolist() == [2, 3]  # bar 1 (eth-only) dropped
    assert not out.isna().any().any()
