from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from coinmon.backtest.execution import ExecutionModel, IdealExecution
from coinmon.backtest.metrics import summarize
from coinmon.backtest.portfolio import Portfolio
from coinmon.backtest.result import BacktestResult
from coinmon.data.models import Candle
from coinmon.feed import BarView
from coinmon.strategies.base import Strategy


@dataclass(frozen=True, slots=True)
class StepResult:
    """What advancing the black box one closed bar yields.

    ``target`` is the position the strategy now wants (it fills at the NEXT bar's open, so the
    final bar's target never trades). ``position`` is what's actually held after this bar's open
    fill, ``filled`` whether that fill happened, ``equity`` the mark-to-market at this bar's close.
    """

    open_time: int
    close: float
    filled: bool
    position: int
    target: int
    equity: float


class BarStepper:
    """The black box's single-bar state machine: the no-lookahead fill→mark→decide core, shared
    by the batch backtester and the live forward feed so they fill and decide IDENTICALLY (parity
    by construction). One ``step`` per closed bar; state persists across calls, so it doesn't care
    whether bars arrive all at once (backtest) or a few at a time (live polling).
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
        self._position = 0  # held after the latest bar's fill
        self._pending: int | None = None  # target decided last bar, to fill at this bar's open

    def step(self, candle: Candle) -> StepResult:
        """Advance one closed bar: fill last bar's order at this open, mark equity at this close,
        then ask the strategy for the next target. Mirrors one iteration of ``BacktestEngine.run``.
        """
        filled = False
        if self._pending is not None and self._pending != self._position:
            # Buy (+1) when moving more positive, sell (-1) when more negative — so a long->short
            # flip sells, a short->flat buys. For the 0/1 spot path this is the old rule unchanged.
            side = 1 if self._pending > self._position else -1
            fill = self.execution.fill_price(side, candle.open)
            if fill is not None:  # a None fill = order didn't execute; position unchanged
                self.portfolio.rebalance(self._pending, fill)
                self._position = self._pending
                filled = True
        equity = self.portfolio.equity(candle.close)
        self._pending = self.strategy.on_bar(BarView(candle=candle))
        return StepResult(
            open_time=candle.open_time,
            close=candle.close,
            filled=filled,
            position=self._position,
            target=self._pending,
            equity=equity,
        )


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

        stepper = BarStepper(self.strategy, self.portfolio, self.execution)
        equity = []
        bars_in_market = 0
        for row in candles.itertuples(index=False):
            candle = Candle(
                open_time=int(row.open_time),
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=float(row.volume),
            )
            result = stepper.step(candle)
            equity.append(result.equity)
            bars_in_market += abs(result.position)  # held a position when +1 long or -1 short

        curve = pd.Series(
            equity,
            index=pd.Index(candles["open_time"].to_numpy(), name="open_time"),
            name="equity",
        )
        exposure = bars_in_market / len(candles)
        metrics = summarize(curve, self.portfolio.trades, exposure)
        return BacktestResult(equity_curve=curve, metrics=metrics)
