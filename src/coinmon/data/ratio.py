from __future__ import annotations

import pandas as pd

from coinmon.data.models import CANDLE_COLUMNS


def build_ratio(base_leg: pd.DataFrame, quote_leg: pd.DataFrame) -> pd.DataFrame:
    """Synthesize a coin/coin OHLCV-like frame from two USDC legs.

    e.g. ETH/BTC = (ETH/USDC) / (BTC/USDC), inner-joined on a shared ``open_time`` so only
    bars present in *both* legs survive (no NaN rows). The result conforms to
    ``CANDLE_COLUMNS`` so it feeds the engine and strategies unchanged.

    OHLC are combined per bar so the synthetic high/low bound the ratio's true extremes:
    the ratio is largest when the numerator peaks while the denominator bottoms, hence
    ``high = base.high / quote.low`` and ``low = base.low / quote.high``. Volume is the
    *min* of the two legs — a rotation can only move as much size as the thinner leg
    supports, so that's the honest liquidity proxy (raw volumes aren't additive across a
    ratio).
    """
    merged = base_leg.merge(quote_leg, on="open_time", suffixes=("_b", "_q"), how="inner")
    # Data hygiene (chunk N4): illiquid alts carry bad prints — zero/negative/NaN OHLC — that poison
    # the ratio (a zero or NaN in a denominator yields inf/NaN and corrupts the whole synthetic
    # series). Drop any bar where either leg has a non-positive or missing price before dividing, so
    # a single bad print can't propagate. Clean USDC pairs (all prices > 0) are unaffected.
    price_cols = [f"{c}_{leg}" for leg in ("b", "q") for c in ("open", "high", "low", "close")]
    merged = merged[(merged[price_cols] > 0).all(axis=1)]
    out = pd.DataFrame(
        {
            "open_time": merged["open_time"],
            "open": merged["open_b"] / merged["open_q"],
            "high": merged["high_b"] / merged["low_q"],
            "low": merged["low_b"] / merged["high_q"],
            "close": merged["close_b"] / merged["close_q"],
            "volume": merged[["volume_b", "volume_q"]].min(axis=1),
        }
    )
    return out[list(CANDLE_COLUMNS)].sort_values("open_time").reset_index(drop=True)
