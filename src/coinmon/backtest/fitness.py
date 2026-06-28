from __future__ import annotations

import math
import statistics
from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from coinmon.backtest.engine import BacktestEngine
from coinmon.backtest.portfolio import Portfolio, SpotPortfolio
from coinmon.strategies.base import Strategy

# The scalar a search (the GA north star) maximizes per candidate genome. It is built to make
# the overfit the grid search already demonstrated HARD to repeat: a genome is scored across
# several out-of-sample folds (never one in-sample number), the MEDIAN fold return (robust to a
# single lucky fold) is rewarded, and it is then docked for (a) losing money in any fold
# (downside, not mere variation), (b) trading too rarely to be anything but noise, and (c) riding
# any fold into a deep drawdown — a convex, recovery-asymmetry penalty (chunk L) that makes the
# search pay honestly for the tail risk leverage introduces instead of chasing blow-ups.
# See docs/lessons-learned.md "the search overfits, the fixed params survive".


@dataclass(frozen=True)
class FitnessResult:
    fitness: float  # median_return - instability - trade_penalty - drawdown_penalty (GA objective)
    median_oos_return: float  # median of the per-fold returns — the central tendency rewarded
    mean_oos_return: float  # mean of the per-fold returns (informational; outlier-sensitive)
    return_std: float  # spread of per-fold returns (informational; not penalized)
    downside_dev: float  # RMS of the negative fold returns — the inconsistency the penalty bites
    worst_drawdown: float  # deepest single-fold max drawdown (magnitude) — drives the DD penalty
    total_trades: int  # closed round-trips summed across all folds
    instability_penalty: float
    trade_penalty: float
    drawdown_penalty: float
    fold_returns: list[float]
    fold_trades: list[int]
    fold_drawdowns: list[float]  # per-fold max drawdown magnitudes (0..1; 1.0 == liquidated)

    def summary(self) -> str:
        per_fold = ", ".join(
            f"{r:+.2%}({t}t,{d:.0%}dd)"
            for r, t, d in zip(
                self.fold_returns, self.fold_trades, self.fold_drawdowns, strict=True
            )
        )
        folds = len(self.fold_returns)
        return (
            f"  fitness            {self.fitness:+.4f}\n"
            f"  median OOS return  {self.median_oos_return:+.2%}  over {folds} folds (drives it)\n"
            f"  mean OOS return    {self.mean_oos_return:+.2%}  (informational)\n"
            f"  downside dev       {self.downside_dev:.2%}  (-{self.instability_penalty:.4f})\n"
            f"  worst drawdown     {self.worst_drawdown:.2%}  (-{self.drawdown_penalty:.4f})\n"
            f"  return std         {self.return_std:.2%}  (spread; not penalized)\n"
            f"  total trades       {self.total_trades}  (-{self.trade_penalty:.4f})\n"
            f"  per fold           {per_fold}"
        )


def _fold_bounds(n: int, folds: int, embargo_bars: int) -> list[tuple[int, int]]:
    """Split ``n`` bars into ``folds`` contiguous equal-ish segments, dropping ``embargo_bars``
    from the START of every fold after the first. The embargo purges the autocorrelated bars
    straddling each boundary so the per-fold scores are more independent — the same purge idea
    as the walk-forward, applied to scoring a single fixed genome."""
    size = n // folds
    bounds = []
    for i in range(folds):
        start = i * size
        end = n if i == folds - 1 else (i + 1) * size
        if i > 0:
            start += embargo_bars
        bounds.append((start, end))
    return bounds


def _robust_center(returns: list[float]) -> float:
    """Median of the per-fold returns — the central tendency the fitness rewards. Robust to a
    single outsized fold: with 4 folds it is the mean of the middle two, so neither the best nor
    the worst fold can carry a genome. The plain mean could not: a live search topped its
    population with a genome whose +94% mean was one +355% fold among +19% / -35% / +39% — the
    graduation gate then rejected it OOS. Rewarding the median makes the search spend its budget
    on steadily-positive genomes instead of one-lucky-fold spikes."""
    return statistics.median(returns)


def _downside_dev(returns: list[float]) -> float:
    """Root-mean-square of the *negative* fold returns (positive folds contribute 0). Zero
    exactly when every fold is non-negative, so a genome that wins in every fold pays no
    instability penalty — unlike a symmetric std, which docks a genome merely for varying in
    size (the chunk-A miscalibration this replaces)."""
    return math.sqrt(statistics.fmean([min(0.0, r) ** 2 for r in returns]))


# Drawdowns at/above this magnitude are treated as ruin: their recovery gain is capped here so a
# liquidated fold (drawdown == 1.0, which would need an infinite gain back) yields a large but
# finite catastrophic penalty (g(0.99) = 99) instead of an inf that would break GA ordering.
_DRAWDOWN_RUIN_CAP = 0.99


def _recovery_gain(drawdown: float) -> float:
    """The gain needed to climb back from a max drawdown of ``drawdown`` (0..1): ``d / (1 - d)``.
    This is the REAL asymmetry of a loss — down 20% needs +25%, down 50% needs +100%, down 80%
    needs +400% — so it is naturally convex and explodes toward total loss. Anchoring the penalty
    to it (rather than a hand-picked exponent) is why deep drawdowns cost super-linearly while a
    shallow one barely registers. Capped at ``_DRAWDOWN_RUIN_CAP`` so liquidation stays finite."""
    return _DRAWDOWN_RUIN_CAP / (1.0 - _DRAWDOWN_RUIN_CAP) if drawdown >= _DRAWDOWN_RUIN_CAP \
        else drawdown / (1.0 - drawdown)


