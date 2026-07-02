from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ClosedTrade:
    """The economics of one closed round-trip the portfolio can attribute on its own: the
    position's ``direction`` (+1 long / -1 short) and ``net_return_pct`` (realized PnL / entry
    collateral, net of both taker-fee legs). Recorded in lockstep with ``trades``; the engine
    (which knows the bar times) pairs it into a ``TradeRecord`` for the chunk-U ledger."""

    direction: int
    net_return_pct: float


class Portfolio(ABC):
    """Tracks position, cash and equity as fills happen. An interface from day one.

    Phase 1 ships ``SpotPortfolio`` (long/flat). ``PerpPortfolio`` (long/short + 8h
    funding) is a future impl of this same interface.
    """

    # Impls expose ``trades: list[float]`` — the realized PnL of each CLOSED round-trip, in
    # account currency (fees included). A position still open at the end is not a closed trade
    # and never appears here.
    trades: list[float]
    # ``closed_trades`` mirrors ``trades`` one-for-one with the (direction, net_return_pct) the
    # engine needs to build the chunk-U ledger — economics the portfolio knows but times it doesn't.
    closed_trades: list[ClosedTrade]

    @abstractmethod
    def rebalance(self, target: int, price: float) -> None:
        """Move the position toward ``target`` (Phase 1: 1 long / 0 flat) at ``price``,
        charging the realized cost of any fill. A no-op when already at ``target``."""
        raise NotImplementedError

    @abstractmethod
    def equity(self, price: float) -> float:
        """Mark-to-market account value at the given price."""
        raise NotImplementedError


class SpotPortfolio(Portfolio):
    """Long/flat spot account. A rotation is two sequential taker fills, both charged.

    Holds either ``cash`` (USDC) or ``units`` of the asset, never partial — Phase 1 trades
    all-in/all-out. Entering long spends all cash on units (minus taker fee); going flat
    sells all units back to cash (minus taker fee). So a full in-and-out round trip pays two
    taker fees, exactly the round-trip cost a strategy's no-trade band must clear. This is the
    REALIZED cost charged after the fill — never fed back into the strategy's decision.

    Build step 6.
    """

    def __init__(self, cash: float, taker_fee: float) -> None:
        self.cash = cash
        self.units = 0.0
        self.taker_fee = taker_fee
        self._target = 0
        self._entry_cash = 0.0  # cash spent opening the current long, to PnL it on exit
        self.trades: list[float] = []
        self.closed_trades: list[ClosedTrade] = []

    def rebalance(self, target: int, price: float) -> None:
        if target == self._target:
            return
        if target == 1:  # flat -> long: spend all cash on units, net of taker fee
            self._entry_cash = self.cash
            self.units = self.cash * (1.0 - self.taker_fee) / price
            self.cash = 0.0
        else:  # long -> flat: sell all units back to cash, net of taker fee
            self.cash = self.units * price * (1.0 - self.taker_fee)
            self.units = 0.0
            pnl = self.cash - self._entry_cash  # realized round-trip PnL
            self.trades.append(pnl)
            self.closed_trades.append(ClosedTrade(1, pnl / self._entry_cash))
        self._target = target

    def equity(self, price: float) -> float:
        return self.cash + self.units * price


class PerpPortfolio(Portfolio):
    """Long / flat / short USDT-perp account with isolated, all-in leverage — the bearish-leg
    capability spot can't give (a long/flat account can only sidestep a downtrend; a short
    profits from it). The whole account is the margin for one position (all-in, like the spot
    book): going long or short opens a position of notional = ``equity * leverage``, paying a
    taker fee on that notional; the opposite or flat target closes it, paying the exit taker fee
    and realizing the round-trip PnL. ``target`` is +1 long / 0 flat / -1 short.

    PnL on an open position is ``units * (price - entry)`` with ``units`` signed, so a short
    (units < 0) gains as price falls. Leverage L multiplies both gain and loss, so an adverse
    move of ~1/L wipes the collateral: ``equity`` latches an **isolated-margin liquidation** the
    first bar the mark hits zero (collateral gone, position force-closed, the loss booked as a
    trade, the account dead for the rest of the run). Simplifications kept honest for a first
    model: liquidation is checked on the bar CLOSE only (an intrabar wick that liquidates then
    recovers is missed), no maintenance-margin buffer (liq at mark <= 0, marginally generous),
    and no funding. The eval rig (OOS fitness + fragility + holdout) is what punishes reckless
    leverage — not a hand-tuned cap here.
    """

    def __init__(self, cash: float, taker_fee: float, leverage: float = 1.0) -> None:
        if leverage < 1.0:
            raise ValueError("leverage must be >= 1.0")
        self.cash = cash
        self.units = 0.0  # signed: + long, - short; 0 when flat
        self.taker_fee = taker_fee
        self.leverage = leverage
        self._target = 0
        self._entry_price = 0.0
        self._entry_equity = 0.0  # collateral at entry, to PnL the round-trip on close
        self._liquidated = False
        self.trades: list[float] = []
        self.closed_trades: list[ClosedTrade] = []

    def rebalance(self, target: int, price: float) -> None:
        if self._liquidated or target == self._target:
            return
        if self._target != 0:  # close the open position: realize PnL, then pay the exit fee
            self.cash += self.units * (price - self._entry_price)
            self.cash -= abs(self.units) * price * self.taker_fee
            pnl = self.cash - self._entry_equity  # realized round-trip PnL
            self.trades.append(pnl)
            direction = 1 if self.units > 0 else -1  # captured before the position is zeroed
            self.closed_trades.append(ClosedTrade(direction, pnl / self._entry_equity))
            self.units = 0.0
        if target != 0:  # open a leveraged position, paying the entry fee on the notional
            self._entry_equity = self.cash
            notional = self.cash * self.leverage
            self.cash -= notional * self.taker_fee
            self.units = (notional / price) * (1.0 if target == 1 else -1.0)
            self._entry_price = price
        self._target = target

    def equity(self, price: float) -> float:
        if self._target == 0:
            return self.cash
        mark = self.cash + self.units * (price - self._entry_price)
        if mark <= 0.0 and not self._liquidated:  # isolated-margin liquidation: collateral gone
            self.trades.append(-self._entry_equity)
            self.closed_trades.append(ClosedTrade(1 if self.units > 0 else -1, -1.0))
            self.cash = 0.0
            self.units = 0.0
            self._target = 0
            self._liquidated = True
            return 0.0
        return mark
