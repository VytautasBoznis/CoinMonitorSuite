from __future__ import annotations

from coinmon.feed import BarView, CostModel
from coinmon.indicators import StreamingEMA
from coinmon.strategies.base import Strategy


class EMACrossover(Strategy):
    """Long when the fast EMA leads the slow EMA, flat otherwise — with a cost-aware band.

    The raw signal is the relative EMA spread ``(fast - slow) / close``. To avoid churning
    fees on noise it only switches when that spread clears the round-trip taker cost: enter
    long when flat and spread > cost, go flat when long and spread < -cost. Inside the band
    it holds. Uses precomputed ``ema_<period>`` features when the feed provides them, else
    recomputes the EMAs from its own buffer of closes.
    """

    def __init__(self, cost: CostModel, fast: int = 12, slow: int = 26) -> None:
        self.cost = cost
        self.fast = fast
        self.slow = slow
        self._fast_ema = StreamingEMA(fast)
        self._slow_ema = StreamingEMA(slow)
        self._target = 0

    def on_bar(self, view: BarView) -> int:
        close = view.candle.close
        fast_streamed = self._fast_ema.update(close)
        slow_streamed = self._slow_ema.update(close)
        fast = view.feature(f"ema_{self.fast}")
        slow = view.feature(f"ema_{self.slow}")
        if fast is None:
            fast = fast_streamed
        if slow is None:
            slow = slow_streamed

        spread = (fast - slow) / close
        band = self.cost.round_trip_cost()
        if self._target == 0 and spread > band:
            self._target = 1
        elif self._target == 1 and spread < -band:
            self._target = 0
        return self._target
