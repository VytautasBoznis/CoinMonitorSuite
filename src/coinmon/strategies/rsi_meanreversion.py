from __future__ import annotations

from coinmon.data.models import Candle
from coinmon.strategies.base import Strategy


class RSIMeanReversion(Strategy):
    """Long when RSI is oversold, flat once it recovers past the exit level. Build step 5.

    Buffers closes internally and updates its RSI (Wilder smoothing) per bar.
    """

    def __init__(self, period: int = 14, oversold: float = 30.0, exit_level: float = 50.0) -> None:
        self.period = period
        self.oversold = oversold
        self.exit_level = exit_level

    def on_bar(self, candle: Candle) -> int:
        raise NotImplementedError("RSIMeanReversion.on_bar — build step 5")
