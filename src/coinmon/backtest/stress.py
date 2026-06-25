from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from coinmon.backtest.engine import BacktestEngine
from coinmon.backtest.execution import ExecutionModel
from coinmon.backtest.portfolio import Portfolio
from coinmon.strategies.base import Strategy


class StochasticExecution(ExecutionModel):
    """Phase 1.5 fragility variant: seedable adverse slippage + fill failure. OFF by default.

    A kill-filter, not a validation badge — never tune to pass it; failing is a red flag,
    passing is not a live-ready green light. In a historical backtest "data lag" and
    "execution lag" are the same mechanism (acting later on a stale price), so latency, spread
    and impact are modeled once as a single adverse slippage draw — always against the order
    (a buy fills higher, a sell lower). ``fail_prob`` drops the fill entirely (the order didn't
    land this bar); the strategy re-issues next bar, capturing the cost of a missed rotation.
    """

    def __init__(self, max_slippage: float, fail_prob: float, rng: np.random.Generator) -> None:
        self.max_slippage = max_slippage
        self.fail_prob = fail_prob
        self.rng = rng

    def fill_price(self, side: int, reference: float) -> float | None:
        if self.rng.random() < self.fail_prob:
            return None  # order didn't fill this bar
        slip = self.rng.uniform(0.0, self.max_slippage)  # >= 0, applied adversely via side
        return reference * (1.0 + side * slip)


@dataclass
class MonteCarloResult:
    """Distribution of total return across N perturbed runs + the fragility read.

    The headline fragility metric is the fraction of runs that still clear the bar (positive,
    and beating buy-and-hold if a benchmark is given). A strategy whose edge evaporates under
    small realistic frictions is fragile — the whole point of the filter.
    """

    returns: list[float]
    benchmark_return: float | None

    @property
    def runs(self) -> int:
        return len(self.returns)

    @property
    def fraction_positive(self) -> float:
        return float(np.mean([r > 0 for r in self.returns]))

    @property
    def fraction_beating_benchmark(self) -> float | None:
        if self.benchmark_return is None:
            return None
        return float(np.mean([r > self.benchmark_return for r in self.returns]))

    def summary(self) -> str:
        pct = np.percentile(self.returns, [5, 50, 95])
        lines = [
            f"  Runs                   {self.runs}",
            f"  Return  p5 / p50 / p95 {pct[0]:+.2%} / {pct[1]:+.2%} / {pct[2]:+.2%}",
            f"  % runs positive        {self.fraction_positive:.2%}",
        ]
        if self.benchmark_return is not None:
            lines.append(f"  % runs beat B&H        {self.fraction_beating_benchmark:.2%}")
        return "\n".join(lines)


def run_monte_carlo(
    make_strategy: Callable[[], Strategy],
    make_portfolio: Callable[[], Portfolio],
    candles: pd.DataFrame,
    *,
    runs: int = 200,
    max_slippage: float = 0.0005,
    fail_prob: float = 0.01,
    seed: int = 0,
    benchmark_return: float | None = None,
) -> MonteCarloResult:
    """Replay the strategy ``runs`` times under independent, reproducible ``StochasticExecution``
    draws and collect the total-return distribution.

    Factories (not instances) are taken because both ``Strategy`` and ``Portfolio`` carry
    per-run state — each run needs a fresh pair. ``benchmark_return`` is buy-and-hold's
    total return (under ideal execution); pass it to get the "% of runs beating B&H" read.
    """
    children = np.random.SeedSequence(seed).spawn(runs)
    returns = []
    for child in children:
        execution = StochasticExecution(max_slippage, fail_prob, np.random.default_rng(child))
        result = BacktestEngine(make_strategy(), make_portfolio(), execution).run(candles)
        returns.append(result.metrics["total_return"])
    return MonteCarloResult(returns=returns, benchmark_return=benchmark_return)
