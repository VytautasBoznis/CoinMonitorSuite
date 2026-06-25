from __future__ import annotations

import pandas as pd

from coinmon.backtest.execution import ExecutionModel, IdealExecution
from coinmon.backtest.metrics import summarize
from coinmon.backtest.portfolio import Portfolio
from coinmon.backtest.result import BacktestResult
from coinmon.data.models import Candle
from coinmon.feed import BarView
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

    def run(self, candles: pd.DataFrame) -> BacktestResult:
        """Replay ``candles`` → equity curve + metrics.

        The no-lookahead discipline is the bar boundary: the strategy decides on the CLOSED
        bar ``t`` and that order only fills at the OPEN of bar ``t+1`` (via the execution
        model). So the final bar's signal never trades — you can't act on a bar still forming.
        Equity is marked to each bar's close after that bar's fill is applied.
        """
        if candles.empty:
            raise ValueError("cannot backtest an empty candle frame")

        equity = []
        position = 0  # currently held position, after this bar's fill
        bars_in_market = 0
        pending: int | None = None  # target decided last bar, to fill at this bar's open
        for row in candles.itertuples(index=False):
            if pending is not None:
                fill = self.execution.fill_price(row.open)
                self.portfolio.rebalance(pending, fill)
                position = pending
            equity.append(self.portfolio.equity(row.close))
            bars_in_market += position  # position is 1 long / 0 flat

            candle = Candle(
                open_time=int(row.open_time),
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=float(row.volume),
            )
            pending = self.strategy.on_bar(BarView(candle=candle))

        curve = pd.Series(
            equity,
            index=pd.Index(candles["open_time"].to_numpy(), name="open_time"),
            name="equity",
        )
        exposure = bars_in_market / len(candles)
        metrics = summarize(curve, self.portfolio.trades, exposure)
        return BacktestResult(equity_curve=curve, metrics=metrics)
