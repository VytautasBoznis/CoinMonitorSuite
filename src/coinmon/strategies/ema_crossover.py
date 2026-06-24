from __future__ import annotations

from coinmon.data.models import Candle
from coinmon.strategies.base import Strategy


class EMACrossover(Strategy):
    """Long when the fast EMA is above the slow EMA, flat otherwise. Build step 5.

    Buffers closes internally and updates its EMAs per bar.
    """

    def __init__(self, fast: int = 12, slow: int = 26) -> None:
        self.fast = fast
        self.slow = slow

    def on_bar(self, candle: Candle) -> int:
        raise NotImplementedError("EMACrossover.on_bar — build step 5")
