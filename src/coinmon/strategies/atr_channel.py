from __future__ import annotations

import pandas as pd

from coinmon.feed import BarView
from coinmon.indicators import StreamingATR, StreamingEMA
from coinmon.strategies.base import Strategy


class ATRChannelBreakout(Strategy):
    """Keltner-style channel breakout (long/flat): go long on a volatility-confirmed breakout,
    flat once price falls back through the lower channel.

    The channel is an EMA midline +/- ``mult`` * ATR, both over ``period``. Enter long when the
    close pushes above the upper band; exit when it drops below the lower band. The ``mult`` * ATR
    half-width IS the no-trade band — it scales with volatility, so the cost hurdle is structural
    (like RSIMeanReversion's threshold gap) rather than a fixed price-cost band. Uses precomputed
    ``atr_<period>`` / ``ema_<period>`` features when the feed supplies them, else recomputes both
    from its own buffers of highs/lows/closes.
    """

    def __init__(self, period: int = 14, mult: float = 1.5) -> None:
        self.period = period
        self.mult = mult
        self._atr = StreamingATR(period)
        self._ema = StreamingEMA(period)
        self._target = 0

    def on_bar(self, view: BarView) -> int:
        candle = view.candle
        atr_streamed = self._atr.update(candle.high, candle.low, candle.close)
        mid_streamed = self._ema.update(candle.close)

        atr_value = view.feature(f"atr_{self.period}")
        mid = view.feature(f"ema_{self.period}")
        if atr_value is None:
            atr_value = atr_streamed
        if mid is None:
            mid = mid_streamed
        if pd.isna(atr_value) or pd.isna(mid):
            return self._target  # warmup: not enough history for ATR yet

        upper = mid + self.mult * atr_value
        lower = mid - self.mult * atr_value
        if self._target == 0 and candle.close > upper:
            self._target = 1
        elif self._target == 1 and candle.close < lower:
            self._target = 0
        return self._target
