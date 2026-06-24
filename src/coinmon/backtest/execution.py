from __future__ import annotations

from abc import ABC, abstractmethod


class ExecutionModel(ABC):
    """Decides the achieved fill price/outcome for a submitted order. An injectable seam.

    Default ``IdealExecution`` = next-bar open, no slippage. ``StochasticExecution``
    (latency / slippage / fill-failure) is the Phase 1.5 fragility variant.
    """

    @abstractmethod
    def fill_price(self, next_open: float) -> float:
        """Return the achieved fill price for an order given the next bar's open."""
        raise NotImplementedError


class IdealExecution(ExecutionModel):
    """Fills at the next bar's open with no slippage (the no-lookahead baseline)."""

    def fill_price(self, next_open: float) -> float:
        return next_open
