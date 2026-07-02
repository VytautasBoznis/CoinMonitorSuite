from __future__ import annotations

from collections import deque

from coinmon.feed import BarView
from coinmon.strategies.base import Strategy


class RatioMomentum(Strategy):
    """Long when the close outperformed itself ``lookback`` bars ago, flat otherwise.

    On a synthetic ratio pair (``BASE_i/BASE_j``) time-series momentum IS relative momentum
    between the two coins — the crypto effect with real documented persistence (probe H1,
    alpha-hunt.md §1.5), which is why chunk W1 promotes it out of the RSI valley. The most
    recent ``skip`` bars are dropped from the rate-of-change window (the standard short-term
    reversal guard). ``band`` is the cost-aware entry threshold: the momentum must clear
    ``band`` (a fraction of price) before going long, so a move smaller than the round-trip
    cost can't buy a losing trade; it goes flat once momentum falls back below the band. The
    adaptive wrapper (``RegimeAdaptive``) supplies the short side when the genome is directional.
    """

    def __init__(self, lookback: int = 30, skip: int = 1, band: float = 0.0) -> None:
        self.lookback = lookback
        self.skip = skip
        self.band = band
        # Bounded to exactly the history the ROC needs: O(1)/bar, no growing buffer (N1 discipline).
        self._closes: deque[float] = deque(maxlen=lookback + skip + 1)

    def on_bar(self, view: BarView) -> int:
        self._closes.append(view.candle.close)
        if len(self._closes) < self._closes.maxlen:
            return 0  # warmup: not enough history for the lookback yet
        recent = self._closes[-1 - self.skip]
        past = self._closes[0]  # lookback+skip bars back == oldest bar in the bounded window
        roc = recent / past - 1.0
        return 1 if roc > self.band else 0
