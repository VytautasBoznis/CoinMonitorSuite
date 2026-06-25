from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field

from coinmon.config import settings
from coinmon.data.models import Candle


@dataclass(frozen=True, slots=True)
class BarView:
    """What the black-box feed hands the strategy at each step: the current closed bar plus
    any indicator values already computed **as of this bar** — never beyond it.

    Phase 1's backtest feeds bare bars (``features`` empty) and the strategy computes its
    own indicators from a rolling buffer. A later indicator-engine can instead fill
    ``features`` so many bots share one computation. Because the feed only ever exposes
    values derived from bars <= now, no-lookahead holds either way — the precomputed path
    is a cache, not a new contract. The strategy must still work from ``candle`` alone.
    """

    candle: Candle
    features: Mapping[str, float] = field(default_factory=dict)

    def feature(self, name: str) -> float | None:
        """A precomputed indicator value for this bar, or ``None`` if absent/NaN."""
        value = self.features.get(name)
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return None
        return value


@dataclass(frozen=True, slots=True)
class CostModel:
    """The fee schedule the black box exposes to the strategy for its no-trade band — the
    same thing a live exchange tells you. A spot rotation pays a taker fee on **both** legs
    (sell leg -> USDC, buy USDC -> leg), so the round-trip cost a band must clear is two
    taker fees. This is the *estimable-at-now* cost used for the decision; the portfolio
    charges the *realized* cost after the fill (never let realized cost feed the decision).
    """

    taker_fee: float

    @classmethod
    def from_settings(cls) -> CostModel:
        return cls(taker_fee=settings.taker_fee)

    def round_trip_cost(self) -> float:
        return 2.0 * self.taker_fee
