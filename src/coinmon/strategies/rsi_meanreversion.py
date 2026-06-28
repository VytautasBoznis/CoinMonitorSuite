from __future__ import annotations

import pandas as pd

from coinmon.feed import BarView
from coinmon.indicators import StreamingRSI
from coinmon.strategies.base import Strategy


class RSIMeanReversion(Strategy):
    """Long when RSI is oversold, flat once it recovers past the exit level.

    The oversold -> exit-level gap (default 30 -> 50) is the strategy's no-trade band: it
    enters only on a meaningful dip and won't re-enter until RSI has clearly recovered, so
    sub-threshold wiggles can't churn fees — the cost hurdle is structural in RSI space
    rather than a price-cost band (unlike EMACrossover). Uses a precomputed ``rsi_<period>``
    feature when the feed provides it, else recomputes RSI from its own buffer of closes.
    """

    def __init__(self, period: int = 14, oversold: float = 30.0, exit_level: float = 50.0) -> None:
        self.period = period
        self.oversold = oversold
        self.exit_level = exit_level
        self._rsi = StreamingRSI(period)
        self._target = 0

    def on_bar(self, view: BarView) -> int:
        streamed = self._rsi.update(view.candle.close)
        value = view.feature(f"rsi_{self.period}")
        if value is None:
            value = streamed
        if pd.isna(value):
            return self._target  # warmup: not enough history for RSI yet

        if self._target == 0 and value < self.oversold:
            self._target = 1
        elif self._target == 1 and value > self.exit_level:
            self._target = 0
        return self._target
