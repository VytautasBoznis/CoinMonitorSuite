from __future__ import annotations

from collections import deque

from coinmon.feed import BarView
from coinmon.strategies.base import Strategy


class FundingCarry(Strategy):
    """Hedge on (1) to harvest perp funding when it is richly positive, flat (0) otherwise.

    Funding is a collectible PREMIUM, not a timing signal (probe H6, alpha-hunt.md §1.5): when
    perp funding is positive the crowded longs pay the shorts, so a market-neutral book (long spot
    + short perp — ``CarryPortfolio``) collects it without taking price direction. This strategy
    decides WHEN the premium is worth the four taker-fee legs: it reads the point-in-time
    ``funding_rate`` feature the engine exposes, keeps a bounded rolling window of recent rates,
    and turns the hedge on only when the current rate is positive AND sits at or above the
    ``entry_pct`` quantile of that window (funding at its richest). It goes flat when the rate turns
    non-positive or drops out of the top of its own recent range — never paying to hold the hedge.

    ``CarryPortfolio`` supplies the market-neutral book (wired via the genome's family, chunk W3);
    the direction/leverage/stop genes are inert for a hedged carry — there is no price side to take
    and nothing to stop out.
    """

    def __init__(self, window: int = 60, entry_pct: float = 0.5) -> None:
        self.window = window
        self.entry_pct = entry_pct
        # Bounded to the percentile window: O(window)/bar, no growth with series length (N1).
        self._rates: deque[float] = deque(maxlen=window)

    def on_bar(self, view: BarView) -> int:
        rate = view.feature("funding_rate")
        if rate is None:  # no funding on this pair/bar (e.g. a ratio, or a no-funding run) -> flat
            return 0
        self._rates.append(rate)
        if len(self._rates) < self._rates.maxlen:
            return 0  # warmup: not a full window to rank the current rate against yet
        if rate <= 0.0:
            return 0  # never run a fee-bleeding hedge while paying to hold it
        rank = sum(1 for r in self._rates if r <= rate) / len(self._rates)
        return 1 if rank >= self.entry_pct else 0
