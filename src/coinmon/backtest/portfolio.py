from __future__ import annotations

from abc import ABC, abstractmethod


class Portfolio(ABC):
    """Tracks position, cash and equity as fills happen. An interface from day one.

    Phase 1 ships ``SpotPortfolio`` (long/flat). ``PerpPortfolio`` (long/short + 8h
    funding) is a future impl of this same interface.
    """

    # Impls expose ``trades: list[float]`` — the realized PnL of each CLOSED round-trip, in
    # account currency (fees included). A position still open at the end is not a closed trade
    # and never appears here.
    trades: list[float]

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
            self.trades.append(self.cash - self._entry_cash)  # realized round-trip PnL
        self._target = target

    def equity(self, price: float) -> float:
        return self.cash + self.units * price
