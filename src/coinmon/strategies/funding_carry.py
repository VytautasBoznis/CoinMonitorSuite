from __future__ import annotations

from collections import deque

from coinmon.feed import BarView
from coinmon.strategies.base import Strategy


class FundingCarry(Strategy):
    """Hedge on (1) while the smoothed funding premium is positive, flat (0) otherwise.

    Funding is a collectible PREMIUM, not a timing signal (probe H6, alpha-hunt.md §1.5): when
    perp funding is positive the crowded longs pay the shorts, so a market-neutral book (long spot
    + short perp — ``CarryPortfolio``) collects it without taking price direction. The whole game
    is FEE EFFICIENCY: each hedge round-trip costs four taker legs (~0.2%), while a bar's funding is
    tiny (~0.005%/bar at 1x), so the hedge must be HELD across many settlements, not toggled. The
    first live run (2026-07-05, [[w3-carry-first-live-diagnosis]]) proved this: the earlier
    percentile-toggle design re-hedged on every funding wobble and bled −1.4%/yr net, while simply
    HOLDING captured the real +2–5%/yr premium (29/29 USDT perps positive at 1d).

    So this reads the point-in-time ``funding_rate`` feature, keeps a bounded rolling window, and
    hedges on only while the window MEAN clears ``threshold`` — smoothing rides out single-bar dips
    (and, at sub-8h bars, the alternating zero-funding bars between 8h settlements) so it exits only
    when the funding REGIME turns durably non-positive. ``threshold`` = 0 harvests whenever the
    smoothed premium is positive; a positive floor only harvests when it is meaningfully rich.

    ``CarryPortfolio`` supplies the market-neutral book (wired via the genome's family, chunk W3);
    the direction/leverage/stop genes are inert for a hedged carry — there is no price side to take
    and nothing to stop out.
    """

    def __init__(self, window: int = 60, threshold: float = 0.0) -> None:
        self.window = window
        self.threshold = threshold
        # Bounded to the smoothing window: O(window)/bar, no growth with series length (N1).
        self._rates: deque[float] = deque(maxlen=window)

    def on_bar(self, view: BarView) -> int:
        rate = view.feature("funding_rate")
        if rate is None:  # no funding on this pair/bar (e.g. a ratio, or a no-funding run) -> flat
            return 0
        self._rates.append(rate)
        if len(self._rates) < self._rates.maxlen:
            return 0  # warmup: not a full window to average yet
        mean_rate = sum(self._rates) / len(self._rates)
        return 1 if mean_rate > self.threshold else 0
