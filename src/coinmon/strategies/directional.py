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


class RegimeAdaptive(Strategy):
    """Let the *current-bar* trend regime pick the direction, so the same genome flips with the
    market instead of betting one direction persists.

    A fixed per-genome ``short`` gene is fit to the search span but blind to the unseen holdout
    regime, which is why every live graduation NO-GO was a wrong-direction bet (long where the
    holdout crashed, short where it rose — see [[direction-gene-overfits-regime]]). This reads the
    regime point-in-time from a simple ``trend_period`` SMA of the closes the strategy has actually
    seen (no lookahead, a live feed drives it unchanged):

    - **Up-regime** (close >= SMA): run the base long/flat unchanged — it will NOT short a rising
      market, the exact mistake that NO-GO'd the rising BNB/ETH holdout.
    - **Down-regime** (close < SMA): apply ``ShortWhenFlat`` — when the base would sit in cash,
      short instead, so a falling market is ridden rather than merely sidestepped.

    Direction therefore reads the holdout's OWN measured trend. During warmup (fewer than
    ``trend_period`` closes) the regime is undefined, so it stays long/flat and never shorts on
    thin evidence. Pairs with a ``PerpPortfolio`` (it may short); leverage is a separate gene.

    This is NOT guaranteed to win a *choppy* crash — a whipsawing regime flag can flip into bear
    rallies and lose ([[chunk-l-live-validation]]); the graduation gate stays the judge.
    """

    def __init__(self, base: Strategy, trend_period: int) -> None:
        self._base = base
        self._short = ShortWhenFlat(base)  # same underlying base — call exactly once per bar
        self._trend_period = trend_period
        self._closes: list[float] = []

    def on_bar(self, view: BarView) -> int:
        self._closes.append(view.candle.close)
        if len(self._closes) < self._trend_period:
            return self._base.on_bar(view)  # warmup: regime undefined, stay long/flat
        sma = sum(self._closes[-self._trend_period :]) / self._trend_period
        if view.candle.close >= sma:
            return self._base.on_bar(view)  # up-regime: long/flat
        return self._short.on_bar(view)  # down-regime: short when the base would go flat
