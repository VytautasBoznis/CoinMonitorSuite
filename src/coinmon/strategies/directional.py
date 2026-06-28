from __future__ import annotations

from coinmon.feed import BarView
from coinmon.strategies.base import Strategy


class ShortWhenFlat(Strategy):
    """Wrap a long/flat strategy so its exit-to-cash becomes a short — the bearish leg.

    The base strategy still decides direction on price; this only reinterprets its signal:
    +1 stays long, but 0 ("go to cash") is turned into -1 (go short). Leverage is not here — it
    lives in ``PerpPortfolio`` — so this is a pure direction transform. Paired with a
    ``PerpPortfolio`` the account is always directional (long or short, never flat), so a
    strategy that profitably times exits in a downtrend now *profits from the drop* instead of
    merely sidestepping it. This is exactly "at the moment you'd sell, short instead."

    A base that already shorts (-1) is passed through unchanged.
    """

    def __init__(self, base: Strategy) -> None:
        self._base = base

    def on_bar(self, view: BarView) -> int:
        signal = self._base.on_bar(view)
        return signal if signal != 0 else -1
