from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from coinmon.data.models import Candle
from coinmon.feed import BarView
from coinmon.indicators import (
    StreamingATR,
    StreamingEMA,
    StreamingMACD,
    StreamingRSI,
    StreamingTRIX,
    StreamingTSI,
)
from coinmon.strategies.base import Strategy

# Chunk P: the bounded multi-indicator genome — the risk-managed half-step toward tree-GP (Q).
# Instead of the three hand-built strategy templates, the MACHINE composes a small program: pick
# N_CONDITIONS indicators from a curated pool, each with a period, a comparison and a threshold,
# and join them with one AND/OR rule. The shape is FIXED (no trees yet), so the overfit surface
# grows by a controlled, watchable amount — exactly what chunk P needs to test whether the
# O-hardened gate holds its false-GO rate against a bigger-but-bounded representation.
#
# It compiles to an ordinary ``Strategy`` (this module's ``build_combo``) and is registered as a
# normal family in ``genome.FAMILIES``, so it reuses the WHOLE pipeline unchanged: GA sampling/
# mutation/crossover, ``decode``/``decode_portfolio`` (an adaptive combo is wrapped in
# RegimeAdaptive and trades a perp just like any family), OOS fitness, graduation, cross-pair.
#
# THE THRESHOLD-SCALE PROBLEM and its fix. Indicators live on incomparable scales (RSI is 0..100,
# a MACD histogram is in price units that differ by 1000x across pairs). A single uniform threshold
# gene can't be meaningful across them. So the genotype is SCALE-FREE: ``period`` and ``threshold``
# are stored as unit floats in [0, 1], and each indicator's ``IndicatorSpec`` maps the unit to its
# OWN natural range at decode time. The GA therefore mutates one uniform schema while every
# indicator still gets sane periods/thresholds. The pool is also curated to pair-scale-INVARIANT
# signals (oscillators, or quantities divided by price), so a threshold means the same thing on
# BTC/USDC and a tiny ratio pair — the cumulative-volume indicators (OBV/AD/PVT) are deliberately
# left out for now because their absolute level is pair-scale-dependent (a clean follow-on is to
# add them normalised against their own trend).

COMBO_FAMILY = "indicator_combo"

# Fixed genome shape: how many (indicator, period, op, threshold) conditions are joined by the
# single AND/OR combine gene. Two is the cleanest bounded half-step; the code is general, so
# bumping this to 3 (the upper end of the roadmap's "2-3 indicators") is a one-line change.
N_CONDITIONS = 2


@dataclass(frozen=True)
class IndicatorSpec:
    """One indicator the combo can pick. ``make(period)`` builds its streaming O(1)/bar object;
    ``evaluate(stream, candle)`` updates that object with the new bar and returns a single
    pair-scale-invariant scalar (NaN during warmup). ``[min_period, max_period]`` and
    ``[thr_lo, thr_hi]`` are the natural ranges the genome's unit [0, 1] genes map onto."""

    name: str
    make: Callable[[int], object]
    evaluate: Callable[[object, Candle], float]
    min_period: int
    max_period: int
    thr_lo: float
    thr_hi: float


