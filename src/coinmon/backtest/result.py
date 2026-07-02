from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd


@dataclass(frozen=True, slots=True)
class TradeRecord:
    """One closed round-trip in the per-trade OOS ledger (chunk U). ``direction`` is +1 long /
    -1 short; ``net_return_pct`` is the realized return on entry collateral, net of both taker-fee
    legs — a trade's *success* is ``net_return_pct > 0``. ``entry_time``/``exit_time`` are the bar
    ``open_time``s of the entry and exit fills, so the pooled ledger stays time-orderable (the
    block-bootstrap and regime bucketing the Edge Certificate needs)."""

    entry_time: int
    exit_time: int
    direction: int
    net_return_pct: float


@dataclass
class BacktestResult:
    """A backtest run's output: equity curve + metrics, with a text summary. Build step 6."""

    equity_curve: pd.Series
    metrics: dict[str, float]
    # The per-trade ledger (chunk U). Purely additive — metrics still reads the PnL floats on the
    # portfolio, so this leaves every existing number byte-identical. One record per CLOSED trade,
    # so ``len(trades) == metrics["trades"]``; an open position at the end never appears.
    trades: list[TradeRecord] = field(default_factory=list)

    # Human-readable label per metric, in display order.
    _LABELS = {
        "total_return": "Total return",
        "max_drawdown": "Max drawdown",
        "calmar": "Calmar",
        "sharpe": "Sharpe (per-bar)",
        "trades": "Trades",
        "exposure": "Exposure",
        "win_rate": "Win rate (per-trade)",
        "profit_factor": "Profit factor",
    }
    # Signed percentages (gain/loss): a leading +/- aids reading.
    _AS_SIGNED_PERCENT = {"total_return", "max_drawdown"}
    # Unsigned percentages.
    _AS_PERCENT = {"exposure", "win_rate"}

    def summary(self) -> str:
        lines = []
        for key, label in self._LABELS.items():
            value = self.metrics[key]
            if math.isnan(value):
                text = "n/a"  # e.g. win rate with no closed trades (buy & hold)
            elif key in self._AS_SIGNED_PERCENT:
                text = f"{value:+.2%}"
            elif key in self._AS_PERCENT:
                text = f"{value:.2%}"
            elif key == "trades":
                text = f"{int(value)}"
            elif math.isinf(value):
                text = "inf"
            else:
                text = f"{value:.2f}"
            lines.append(f"  {label:<22} {text}")
        return "\n".join(lines)
