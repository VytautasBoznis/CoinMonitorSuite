"""Plan-B probe B3 — cross-venue lead-lag at 4h (pre-registered, plan-b §P1).

Hypothesis: one venue prints information the other follows a bar later (Binance leads Bybit
or vice versa) on the same asset.

Frozen rule (2026-07-03, before any run): per major, corr(venue-A ret_t, venue-B ret_{t+1})
in BOTH directions, seeded pairs-bootstrap 95% CI; lag-0 (contemporaneous) reported for
CONTEXT ONLY (H4 discipline — it is co-movement, not lead-lag). PASS if the lag-1 CI excludes
0 with the same sign on >= 3 of the 5 majors in EITHER direction. Fixed analysis, no tuning.

Majors = BTC/ETH/SOL/BNB/XRP USDT, joined on open_time across Binance and Bybit (local DB).

Run:  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
      .venv/Scripts/python probes/b3_cross_venue.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from coinmon.data import db

MAJORS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
TIMEFRAME = "4h"
N_BOOT = 10_000
SEED = 0


def venue_returns(conn, venue: str, sym: str) -> pd.Series:
    c = db.read_candles(conn, venue, sym, TIMEFRAME)
    ret = np.log(c["close"]).diff()
    ret.index = c["open_time"].astype("int64")
    return ret.dropna()


def boot_corr_ci(x: np.ndarray, y: np.ndarray, rng: np.random.Generator):
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
    print(f"B3 cross-venue lead-lag — {TIMEFRAME} majors, Binance vs Bybit USDT")
    print(f"{'sym':<10}{'n':>7}{'lag0':>8}"
          f"{'bin->byb':>10}{'CI':>20}{'byb->bin':>10}{'CI':>20}")
    bin_lead: list[int] = []
    byb_lead: list[int] = []
    for sym in MAJORS:
        binance = venue_returns(conn, "binance", sym)
        bybit = venue_returns(conn, "bybit", sym)
        j = pd.DataFrame({"bin": binance, "byb": bybit}).dropna()
        lag0 = float(np.corrcoef(j["bin"], j["byb"])[0, 1])

        # binance leads: binance_t vs bybit_{t+1}
        c_bl, lo_bl, hi_bl = boot_corr_ci(j["bin"].to_numpy()[:-1], j["byb"].to_numpy()[1:], rng)
        # bybit leads: bybit_t vs binance_{t+1}
        c_yb, lo_yb, hi_yb = boot_corr_ci(j["byb"].to_numpy()[:-1], j["bin"].to_numpy()[1:], rng)
        s_bl = not lo_bl <= 0 <= hi_bl
        s_yb = not lo_yb <= 0 <= hi_yb
        if s_bl:
            bin_lead.append(1 if c_bl > 0 else -1)
        if s_yb:
            byb_lead.append(1 if c_yb > 0 else -1)
        print(f"{sym:<10}{len(j):>7}{lag0:>8.3f}"
              f"{c_bl:>10.3f}{f'[{lo_bl:+.3f},{hi_bl:+.3f}]':>20}{'*' if s_bl else '':>1}"
              f"{c_yb:>9.3f}{f'[{lo_yb:+.3f},{hi_yb:+.3f}]':>20}{'*' if s_yb else '':>1}")
    conn.close()

    def lead_pass(signs: list[int]) -> bool:
        return len(signs) >= 3 and abs(sum(signs)) == len(signs)

    ok = lead_pass(bin_lead) or lead_pass(byb_lead)
    verdict = "PASS" if ok else "FAIL"
    print(f"\nB3 VERDICT: {verdict} — same-sign significant lag-1: binance-leads {len(bin_lead)}/5, "
          f"bybit-leads {len(byb_lead)}/5 (need one direction >=3 same-sign)")


if __name__ == "__main__":
    main()