# The curated pool. Every ``evaluate`` returns a value that means the same thing regardless of the
# pair's price scale: a bounded oscillator (rsi/trix/tsi) or a quantity divided by the close
# (macd histogram, EMA deviation, ATR). MACD couples its slow EMA to 2x the fast period and its
# signal to half it (classic 12/26/9 ratios), keeping the whole indicator on one period gene.
INDICATORS: tuple[IndicatorSpec, ...] = (
    IndicatorSpec(
        "rsi",
        make=lambda p: StreamingRSI(p),
        evaluate=lambda s, c: s.update(c.close),
        min_period=2, max_period=40, thr_lo=10.0, thr_hi=90.0,
    ),
    IndicatorSpec(
        "trix",
        make=lambda p: StreamingTRIX(p),
        evaluate=lambda s, c: s.update(c.close),
        min_period=5, max_period=40, thr_lo=-1.0, thr_hi=1.0,
    ),
    IndicatorSpec(
        "tsi",
        make=lambda p: StreamingTSI(p, max(2, p // 2)),
        evaluate=lambda s, c: s.update(c.close),
        min_period=10, max_period=40, thr_lo=-40.0, thr_hi=40.0,
    ),
    IndicatorSpec(
        "macd_hist",
        make=lambda p: StreamingMACD(p, 2 * p, max(2, p // 2)),
        evaluate=lambda s, c: s.update(c.close)[2] / c.close,
        min_period=5, max_period=30, thr_lo=-0.02, thr_hi=0.02,
    ),
    IndicatorSpec(
        "ema_dev",
        make=lambda p: StreamingEMA(p),
        evaluate=lambda s, c: (c.close - s.update(c.close)) / c.close,
        min_period=5, max_period=50, thr_lo=-0.05, thr_hi=0.05,
    ),
    IndicatorSpec(
        "atr_pct",
        make=lambda p: StreamingATR(p),
        evaluate=lambda s, c: s.update(c.high, c.low, c.close) / c.close,
        min_period=5, max_period=40, thr_lo=0.0, thr_hi=0.1,
    ),
)

INDICATOR_COUNT = len(INDICATORS)


@dataclass(frozen=True)
class Condition:
    """One decoded ``indicator OP threshold`` predicate at a concrete period."""

    spec: IndicatorSpec
    period: int
    op: str  # ">" or "<"
    threshold: float


def _decode_index(value: float, count: int) -> int:
    """Map an indicator/op gene (an integer-valued float) to a valid index, clamped defensively in
    case a hand-built genome carries an out-of-range value (the GA stays in range already)."""
    return max(0, min(count - 1, int(round(value))))


def _decode_period(spec: IndicatorSpec, unit: float) -> int:
    """Map a unit [0, 1] period gene onto the indicator's own integer period range."""
    span = spec.max_period - spec.min_period
    value = round(spec.min_period + unit * span)
    return max(spec.min_period, min(spec.max_period, value))


def _decode_threshold(spec: IndicatorSpec, unit: float) -> float:
    """Map a unit [0, 1] threshold gene onto the indicator's own value range."""
    return spec.thr_lo + unit * (spec.thr_hi - spec.thr_lo)


def decode_conditions(params: Mapping[str, float]) -> tuple[list[Condition], str]:
    """Decode the flat param genes into the list of conditions plus the combine rule. Shared by
    ``build_combo`` (runs them) and ``describe_combo`` (prints them), so the two never diverge."""
    conditions: list[Condition] = []
    for i in range(N_CONDITIONS):
        spec = INDICATORS[_decode_index(params[f"ind{i}"], INDICATOR_COUNT)]
        period = _decode_period(spec, params[f"period{i}"])
        op = ">" if _decode_index(params[f"op{i}"], 2) == 1 else "<"
        threshold = _decode_threshold(spec, params[f"thr{i}"])
        conditions.append(Condition(spec, period, op, threshold))
    combine = "or" if _decode_index(params["combine"], 2) == 1 else "and"
    return conditions, combine


class IndicatorCombo(Strategy):
    """Go long when the combined indicator conditions fire, flat otherwise.

    Each condition updates its own streaming indicator every bar (state must advance even when a
    sibling is still warming up) and tests ``value OP threshold``; the conditions are joined by AND
    or OR. While ANY indicator is in warmup (NaN) the position is held — the rule is undefined, so
    the strategy doesn't trade on partial evidence. There is no separate entry/exit band: the same
    combined predicate both enters and exits, so a churny rule simply pays fees and the OOS fitness
    rejects it (the honest signal), rather than a band being baked in. Point-in-time by construction
    (only streaming values up to now), so a live feed drives the same object unchanged.
    """

    def __init__(self, conditions: Sequence[Condition], combine: str) -> None:
        self._combine = combine
        # (streaming object, the spec's evaluate fn, op, threshold) per condition.
        self._conditions = [
            (c.spec.make(c.period), c.spec.evaluate, c.op, c.threshold) for c in conditions
        ]
        self._target = 0

    def on_bar(self, view: BarView) -> int:
        candle = view.candle
        # Update every stream this bar (list, not generator) so warmup never desyncs the state.
        values = [evaluate(stream, candle) for stream, evaluate, _, _ in self._conditions]
        if any(math.isnan(v) for v in values):
            return self._target  # an indicator is still warming up: rule undefined, hold
        fires = [
            value > threshold if op == ">" else value < threshold
            for value, (_, _, op, threshold) in zip(values, self._conditions, strict=True)
        ]
        hit = all(fires) if self._combine == "and" else any(fires)
        self._target = 1 if hit else 0
        return self._target


def build_combo(params: Mapping[str, float]) -> Strategy:
    """Compile the flat combo genes into an ``IndicatorCombo`` strategy — the family's ``build``."""
    conditions, combine = decode_conditions(params)
    return IndicatorCombo(conditions, combine)


def describe_combo(params: Mapping[str, float]) -> str:
    """Human-readable form of a combo genome, e.g. ``rsi(14) > 72.3 AND ema_dev(20) < -0.012`` —
    so a search winner's composed rule is watchable instead of a row of opaque ``ind0=3`` genes."""
    conditions, combine = decode_conditions(params)
    parts = [f"{c.spec.name}({c.period}) {c.op} {c.threshold:g}" for c in conditions]
    return f" {combine.upper()} ".join(parts)
