from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class BacktestResult:
    """A backtest run's output: equity curve + metrics, with a text summary. Build step 6."""

    equity_curve: pd.Series
    metrics: dict[str, float]

    def summary(self) -> str:
        raise NotImplementedError("BacktestResult.summary — build step 6")
