"""Plan-B probe B1 — post-shock reversal (pre-registered, .claude/plans/alpha-hunt-plan-b.md §P1).

Hypothesis: a >=2-sigma down 4h bar overreacts and bounces.

Frozen rule (2026-07-03, before any run): per major, shock = 4h log return < -2*sigma
(rolling 90-bar sigma, point-in-time — trailing, excludes the shock bar). Event study of the
cumulative forward log return (CAR) over the next 1/3/6 bars, 10k seeded bootstrap 95% CI on
the mean. PASS if the 3-bar CAR CI excludes 0 on the POSITIVE side AND mean 3-bar CAR > 1x
round-trip cost, on >= 3 of the 5 majors. Fixed analysis, no tuning, no threshold search.

Majors = BTC/ETH/SOL/BNB/XRP on Binance USDT (deep history), read from the local DB.

Run:  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
      .venv/Scripts/python probes/b1_shock_reversal.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from coinmon.config import settings
from coinmon.data import db

MAJORS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
TIMEFRAME = "4h"
VOL_WINDOW = 90
SHOCK_Z = -2.0
HORIZONS = (1, 3, 6)
ROUND_TRIP = 2 * settings.taker_fee  # honest in-and-out taker cost the bounce must clear
N_BOOT = 10_000
SEED = 0


def boot_mean_ci(x: np.ndarray, rng: np.random.Generator) -> tuple[float, float]:
    draws = rng.choice(x, size=(N_BOOT, len(x)), replace=True).mean(axis=1)
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return float(lo), float(hi)


def main() -> None:
    rng = np.random.default_rng(SEED)
    conn = db.connect()
    print(f"B1 post-shock reversal — {TIMEFRAME} majors (Binance USDT), "
          f"shock = ret < {SHOCK_Z}*sigma_{VOL_WINDOW}, round-trip cost {ROUND_TRIP:.4f}")
    header = f"{'sym':<10}{'events':>7}" + "".join(f"{f'CAR{h}':>9}" for h in HORIZONS)
    print(header + f"{'3b 95% CI':>20}  pass")
    passes = 0
    for sym in MAJORS:
        c = db.read_candles(conn, "binance", sym, TIMEFRAME)
        logret = np.log(c["close"].to_numpy())
        logret = np.concatenate([[np.nan], np.diff(logret)])  # ret_t = log(c_t/c_{t-1})
        r = pd.Series(logret)
        sigma = r.rolling(VOL_WINDOW).std().shift(1)  # trailing, excludes bar t (point-in-time)
        shock = (r < SHOCK_Z * sigma).to_numpy()

        n = len(r)
        idx = np.where(shock)[0]
        idx = idx[idx + max(HORIZONS) < n]  # keep only events with full forward window
        cars = {h: np.array([logret[i + 1 : i + 1 + h].sum() for i in idx]) for h in HORIZONS}

        car3 = cars[3]
        lo, hi = boot_mean_ci(car3, rng)
        ok = lo > 0 and car3.mean() > ROUND_TRIP
        passes += ok
        row = f"{sym:<10}{len(idx):>7}" + "".join(f"{cars[h].mean():>+9.4f}" for h in HORIZONS)
        print(row + f"{f'[{lo:+.4f},{hi:+.4f}]':>20}  {'*' if ok else ''}")
    conn.close()

    verdict = "PASS" if passes >= 3 else "FAIL"
    print(f"\nB1 VERDICT: {verdict} — 3-bar CAR CI>0 and mean>round-trip on {passes}/5 majors "
          f"(need >=3)")


if __name__ == "__main__":
    main()
