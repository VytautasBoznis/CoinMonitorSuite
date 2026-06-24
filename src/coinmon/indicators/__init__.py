from __future__ import annotations

import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential moving average. Build step 4."""
    raise NotImplementedError("indicators.ema — build step 4")


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index with Wilder smoothing. Build step 4."""
    raise NotImplementedError("indicators.rsi — build step 4")
