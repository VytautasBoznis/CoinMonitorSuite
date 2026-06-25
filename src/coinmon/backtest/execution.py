from __future__ import annotations

from abc import ABC, abstractmethod


class ExecutionModel(ABC):
    """Decides the achieved fill for a submitted order. An injectable seam.

    Default ``IdealExecution`` = next-bar open, no slippage, always fills. The Phase 1.5
    ``StochasticExecution`` (latency / slippage / fill-failure) perturbs this as a fragility
    kill-filter. The seam carries the order ``side`` so frictions can be applied *adversely*
    (a buy fills higher, a sell lower) and may return ``None`` to mean the order did not fill.
    """

    @abstractmethod
    def fill_price(self, side: int, reference: float) -> float | None:
        """Achieved fill price for an order at ``reference`` (the next bar's open), or ``None``
        if the order did not fill this bar. ``side`` is +1 to buy (flat→long), -1 to sell."""
        raise NotImplementedError


class IdealExecution(ExecutionModel):
    """Fills at the next bar's open with no slippage, always (the no-lookahead baseline)."""

    def fill_price(self, side: int, reference: float) -> float | None:
        return reference
