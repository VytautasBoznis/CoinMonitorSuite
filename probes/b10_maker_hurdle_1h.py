"""Plan-B probe B10 — do 1h bars clear a MAKER round-trip? (pre-registered, plan-b §P3).

Hypothesis (the H3 analogue one timeframe down): a 1h bar's typical close-to-close move is
large enough that a round-trip paid at the MAKER fee is not self-defeating — i.e. the cost
floor, not signal absence, is what a 1h strategy has to clear.

Frozen rule (2026-07-03, before any run): distribution of |close-to-close| per 1h bar vs the
maker round-trip cost on the 5 majors. PASS if the MEDIAN |move| >= 2x the maker round-trip on
>= 3 of the 5 majors. Fixed analysis, no tuning.

maker round-trip = 2 * maker_fee (in + out, both maker); the bar must clear 2x that.

Majors = BTC/ETH/SOL/BNB/XRP on Binance USDT (1h, backfilled for this probe), local DB.

Run:  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
      .venv/Scripts/python probes/b10_maker_hurdle_1h.py
"""
from __future__ import annotations

import numpy as np

from coinmon.config import settings
from coinmon.data import db

MAJORS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
TIMEFRAME = "1h"
MAKER_ROUND_TRIP = 2 * settings.maker_fee  # in + out, both maker
HURDLE = 2 * MAKER_ROUND_TRIP  # the frozen bar the median move must clear


def main() -> None:
    conn = db.connect()
    print(f"B10 maker hurdle — {TIMEFRAME} majors (Binance USDT), maker round-trip "
          f"{MAKER_ROUND_TRIP:.4f}, hurdle = 2x = {HURDLE:.4f}")
    print(f"{'sym':<10}{'bars':>8}{'med|move|':>11}{'mean|move|':>11}{'x round-trip':>14}  pass")
    passes = 0
    for sym in MAJORS:
        c = db.read_candles(conn, "binance", sym, TIMEFRAME)
        close = c["close"].to_numpy()
        move = np.abs(close[1:] / close[:-1] - 1.0)  # |close-to-close| per bar
        med = float(np.median(move))
        ok = med >= HURDLE
        passes += ok
        print(f"{sym:<10}{len(move):>8}{med:>11.4f}{move.mean():>11.4f}"
              f"{med / MAKER_ROUND_TRIP:>13.2f}x  {'*' if ok else ''}")
    conn.close()

    verdict = "PASS" if passes >= 3 else "FAIL"
    print(f"\nB10 VERDICT: {verdict} — median |move| >= 2x maker round-trip on {passes}/5 majors "
          f"(need >=3)")


if __name__ == "__main__":
    main()
