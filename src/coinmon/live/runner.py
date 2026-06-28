from __future__ import annotations

from collections.abc import Iterable

from coinmon.backtest.engine import BarStepper, StepResult
from coinmon.backtest.execution import ExecutionModel
from coinmon.backtest.portfolio import Portfolio
from coinmon.data.models import Candle
from coinmon.strategies.base import Strategy


class ForwardRunner:
    """Drives one strategy forward through the shared ``BarStepper`` as closed bars arrive from a
    ``LiveFeed``, tracking position + equity statefully across polls. Because it uses the engine's
    execution core, feeding a series here reproduces ``BacktestEngine`` exactly — and it does so
    regardless of how the bars are batched, so live polling and a one-shot replay agree (parity).
    The strategy and portfolio are stateful and must be fresh (one ``ForwardRunner`` per run)."""

    def __init__(
        self,
        strategy: Strategy,
        portfolio: Portfolio,
        execution: ExecutionModel | None = None,
    ) -> None:
        self._stepper = BarStepper(strategy, portfolio, execution)
        self.signals: list[StepResult] = []

    def feed(self, candles: Iterable[Candle]) -> list[StepResult]:
        """Advance through ``candles`` (a poll's worth of new bars), returning just this batch's
        results; all results so far accumulate in ``self.signals``."""
        batch = [self._stepper.step(c) for c in candles]
        self.signals.extend(batch)
        return batch

    @property
    def latest(self) -> StepResult | None:
        """The most recent bar's result, or ``None`` before any bar is fed."""
        return self.signals[-1] if self.signals else None
