"""Plan-B probe B4 — rebalancing (variance-harvesting) premium (pre-registered, plan-b §P1).

Hypothesis: periodically rebalancing an equal-weight basket back to equal weight harvests a
premium over buy-and-hold that survives fees.

Frozen rule (2026-07-03, before any run): equal-weight basket of the 5 majors; daily and
weekly rebalance vs the SAME-basket buy-and-hold, net of taker fees on rebalance turnover,
over rolling 1-year windows. PASS if the net premium (rebalanced total return - buy-and-hold
total return) > 0 in >= 70% of rolling 1y windows at EITHER cadence. Fixed analysis, no tuning.

B4 caveat (from the plan): this is a portfolio overlay, not a per-trade signal — no trade
ledger, so the Edge Certificate doesn't apply as-is. A PASS funds a design note on certifying
overlays, not a family. The 5 majors are highly correlated, so the harvestable premium here is
a conservative lower bound (a more decorrelated basket would harvest more).

Run:  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
      .venv/Scripts/python probes/b4_rebalance_premium.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from coinmon.config import settings
from coinmon.data import db

MAJORS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
TIMEFRAME = "1d"
FEE = settings.taker_fee  # charged on both sell and buy sides of rebalance turnover
WINDOW = 365  # trading-day rolling window (daily bars)
CADENCES = {"daily": 1, "weekly": 7}


def basket_values(prices: np.ndarray, rebalance_every: int | None) -> np.ndarray:
    """Portfolio value path for an equal-weight basket. ``rebalance_every=None`` = buy-and-hold
    (weights drift forever); an int k rebalances to equal weight every k bars, charging
    FEE * sum|weight change| turnover cost. ``prices`` is (T, N), row 0 is the start."""
    t, n = prices.shape
    rets = prices[1:] / prices[:-1]  # (T-1, N) gross per-bar returns
    w = np.full(n, 1.0 / n)
    value = 1.0
    out = np.empty(t)
    out[0] = value
    for i in range(t - 1):
        contrib = w * rets[i]
        gross = contrib.sum()
        value *= gross
        w = contrib / gross  # drifted weights after the bar
        if rebalance_every is not None and (i + 1) % rebalance_every == 0:
            target = np.full(n, 1.0 / n)
            cost = FEE * np.abs(target - w).sum()
            value *= 1.0 - cost
            w = target
        out[i + 1] = value
    return out


def main() -> None:
    conn = db.connect()
    frames = []
    for sym in MAJORS:
        c = db.read_candles(conn, "binance", sym, TIMEFRAME)[["open_time", "close"]]
        frames.append(c.rename(columns={"close": sym}).set_index("open_time"))
    conn.close()
    px = pd.concat(frames, axis=1, join="inner").sort_index()
    prices = px.to_numpy(dtype=float)
    start = pd.to_datetime(px.index[0], unit="ms").date()
    end = pd.to_datetime(px.index[-1], unit="ms").date()
    print(f"B4 rebalancing premium — 5 majors (Binance USDT) 1d, {len(px)} common bars "
          f"{start}..{end}, fee {FEE}")

    bh = basket_values(prices, None)
    any_pass = False
    for name, k in CADENCES.items():
        rb = basket_values(prices, k)
        rb_win = rb[WINDOW:] / rb[:-WINDOW]        # rebalanced 1y total return per window
        bh_win = bh[WINDOW:] / bh[:-WINDOW]        # buy-and-hold 1y total return per window
        premium = rb_win - bh_win
        frac = float((premium > 0).mean())
        ok = frac >= 0.70
        any_pass |= ok
        print(f"  {name:<7} rebalance: premium>0 in {frac:>6.1%} of {len(premium)} rolling-1y "
              f"windows  mean premium {premium.mean():+.4f}  {'*' if ok else ''}")
    verdict = "PASS" if any_pass else "FAIL"
    print(f"\nB4 VERDICT: {verdict} — need net premium>0 in >=70% of rolling-1y windows at "
          f"either cadence")


if __name__ == "__main__":
    main()
