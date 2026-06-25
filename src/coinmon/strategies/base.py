from __future__ import annotations

from abc import ABC, abstractmethod

from coinmon.feed import BarView


class Strategy(ABC):
    """Maps a stream of bars to a trading signal. The SAME class runs in backtest and live.

    The black-box engine pushes exactly ONE ``BarView`` at a time via ``on_bar`` and never
    hands over a history frame. A ``BarView`` carries the current candle plus any indicators
    precomputed as-of that bar; if a needed indicator is absent the strategy computes it from
    its own rolling buffer of past bars. Either way it only ever sees data up to now, so
    lookahead is structurally impossible and a live feed can drive the same object unchanged.

    Strategies are COST-AWARE. Switching position is not free: a rotation pays two taker
    fees (+ spread/slippage), so a signal smaller than the round-trip cost is a losing trade
    even when the direction is right. A ``CostModel`` is injected (fee rates from config in
    backtest; the live exchange adapter live), and the strategy should apply a no-trade band
    — only change target when the expected move clears the estimated round-trip cost.
    Decision uses ESTIMATED cost only (fees known, slippage estimated); the Portfolio charges
    the REALIZED cost after the fill. Never let realized slippage feed the decision (lookahead).
    """

    @abstractmethod
    def on_bar(self, view: BarView) -> int:
        """Consume the latest bar and return the desired position: +1 long, 0 flat (Phase 1)."""
        raise NotImplementedError
