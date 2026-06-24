from __future__ import annotations

import pandas as pd

from coinmon.backtest.execution import ExecutionModel, IdealExecution
from coinmon.backtest.portfolio import Portfolio
from coinmon.strategies.base import Strategy


class BacktestEngine:
    """Black-box exchange: replays candles bar-by-bar, feeding the strategy only data up
    to the current bar and routing its orders through an injectable ``ExecutionModel`` into
    the ``Portfolio``. Event-driven, no lookahead. Build step 6.
    """

    def __init__(
        self,
        strategy: Strategy,
        portfolio: Portfolio,
        execution: ExecutionModel | None = None,
    ) -> None:
        self.strategy = strategy
        self.portfolio = portfolio
        self.execution = execution or IdealExecution()

    def run(self, candles: pd.DataFrame):
        """Replay candles → equity curve + result. Build step 6."""
        raise NotImplementedError("BacktestEngine.run — build step 6 (backtest engine)")
