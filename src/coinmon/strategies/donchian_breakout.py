from __future__ import annotations

from collections import deque

import pandas as pd

from coinmon.feed import BarView
from coinmon.indicators import StreamingATR
from coinmon.strategies.base import Strategy


class DonchianBreakout(Strategy):
    """Long on an N-bar high breakout, flat on an ATR-scaled trailing stop.

    Enter long when the close pushes above the highest high of the *prior* ``channel`` bars
    (the Donchian upper channel — computed from bars before this one, so the close can
    genuinely exceed it and no-lookahead holds). Once long, trail a chandelier-style stop:
    track the highest close seen since entry and exit flat when the close falls
    ``exit_mult`` * ATR below that peak — so the exit widens with volatility rather than a
    fixed price band. This is a stop-and-reverse channel system, mechanically distinct from
    the moving-average state of EMA cross and the EMA-midline band of the ATR channel (chunk
    W4). Long/flat only; the ``RegimeAdaptive`` wrapper supplies the short side when the
    genome is directional.
    """

    def __init__(self, channel: int = 20, atr_period: int = 14, exit_mult: float = 3.0) -> None:
        self.channel = channel
        self.atr_period = atr_period
        self.exit_mult = exit_mult
        # Prior bars' highs for the entry channel. Bounded to ``channel`` (never grows with the
        # series): max() over it is constant work per bar, not the O(n) recompute N1 removed.
        self._highs: deque[float] = deque(maxlen=channel)
        self._atr = StreamingATR(atr_period)
        self._target = 0
        self._peak = 0.0  # highest close since entry (anchors the trailing stop)

    def on_bar(self, view: BarView) -> int:
        candle = view.candle
        atr_value = self._atr.update(candle.high, candle.low, candle.close)
        # Upper channel from the PRIOR bars only (read before appending this bar's high, so the
        # current close is compared against history, never against its own bar).
        upper = max(self._highs) if len(self._highs) == self.channel else None
        self._highs.append(candle.high)

        if self._target == 0:
            if upper is not None and candle.close > upper:
                self._target = 1
                self._peak = candle.close
        else:
            self._peak = max(self._peak, candle.close)
            if not pd.isna(atr_value) and candle.close < self._peak - self.exit_mult * atr_value:
                self._target = 0
        return self._target
