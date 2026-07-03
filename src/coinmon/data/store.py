from __future__ import annotations

from pathlib import Path

import pandas as pd

from coinmon.config import settings


def dataset_path(exchange: str, symbol: str, timeframe: str) -> Path:
    """Parquet path for one (exchange, symbol, timeframe) candle series."""
    safe_symbol = symbol.replace("/", "-")
    return settings.data_dir / exchange / safe_symbol / f"{timeframe}.parquet"


def write_candles(df: pd.DataFrame, exchange: str, symbol: str, timeframe: str) -> Path:
    """Persist a candle frame to Parquet. Implemented in build step 2."""
    raise NotImplementedError("store.write_candles — build step 2 (Bybit data adapter)")


def read_candles(exchange: str, symbol: str, timeframe: str) -> pd.DataFrame:
    """Load a candle frame from Parquet. Implemented in build step 2."""
    raise NotImplementedError("store.read_candles — build step 2 (Bybit data adapter)")
