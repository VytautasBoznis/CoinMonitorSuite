from __future__ import annotations

from coinmon.backtest.execution import ExecutionModel


class StochasticExecution(ExecutionModel):
    """Phase 1.5 fragility variant: seedable latency / inter-leg gap / slippage / fill
    failure. OFF by default. A kill-filter, not a validation badge — never tune to pass it.
    """

    def fill_price(self, next_open: float) -> float:
        raise NotImplementedError("StochasticExecution — Phase 1.5 (fragility stress test)")


def run_monte_carlo():
    """Replay a strategy N times with different seeds → distribution + fragility metric.

    Phase 1.5.
    """
    raise NotImplementedError("stress.run_monte_carlo — Phase 1.5")
