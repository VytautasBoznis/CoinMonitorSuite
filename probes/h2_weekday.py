"""T0 probe H2 — weekday seasonality in USDC legs (pre-registered, alpha-hunt.md §1.5).

Frozen rule (2026-07-02, before first run): PASS if some weekday's bootstrap 95% CI on the
mean daily log return excludes 0 with the SAME sign on >= 3 of 5 coins. Cross-coin
consistency is the multiple-comparisons guard (35 cells tested).

A bar's return is close_t / close_{t-1} - 1 in log form, attributed to the UTC weekday of
bar t's open_time (the day over which the return accrued). Fixed analysis, no tuning.

Run:  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
      .venv/Scripts/python probes/h2_weekday.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from coinmon.data import db

COINS = ["BTC/USDC", "ETH/USDC", "SOL/USDC", "XRP/USDC", "BNB/USDC"]
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
N_BOOT = 10_000
SEED = 0


def weekday_cis(returns: pd.Series, weekdays: pd.Series, rng: np.random.Generator):
    """Per weekday: (n, mean, lo, hi) with a seeded 10k-resample bootstrap 95% CI."""
    out = {}
    for wd in range(7):
        r = returns[weekdays == wd].to_numpy()
        if len(r) < 30:
            out[wd] = (len(r), np.nan, np.nan, np.nan)
            continue
        draws = rng.choice(r, size=(N_BOOT, len(r)), replace=True).mean(axis=1)
        out[wd] = (len(r), r.mean(), *np.percentile(draws, [2.5, 97.5]))
    return out


def main() -> None:
    rng = np.random.default_rng(SEED)
    conn = db.connect()
    per_coin: dict[str, dict[int, tuple]] = {}
    for coin in COINS:
        candles = db.read_candles(conn, "bybit", coin, "1d")
        ts = pd.to_datetime(candles["open_time"], unit="ms", utc=True)
        logret = np.log(candles["close"]).diff()
        frame = pd.DataFrame({"ret": logret, "wd": ts.dt.weekday}).dropna()
        per_coin[coin] = weekday_cis(frame["ret"], frame["wd"], rng)
    conn.close()

    print(f"{'coin':<10}" + "".join(f"{wd:>22}" for wd in WEEKDAYS))
    sig_sign: dict[int, list[int]] = {wd: [] for wd in range(7)}
    for coin, cis in per_coin.items():
        cells = []
        for wd in range(7):
            n, mean, lo, hi = cis[wd]
            sig = not (np.isnan(lo) or lo <= 0 <= hi)
            if sig:
                sig_sign[wd].append(1 if mean > 0 else -1)
            cells.append(f"{mean * 100:+.3f}% [{lo * 100:+.2f},{hi * 100:+.2f}]{'*' if sig else ' '}")
        print(f"{coin:<10}" + "".join(f"{c:>22}" for c in cells))

    print("\n(* = 95% bootstrap CI excludes 0; means/CIs are % per day, log returns)")
    passing = {
        WEEKDAYS[wd]: signs
        for wd, signs in sig_sign.items()
        if len(signs) >= 3 and abs(sum(signs)) == len(signs)
    }
    if passing:
        print(f"H2 VERDICT: PASS — consistent significant weekday(s): {passing}")
    else:
        best = {WEEKDAYS[wd]: signs for wd, signs in sig_sign.items() if signs}
        print(f"H2 VERDICT: FAIL — no weekday significant with one sign on >=3/5 coins "
              f"(significant cells found: {best or 'none'})")


if __name__ == "__main__":
    main()
