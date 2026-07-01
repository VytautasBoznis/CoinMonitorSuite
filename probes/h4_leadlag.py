"""T0 probe H4 — does BTC's daily move lead alts by one day? (pre-registered, alpha-hunt.md §1.5)

Frozen rule (2026-07-02, before first run): PASS if corr(BTC ret_t, alt ret_{t+1}) has a
bootstrap 95% CI excluding 0 with the SAME sign on >= 2 of 4 alts. Lag-0 correlation is
reported for context only (it is beta, not lead-lag). Fixed analysis, no tuning.

Run:  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
      .venv/Scripts/python probes/h4_leadlag.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from coinmon.data import db

ALTS = ["ETH/USDC", "SOL/USDC", "XRP/USDC", "BNB/USDC"]
N_BOOT = 10_000
SEED = 0


def log_returns(conn, coin: str) -> pd.Series:
    candles = db.read_candles(conn, "bybit", coin, "1d")
    ret = np.log(candles["close"]).diff()
    ret.index = pd.to_datetime(candles["open_time"], unit="ms", utc=True)
    return ret.dropna()


def boot_corr_ci(x: np.ndarray, y: np.ndarray, rng: np.random.Generator):
    """Pearson corr + seeded pairs-bootstrap 95% CI."""
    n = len(x)
    idx = rng.integers(0, n, size=(N_BOOT, n))
    xs, ys = x[idx], y[idx]
    xs = xs - xs.mean(axis=1, keepdims=True)
    ys = ys - ys.mean(axis=1, keepdims=True)
    corrs = (xs * ys).sum(axis=1) / np.sqrt((xs**2).sum(axis=1) * (ys**2).sum(axis=1))
    return float(np.corrcoef(x, y)[0, 1]), *np.percentile(corrs, [2.5, 97.5])


def main() -> None:
    rng = np.random.default_rng(SEED)
    conn = db.connect()
    btc = log_returns(conn, "BTC/USDC")
    print(f"{'alt':<10}{'n':>6}{'lag-0 corr':>12}{'lag-1 corr':>12}{'lag-1 95% CI':>20}  sig")
    signs = []
    for alt in ALTS:
        ret = log_returns(conn, alt)
        joined = pd.DataFrame({"btc": btc, "alt": ret}).dropna()
        lag0 = float(np.corrcoef(joined["btc"], joined["alt"])[0, 1])
        # lead-lag: BTC at t vs alt at t+1
        x = joined["btc"].to_numpy()[:-1]
        y = joined["alt"].to_numpy()[1:]
        corr, lo, hi = boot_corr_ci(x, y, rng)
        sig = not lo <= 0 <= hi
        if sig:
            signs.append(1 if corr > 0 else -1)
        print(f"{alt:<10}{len(x):>6}{lag0:>12.3f}{corr:>12.3f}"
              f"{f'[{lo:+.3f},{hi:+.3f}]':>20}  {'*' if sig else ''}")
    conn.close()

    if len(signs) >= 2 and abs(sum(signs)) == len(signs):
        print(f"\nH4 VERDICT: PASS — lag-1 significant with one sign on {len(signs)}/4 alts")
    else:
        print(f"\nH4 VERDICT: FAIL — need same-sign significant lag-1 corr on >=2/4 alts "
              f"(got {len(signs)} significant)")


if __name__ == "__main__":
    main()
