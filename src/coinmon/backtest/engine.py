from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from coinmon.backtest.execution import ExecutionModel, IdealExecution
from coinmon.backtest.metrics import summarize
from coinmon.backtest.portfolio import Portfolio
from coinmon.backtest.result import BacktestResult, TradeRecord
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
        stop_pct: float | None = None,
    ) -> None:
        self.strategy = strategy
        self.portfolio = portfolio
        self.execution = execution or IdealExecution()
        self._stop_pct = stop_pct  # None = no stop (path byte-unchanged); else fraction from entry
        self._position = 0  # held after the latest bar's fill
        self._pending: int | None = None  # target decided last bar, to fill at this bar's open
        self._entry: float | None = None  # fill price of the open position, the stop's reference
        self._stopped_side = 0  # side just stopped out of; suppresses re-entry until signal resets
        self._entry_time: int = 0  # open_time of the bar the current position was entered on
        self._harvested = 0  # closed_trades already turned into records (chunk-U ledger)
        self.trades: list[TradeRecord] = []  # per-trade ledger, one record per closed round-trip

    def step(self, candle: Candle, funding_rate: float | None = None) -> StepResult:
        """Advance one closed bar: fill last bar's order at this open, enforce the intrabar stop,
        charge this bar's perp funding, mark equity at this close, then ask the strategy for the
        next target. Mirrors one iteration of ``BacktestEngine.run``.

        ``funding_rate`` (chunk W3) is this bar's aggregated perp funding rate: it is charged to
        the held position (``apply_funding`` — a no-op for spot) and exposed to the strategy as the
        ``funding_rate`` feature so a carry family can read it point-in-time. ``None`` (the default)
        leaves the path byte-unchanged — no feature, no cashflow.
        """
        filled = False
        if self._pending is not None and self._pending != self._position:
            # Buy (+1) when moving more positive, sell (-1) when more negative — so a long->short
            # flip sells, a short->flat buys. For the 0/1 spot path this is the old rule unchanged.
            side = 1 if self._pending > self._position else -1
            fill = self.execution.fill_price(side, candle.open)
            if fill is not None:  # a None fill = order didn't execute; position unchanged
                self.portfolio.rebalance(self._pending, fill)
                # A flip closes the old position here — record it under its OWN entry time
                # before the new leg's entry overwrites it.
                self._harvest(candle.open_time)
                self._position = self._pending
                if self._position != 0:
                    self._entry = fill
                    self._entry_time = candle.open_time
                else:
                    self._entry = None
                filled = True

        stopped = self._stop_check(candle)
        if funding_rate is not None:  # charge the bar's funding on the position held into the close
            self.portfolio.apply_funding(funding_rate, candle.close)
        equity = self.portfolio.equity(candle.close)
        self._harvest(candle.open_time)  # catch any stop-out / liquidation close this bar
        if funding_rate is None:
            view = BarView(candle=candle)  # byte-unchanged default: no funding feature
        else:
            view = BarView(candle=candle, features={"funding_rate": funding_rate})
        self._pending = self._guard_reentry(self.strategy.on_bar(view))
        return StepResult(
            open_time=candle.open_time,
            close=candle.close,
            filled=filled or stopped,
            position=self._position,
            target=self._pending,
            equity=equity,
        )

    def _harvest(self, exit_time: int) -> None:
        """Turn any portfolio round-trips closed since the last call into ledger records (chunk U),
        tagged with the current position's entry time and this bar's exit time. Called at each
        point a close can happen (a rebalance flip, a stop-out, a liquidation) so each trade is
        attributed to the correct entry bar. Pure bookkeeping — it only reads ``closed_trades``,
        so fills/equity/decisions and thus batch↔live parity are untouched."""
        closed = self.portfolio.closed_trades
        while self._harvested < len(closed):
            econ = closed[self._harvested]
            self.trades.append(
                TradeRecord(
                    entry_time=self._entry_time,
                    exit_time=exit_time,
                    direction=econ.direction,
                    net_return_pct=econ.net_return_pct,
                )
            )
            self._harvested += 1

    def _stop_check(self, candle: Candle) -> bool:
        """If a stop is armed and the bar traded through the stop level, force the position flat at
        that level mid-bar (before equity is marked) and latch the stopped side. The trigger reads
        the bar's low (long) / high (short), both known at close, so no-lookahead holds; the exit is
        routed through the execution model so a stop slips under the fragility harness like a fill.
        Filling at exactly the stop level is a deliberate simplification — a gap THROUGH the stop
        would realize worse, which the fragility slippage draw approximates."""
        if self._stop_pct is None or self._position == 0 or self._entry is None:
            return False
        if self._position == 1:
            level = self._entry * (1.0 - self._stop_pct)
            if candle.low > level:
                return False
            exit_side = -1  # sell to close the long
        else:
            level = self._entry * (1.0 + self._stop_pct)
            if candle.high < level:
                return False
            exit_side = 1  # buy to close the short
        fill = self.execution.fill_price(exit_side, level)
        if fill is None:  # the stop order didn't land this bar; re-checked next bar
            return False
        self.portfolio.rebalance(0, fill)
        self._stopped_side = self._position
        self._position = 0
        self._entry = None
        return True

    def _guard_reentry(self, target: int) -> int:
        """After a stop-out, stay flat while the strategy keeps demanding the side that was stopped;
        resume the moment its signal leaves that side (flips or goes flat). For long/flat spot this
        is the classic 'no immediate re-entry after a stop'; for a ``ShortWhenFlat`` perp (signal is
        always +1/-1) it means a stopped-out short waits for the signal to flip long before re-arm.
        """
        if self._stopped_side == 0:
            return target
        if target == self._stopped_side:
            return 0
        self._stopped_side = 0
        return target


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
        stop_pct: float | None = None,
    ) -> None:
        self.strategy = strategy
        self.portfolio = portfolio
        self.execution = execution or IdealExecution()
        self.stop_pct = stop_pct

    def run(
        self, candles: pd.DataFrame, funding: Sequence[float] | None = None
    ) -> BacktestResult:
        """Replay ``candles`` → equity curve + metrics.

        The no-lookahead discipline is the bar boundary: the strategy decides on the CLOSED
        bar ``t`` and that order only fills at the OPEN of bar ``t+1`` (via the execution
        model). So the final bar's signal never trades — you can't act on a bar still forming.
        Equity is marked to each bar's close after that bar's fill is applied.

        ``funding`` (chunk W3), when given, is a per-bar perp funding rate aligned 1:1 with
        ``candles`` (each bar's aggregated 8h settlements); it is charged to the position and
        exposed as the ``funding_rate`` feature. ``None`` (default) leaves the run byte-unchanged.
        """
        if candles.empty:
            raise ValueError("cannot backtest an empty candle frame")
        # Chunk W3 step 2c: a genome's frame may carry per-bar funding as a ``funding_rate`` column
        # (attached by ``attach_funding`` for direct perps). Extract it here — the single seam — so
        # every fold/holdout/fragility/pool slice, which carries the column through ``.iloc``, gets
        # funding without each caller threading it. An explicit ``funding`` arg wins; no column
        # leaves the run byte-unchanged (parity for every ratio and non-funding series).
        if funding is None and "funding_rate" in candles.columns:
            funding = candles["funding_rate"].to_numpy()
        if funding is not None and len(funding) != len(candles):
            raise ValueError("funding must align 1:1 with candles")

        stepper = BarStepper(self.strategy, self.portfolio, self.execution, self.stop_pct)
        equity = []
        bars_in_market = 0
        for i, row in enumerate(candles.itertuples(index=False)):
            candle = Candle(
                open_time=int(row.open_time),
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=float(row.volume),
            )
            rate = None if funding is None else float(funding[i])
            result = stepper.step(candle, rate)
            equity.append(result.equity)
            bars_in_market += abs(result.position)  # held a position when +1 long or -1 short

        curve = pd.Series(
            equity,
            index=pd.Index(candles["open_time"].to_numpy(), name="open_time"),
            name="equity",
        )
        exposure = bars_in_market / len(candles)
        metrics = summarize(curve, self.portfolio.trades, exposure)
        return BacktestResult(equity_curve=curve, metrics=metrics, trades=stepper.trades)
