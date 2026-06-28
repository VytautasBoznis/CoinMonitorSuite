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
# (downside, not mere variation) and (b) trading too rarely to be anything but noise.
# See docs/lessons-learned.md "the search overfits, the fixed params survive".


@dataclass(frozen=True)
class FitnessResult:
    fitness: float  # median_oos_return - instability_penalty - trade_penalty (the GA objective)
    median_oos_return: float  # median of the per-fold returns — the central tendency rewarded
    mean_oos_return: float  # mean of the per-fold returns (informational; outlier-sensitive)
    return_std: float  # spread of per-fold returns (informational; not penalized)
    downside_dev: float  # RMS of the negative fold returns — the inconsistency the penalty bites
    total_trades: int  # closed round-trips summed across all folds
    instability_penalty: float
    trade_penalty: float
    fold_returns: list[float]
    fold_trades: list[int]

    def summary(self) -> str:
        per_fold = ", ".join(
            f"{r:+.2%}({t}t)"
            for r, t in zip(self.fold_returns, self.fold_trades, strict=True)
        )
        folds = len(self.fold_returns)
        return (
            f"  fitness            {self.fitness:+.4f}\n"
            f"  median OOS return  {self.median_oos_return:+.2%}  over {folds} folds (drives it)\n"
            f"  mean OOS return    {self.mean_oos_return:+.2%}  (informational)\n"
            f"  downside dev       {self.downside_dev:.2%}  (-{self.instability_penalty:.4f})\n"
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


def evaluate_fitness(
    candles: pd.DataFrame,
    make_strategy: Callable[[], Strategy],
    taker_fee: float,
    *,
    make_portfolio: Callable[[float, float], Portfolio] | None = None,
    folds: int = 4,
    embargo_bars: int = 0,
    initial_capital: float = 10_000.0,
    min_trades: int = 20,
    instability_weight: float = 1.0,
    trade_penalty_weight: float = 1.0,
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
    leveraged ``PerpPortfolio`` factory (chunk K2) so the same OOS rig scores a short.
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
    for start, end in _fold_bounds(n, folds, embargo_bars):
        segment = candles.iloc[start:end].reset_index(drop=True)
        result = BacktestEngine(
            make_strategy(), build_portfolio(initial_capital, taker_fee)
        ).run(segment)
        fold_returns.append(result.metrics["total_return"])
        fold_trades.append(int(result.metrics["trades"]))

    median_return = _robust_center(fold_returns)
    mean_return = statistics.fmean(fold_returns)
    return_std = statistics.pstdev(fold_returns)  # population: well-defined for a single fold
    downside = _downside_dev(fold_returns)
    total_trades = sum(fold_trades)

    instability_penalty = instability_weight * downside
    # min_trades <= 0 disables the trade-count floor (no penalty, no division).
    undertraded = max(0.0, 1.0 - total_trades / min_trades) if min_trades > 0 else 0.0
    trade_penalty = trade_penalty_weight * undertraded
    fitness = median_return - instability_penalty - trade_penalty

    return FitnessResult(
        fitness=fitness,
        median_oos_return=median_return,
        mean_oos_return=mean_return,
        return_std=return_std,
        downside_dev=downside,
        total_trades=total_trades,
        instability_penalty=instability_penalty,
        trade_penalty=trade_penalty,
        fold_returns=fold_returns,
        fold_trades=fold_trades,
    )
