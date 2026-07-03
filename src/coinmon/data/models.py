from __future__ import annotations

from dataclasses import dataclass

# Common candle column contract. One Parquet dataset per (exchange, symbol, timeframe).
# Synthetic-ratio frames (e.g. ETH/BTC) conform to this same contract so they feed the
# engine and strategies unchanged.
CANDLE_COLUMNS: tuple[str, ...] = (
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
)


@dataclass(frozen=True, slots=True)
class Candle:
    """A single OHLCV bar. ``open_time`` is the bar's open timestamp (epoch ms, UTC)."""

    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
