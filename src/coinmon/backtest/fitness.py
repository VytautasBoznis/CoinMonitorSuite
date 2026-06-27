from __future__ import annotations

import statistics
from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from coinmon.backtest.engine import BacktestEngine
from coinmon.backtest.portfolio import SpotPortfolio
from coinmon.strategies.base import Strategy

# The scalar a search (the GA north star) maximizes per candidate genome. It is built to make
# the overfit the grid search already demonstrated HARD to repeat: a genome is scored across
# several out-of-sample folds (never one in-sample number), and the raw mean return is then
# docked for (a) inconsistency across folds and (b) trading too rarely to be anything but noise.
# See docs/lessons-learned.md "the search overfits, the fixed params survive".


@dataclass(frozen=True)
class FitnessResult:
    fitness: float  # mean_oos_return - instability_penalty - trade_penalty (the GA objective)
    mean_oos_return: float  # mean of the per-fold returns, before penalties
    return_std: float  # spread of per-fold returns — the inconsistency the penalty bites
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
        return (
            f"  fitness          {self.fitness:+.4f}\n"
            f"  mean OOS return  {self.mean_oos_return:+.2%}  over {len(self.fold_returns)} folds\n"
            f"  return std       {self.return_std:.2%}  (-{self.instability_penalty:.4f})\n"
            f"  total trades     {self.total_trades}  (-{self.trade_penalty:.4f})\n"
            f"  per fold         {per_fold}"
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


def evaluate_fitness(
    candles: pd.DataFrame,
    make_strategy: Callable[[], Strategy],
    taker_fee: float,
    *,
    folds: int = 4,
    embargo_bars: int = 0,
    initial_capital: float = 10_000.0,
    min_trades: int = 20,
    instability_weight: float = 1.0,
    trade_penalty_weight: float = 1.0,
) -> FitnessResult:
    """Score a single fixed genome (``make_strategy``) out-of-sample across ``folds`` segments.

    The genome is never *fitted* here — it is proposed (by a GA, later) and this measures how
    robustly it generalizes. ``fitness = mean_oos_return - instability_weight * return_std -
    trade_penalty``, where ``trade_penalty = trade_penalty_weight * max(0, 1 - total_trades /
    min_trades)``. So a genome that wins big in one fold and bleeds in the others (high std), or
    that barely trades (noise-dominated), is docked toward / below a genome with a steady,
    well-populated edge — which is exactly what the grid-search overfit lacked.
    """
    if folds < 1:
        raise ValueError(f"need at least 1 fold, got {folds}")
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
            make_strategy(), SpotPortfolio(initial_capital, taker_fee)
        ).run(segment)
        fold_returns.append(result.metrics["total_return"])
        fold_trades.append(int(result.metrics["trades"]))

    mean_return = statistics.fmean(fold_returns)
    return_std = statistics.pstdev(fold_returns)  # population: well-defined for a single fold
    total_trades = sum(fold_trades)

    instability_penalty = instability_weight * return_std
    # min_trades <= 0 disables the trade-count floor (no penalty, no division).
    undertraded = max(0.0, 1.0 - total_trades / min_trades) if min_trades > 0 else 0.0
    trade_penalty = trade_penalty_weight * undertraded
    fitness = mean_return - instability_penalty - trade_penalty

    return FitnessResult(
        fitness=fitness,
        mean_oos_return=mean_return,
        return_std=return_std,
        total_trades=total_trades,
        instability_penalty=instability_penalty,
        trade_penalty=trade_penalty,
        fold_returns=fold_returns,
        fold_trades=fold_trades,
    )
