from __future__ import annotations

from abc import ABC, abstractmethod


class ExecutionModel(ABC):
    """Decides the achieved fill for a submitted order. An injectable seam.

    Default ``IdealExecution`` = next-bar open, no slippage, always fills. The Phase 1.5
    ``StochasticExecution`` (latency / slippage / fill-failure) perturbs this as a fragility
    kill-filter. The seam carries the order ``side`` so frictions can be applied *adversely*
    (a buy fills higher, a sell lower) and may return ``None`` to mean the order did not fill.

    The optional ``low``/``high``/``prev_close`` describe the bar the order fills on and the
    previous bar's close; only a limit model (``MakerLimitExecution``, Plan-B probe B9) reads
    them, so the market models ignore them and every existing path stays byte-identical.
    """

    @abstractmethod
    def fill_price(
        self,
        side: int,
        reference: float,
        low: float | None = None,
        high: float | None = None,
        prev_close: float | None = None,
    ) -> float | None:
        """Achieved fill price for an order at ``reference`` (the next bar's open), or ``None``
        if the order did not fill this bar. ``side`` is +1 to buy (flat→long), -1 to sell."""
        raise NotImplementedError


class IdealExecution(ExecutionModel):
    """Fills at the next bar's open with no slippage, always (the no-lookahead baseline)."""

    def fill_price(
        self,
        side: int,
        reference: float,
        low: float | None = None,
        high: float | None = None,
        prev_close: float | None = None,
    ) -> float | None:
        return reference


class MakerLimitExecution(ExecutionModel):
    """Plan-B probe B9: a conservative maker limit-fill. An entry/exit order rests at the PRIOR
    close and fills there only if this bar trades through that price (``low <= prev_close <=
    high``); otherwise the order does not fill and the trade is skipped. When ``prev_close`` is
    absent (the stop-exit call, which passes only the stop level as ``reference``) it falls back
    to filling at ``reference`` — a stop that triggered already traded through its level.

    Optimistic by construction (it ignores queue position and the adverse selection that fills
    you MORE when the move continues against you), so a maker 'edge' from this model funds
    infrastructure work only, never a certificate — see the plan-b §P3 caveat.
    """

    def fill_price(
        self,
        side: int,
        reference: float,
        low: float | None = None,
        high: float | None = None,
        prev_close: float | None = None,
    ) -> float | None:
        if prev_close is None:  # stop-exit passthrough: fill at the triggered level
            return reference
        if low is not None and low <= prev_close <= high:
            return prev_close  # the bar traded through the resting limit
        return None  # gapped past the limit — order unfilled, trade skipped
