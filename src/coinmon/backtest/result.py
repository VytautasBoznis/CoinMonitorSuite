from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd


@dataclass
class BacktestResult:
    """A backtest run's output: equity curve + metrics, with a text summary. Build step 6."""

    equity_curve: pd.Series
    metrics: dict[str, float]

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
