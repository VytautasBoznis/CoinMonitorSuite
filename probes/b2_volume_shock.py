"""Plan-B probe B2 — volume shock conditions next-bar return (pre-registered, plan-b §P1).

Hypothesis: an abnormally high-volume 4h bar changes the next bar's expected return
(continuation or reversal), conditional on the shock bar's sign.

Frozen rule (2026-07-03, before any run): per major, 4h: volume z-score > 2 (rolling 90-bar,
point-in-time) splits shock bars by sign. For each branch (up-shock / down-shock) compare the
conditional next-bar mean return to the unconditional next-bar mean; bootstrap 95% CI on the
difference (10k, seeded). PASS if EITHER branch's difference-CI excludes 0 with the SAME sign
on >= 3 of the 5 majors. Fixed analysis, no tuning.

Majors = BTC/ETH/SOL/BNB/XRP on Binance USDT, read from the local DB.

Run:  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
      .venv/Scripts/python probes/b2_volume_shock.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from coinmon.data import db

MAJORS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
TIMEFRAME = "4h"
VOL_WINDOW = 90
VOL_Z = 2.0
N_BOOT = 10_000
SEED = 0


def boot_diff_ci(branch: np.ndarray, full: np.ndarray, rng: np.random.Generator):
    """95% CI of (branch mean - full mean), resampling each independently with replacement."""
    b = rng.choice(branch, size=(N_BOOT, len(branch)), replace=True).mean(axis=1)
    f = rng.choice(full, size=(N_BOOT, len(full)), replace=True).mean(axis=1)
    lo, hi = np.percentile(b - f, [2.5, 97.5])
    return float(branch.mean() - full.mean()), float(lo), float(hi)


def main() -> None:
    rng = np.random.default_rng(SEED)
    conn = db.connect()
    print(f"B2 volume shock — {TIMEFRAME} majors (Binance USDT), shock = vol z > {VOL_Z} "
          f"(rolling {VOL_WINDOW})")
    print(f"{'sym':<10}{'up n':>6}{'up diff':>10}{'up 95% CI':>20}   "
          f"{'dn n':>6}{'dn diff':>10}{'dn 95% CI':>20}")
    up_signs: list[int] = []
    dn_signs: list[int] = []
    for sym in MAJORS:
        c = db.read_candles(conn, "binance", sym, TIMEFRAME)
        logret = np.concatenate([[np.nan], np.diff(np.log(c["close"].to_numpy()))])
        vol = c["volume"].to_numpy(dtype=float)
        vser = pd.Series(vol)
        vmean = vser.rolling(VOL_WINDOW).mean().shift(1)
        vstd = vser.rolling(VOL_WINDOW).std().shift(1)  # trailing, point-in-time
        volz = ((vser - vmean) / vstd).to_numpy()

        next_ret = np.concatenate([logret[1:], [np.nan]])  # ret of the following bar
        valid = ~np.isnan(volz) & ~np.isnan(next_ret) & ~np.isnan(logret)
        shock = valid & (volz > VOL_Z)
        full = next_ret[valid]

        cells = []
        for sign_mask, store in ((logret > 0, up_signs), (logret < 0, dn_signs)):
            branch = next_ret[shock & sign_mask]
            diff, lo, hi = boot_diff_ci(branch, full, rng)
            sig = not lo <= 0 <= hi
            if sig:
                store.append(1 if diff > 0 else -1)
            cells.append((len(branch), diff, lo, hi, sig))
        (un, ud, ulo, uhi, us), (dn, dd, dlo, dhi, ds) = cells
        print(f"{sym:<10}{un:>6}{ud:>+10.5f}{f'[{ulo:+.5f},{uhi:+.5f}]':>20}{'*' if us else ' '}  "
              f"{dn:>6}{dd:>+10.5f}{f'[{dlo:+.5f},{dhi:+.5f}]':>20}{'*' if ds else ' '}")
    conn.close()

    def branch_pass(signs: list[int]) -> bool:
        return len(signs) >= 3 and abs(sum(signs)) == len(signs)

    up_ok, dn_ok = branch_pass(up_signs), branch_pass(dn_signs)
    verdict = "PASS" if (up_ok or dn_ok) else "FAIL"
    print(f"\nB2 VERDICT: {verdict} — same-sign significant diff on up-branch {len(up_signs)}/5, "
          f"down-branch {len(dn_signs)}/5 (need one branch >=3 same-sign)")


if __name__ == "__main__":
    main()
