from __future__ import annotations

from abc import ABC, abstractmethod

from coinmon.data.models import Candle


class Strategy(ABC):
    """Maps a stream of bars to a trading signal. The SAME class runs in backtest and live.

    The black-box engine pushes exactly ONE bar at a time via ``on_bar`` and never hands
    over a history frame. The strategy owns its own state: it buffers the bars it needs and
    computes its indicators from that buffer. This makes lookahead structurally impossible
    (it only ever sees bars up to now) and lets a live feed drive the same object unchanged.

    Strategies are COST-AWARE. Switching position is not free: a rotation pays two taker
    fees (+ spread/slippage), so a signal smaller than the round-trip cost is a losing trade
    even when the direction is right. A ``CostModel`` is injected (fee rates from config in
    backtest; the live exchange adapter live), and the strategy should apply a no-trade band
    — only change target when the expected move clears the estimated round-trip cost.
    Decision uses ESTIMATED cost only (fees known, slippage estimated); the Portfolio charges
    the REALIZED cost after the fill. Never let realized slippage feed the decision (lookahead).
    CostModel injection + the example no-trade bands land in build step 5.
    """

    @abstractmethod
    def on_bar(self, candle: Candle) -> int:
        """Consume the latest bar and return the desired position: +1 long, 0 flat (Phase 1)."""
        raise NotImplementedError
