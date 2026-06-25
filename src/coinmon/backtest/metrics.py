from __future__ import annotations

import math
from collections.abc import Sequence

import pandas as pd


def summarize(
    equity_curve: pd.Series, trades: Sequence[float], exposure: float
) -> dict[str, float]:
    """Curve metrics (return, drawdown, Calmar, Sharpe) plus trade-level stats.

    Crypto returns are fat-tailed, so trust max drawdown / Calmar / profit factor and
    treat Sharpe as low-signal. Sharpe is the raw per-bar mean/std ratio, deliberately
    un-annualized (annualizing fat-tailed bar returns would overstate it).

    ``trades`` is the realized PnL of each CLOSED round-trip, so win rate / profit factor /
    trade count are PER TRADE — the meaningful read. An open position at the end isn't a
    closed trade and isn't counted (so a buy-and-hold benchmark shows 0 trades, ~100%
    exposure, and n/a win rate — it never completes a round-trip). ``exposure`` is the
    fraction of bars holding a position.
    """
    returns = equity_curve.pct_change().dropna()
    total_return = equity_curve.iloc[-1] / equity_curve.iloc[0] - 1.0

    running_max = equity_curve.cummax()
    max_drawdown = (equity_curve / running_max - 1.0).min()

    calmar = total_return / abs(max_drawdown) if max_drawdown < 0 else math.inf
    std = returns.std()
    sharpe = returns.mean() / std if std > 0 else 0.0

    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t < 0]
    win_rate = len(wins) / len(trades) if trades else math.nan
    gross_profit = sum(wins)
    gross_loss = -sum(losses)
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    elif gross_profit > 0:
        profit_factor = math.inf  # winners, no losers
    else:
        profit_factor = math.nan  # no closed trades

    return {
        "total_return": float(total_return),
        "max_drawdown": float(max_drawdown),
        "calmar": float(calmar),
        "sharpe": float(sharpe),
        "trades": float(len(trades)),
        "exposure": float(exposure),
        "win_rate": float(win_rate),
        "profit_factor": float(profit_factor),
    }