def _drawdown_penalty(drawdowns: list[float], band: float) -> float:
    """Convex penalty driven by the WORST fold's drawdown, measured as recovery-gain ABOVE a
    tolerance ``band``: ``max_t(recovery_gain(d_t) - recovery_gain(band))``, floored at 0. Inside
    the band (e.g. a routine -25/-30% dip) it is zero; past it the recovery asymmetry bites hard,
    and a liquidating fold (d == 1) is near-catastrophic. The WORST fold drives it — not an average
    — so one ruinous fold sinks the genome and can't be diluted by lucky folds (the exact failure
    of the leverage-blind fitness: it rewarded a 4.6x short whose -100% fold averaged away)."""
    floor = _recovery_gain(band)
    return max((max(0.0, _recovery_gain(d) - floor) for d in drawdowns), default=0.0)


def evaluate_fitness(
    candles: pd.DataFrame,
    make_strategy: Callable[[], Strategy],
    taker_fee: float,
    *,
    make_portfolio: Callable[[float, float], Portfolio] | None = None,
    stop_pct: float | None = None,
    folds: int = 4,
    embargo_bars: int = 0,
    initial_capital: float = 10_000.0,
    min_trades: int = 20,
    instability_weight: float = 1.0,
    trade_penalty_weight: float = 1.0,
    drawdown_weight: float = 1.0,
    drawdown_band: float = 0.30,
) -> FitnessResult:
    """Score a single fixed genome (``make_strategy``) out-of-sample across ``folds`` segments.

    The genome is never *fitted* here — it is proposed (by a GA, later) and this measures how
    robustly it generalizes. ``fitness = median_oos_return - instability_weight * downside_dev -
    trade_penalty``, where ``downside_dev = sqrt(mean(min(0, fold_return)^2))`` and
    ``trade_penalty = trade_penalty_weight * max(0, 1 - total_trades / min_trades)``. The central
    term is the MEDIAN fold return, not the mean, so a single outsized fold cannot carry a genome
    (the mean let a +355% fold do exactly that in a live search). A genome that bleeds in some
    folds (deep downside) or barely trades (noise-dominated) is docked below one with a steady,
    well-populated edge. Crucially the penalty is DOWNSIDE, not symmetric std: a genome that is
    positive in every fold pays zero instability — fixing the chunk-A miscalibration where a
    green-every-fold pair (XRP/ETH) scored below zero purely for varying.

    ``make_portfolio`` is a ``(cash, taker_fee) -> Portfolio`` factory; it defaults to the long/flat
    ``SpotPortfolio`` so existing callers are unchanged, but a directional genome supplies a
    leveraged ``PerpPortfolio`` factory (chunk K2) so the same OOS rig scores a short. ``stop_pct``
    (chunk L) arms the engine's intrabar stop for every fold — the brake that lets a leveraged book
    cut its drawdown so the ``drawdown_penalty`` stops sinking it; ``None`` keeps the unbraked path.

    The ``drawdown_penalty`` (chunk L) subtracts a convex term anchored to recovery asymmetry: the
    WORST fold's max drawdown beyond ``drawdown_band`` is charged ``recovery_gain(d) -
    recovery_gain(band)`` (down 50% needs +100% back; liquidation is near-catastrophic). This is the
    fitness-side answer to leverage: leverage stays a free gene, but a genome that rides a position
    to ruin pays super-linearly, so the search only keeps leverage that comes with survivable
    drawdowns. It bites SELECTION only — the simulated equity stays a truthful mirror of the
    exchange (no synthetic loss multiplier), so a graduated genome trades the same numbers live.
    """
    if folds < 1:
        raise ValueError(f"need at least 1 fold, got {folds}")
    build_portfolio = make_portfolio or (lambda cash, fee: SpotPortfolio(cash, fee))
    n = len(candles)
    if n // folds <= embargo_bars:
        raise ValueError(
            f"{folds} folds of ~{n // folds} bars cannot absorb a {embargo_bars}-bar embargo"
        )

    fold_returns: list[float] = []
    fold_trades: list[int] = []
    fold_drawdowns: list[float] = []
    for start, end in _fold_bounds(n, folds, embargo_bars):
        segment = candles.iloc[start:end].reset_index(drop=True)
        result = BacktestEngine(
            make_strategy(), build_portfolio(initial_capital, taker_fee), stop_pct=stop_pct
        ).run(segment)
        fold_returns.append(result.metrics["total_return"])
        fold_trades.append(int(result.metrics["trades"]))
        fold_drawdowns.append(-result.metrics["max_drawdown"])  # store as a positive magnitude

    median_return = _robust_center(fold_returns)
    mean_return = statistics.fmean(fold_returns)
    return_std = statistics.pstdev(fold_returns)  # population: well-defined for a single fold
    downside = _downside_dev(fold_returns)
    worst_drawdown = max(fold_drawdowns, default=0.0)
    total_trades = sum(fold_trades)

    instability_penalty = instability_weight * downside
    # min_trades <= 0 disables the trade-count floor (no penalty, no division).
    undertraded = max(0.0, 1.0 - total_trades / min_trades) if min_trades > 0 else 0.0
    trade_penalty = trade_penalty_weight * undertraded
    drawdown_penalty = drawdown_weight * _drawdown_penalty(fold_drawdowns, drawdown_band)
    fitness = median_return - instability_penalty - trade_penalty - drawdown_penalty

    return FitnessResult(
        fitness=fitness,
        median_oos_return=median_return,
        mean_oos_return=mean_return,
        return_std=return_std,
        downside_dev=downside,
        worst_drawdown=worst_drawdown,
        total_trades=total_trades,
        instability_penalty=instability_penalty,
        trade_penalty=trade_penalty,
        drawdown_penalty=drawdown_penalty,
        fold_returns=fold_returns,
        fold_trades=fold_trades,
        fold_drawdowns=fold_drawdowns,
    )
