from __future__ import annotations

from abc import ABC, abstractmethod


class Portfolio(ABC):
    """Tracks position, cash and equity as fills happen. An interface from day one.

    Phase 1 ships ``SpotPortfolio`` (long/flat). ``PerpPortfolio`` (long/short + 8h
    funding) is a future impl of this same interface.
    """

    @abstractmethod
    def equity(self, price: float) -> float:
        """Mark-to-market account value at the given price."""
        raise NotImplementedError


class SpotPortfolio(Portfolio):
    """Long/flat spot account. A rotation is two sequential taker fills, both charged.

    Build step 6.
    """

    def equity(self, price: float) -> float:
        raise NotImplementedError("SpotPortfolio.equity — build step 6 (backtest engine)")
