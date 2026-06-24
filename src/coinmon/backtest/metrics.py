from __future__ import annotations

import pandas as pd


def summarize(equity_curve: pd.Series) -> dict[str, float]:
    """Total return, win rate, max drawdown, profit factor, Calmar and Sharpe.

    Crypto returns are fat-tailed, so trust max drawdown / Calmar / profit factor and
    treat Sharpe as low-signal. Build step 6.
    """
    raise NotImplementedError("metrics.summarize — build step 6")
