from __future__ import annotations

from coinmon.feed import BarView
from coinmon.strategies.base import Strategy


class StopLoss(Strategy):
    """Risk overlay: wraps any strategy and forces a flat exit when an open long draws down
    more than ``stop_pct`` from its entry, capping the tail losses the inner strategy rides.

    Composable — it IS a ``Strategy`` (same ``on_bar(view) -> int``), so it stacks on any inner
    strategy without modifying it and the engine / stress harness drive it unchanged. The inner
    strategy is consulted every bar (it owns stateful buffers that must stay fed); while flat it
    passes the inner signal through, but a stop overrides the inner's long.

    No-lookahead holds: the trigger reads only the just-closed bar's low (known at close). Entry
    is referenced to the signal bar's close — the price basis the strategy acts on — while the
    actual fill is the next bar's open, so on a gap the realized loss can exceed ``stop_pct``.
    That's the honest behaviour of a stop (stops slip), and exactly what the fragility harness
    probes; the stop bounds the typical loss, not the worst case.

    After a stop-out it stays flat until the inner strategy goes flat and signals long afresh, so
    a strategy that keeps shouting "long" into a decline can't immediately re-enter the same stop.
    """

    def __init__(self, inner: Strategy, stop_pct: float) -> None:
        if not 0.0 < stop_pct < 1.0:
            raise ValueError("stop_pct must be in (0, 1)")
        self.inner = inner
        self.stop_pct = stop_pct
        self._entry: float | None = None  # entry reference price while holding, else None
        self._stopped = False  # stopped out, suppressing re-entry until the inner resets

    def on_bar(self, view: BarView) -> int:
        target = self.inner.on_bar(view)  # always feed the inner strategy's state
        candle = view.candle

        if self._entry is not None:  # currently holding a long
            if candle.low <= self._entry * (1.0 - self.stop_pct):
                self._entry = None
                self._stopped = True
                return 0
            if target == 0:  # inner wants out
                self._entry = None
                return 0
            return 1

        # currently flat
        if target == 0:
            self._stopped = False  # inner has reset; future longs are allowed again
            return 0
        if self._stopped:  # inner still long after a stop-out — suppress re-entry
            return 0
        self._entry = candle.close
        return 1
