"""Z0 collector (stopgap) — one-shot backfill of Bybit daily OPEN-INTEREST history into TimescaleDB.

The mission's Plan-B P2 (positioning/OI signals) is collector-gated; the standing directive is
"Z0 collectors start IMMEDIATELY — lookback expires daily" ([[mission-find-edge-ship-ui]],
[[plan-b-fallback-probes]]). Bybit retains ~400+ daily OI points (verified 2026-07-18), so unlike
liquidations (websocket-only, no history) OI can be backfilled deep enough to TEST a P2 signal now.

This captures the expiring lookback immediately. The CONTINUOUS poller (extend forward each day) is
user-owned k8s infra ([[user-infra-ui-plans]]) — this script is the get-the-history-before-it-ages
stopgap, safe to re-run (idempotent upsert on the natural key).

Run:
  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
  PYTHONPATH="src;." .venv/Scripts/python probes/z0_backfill_oi.py
"""
from __future__ import annotations

import pandas as pd

from coinmon.data import db
from coinmon.data.adapters.bybit import BybitAdapter

EXCHANGE = "bybit"
TIMEFRAME = "1d"


def _direct_usdt_legs(conn) -> list[str]:
    return sorted(
        sym for exch, sym, tf in db.list_series(conn)
        if exch == EXCHANGE and tf == TIMEFRAME and sym.endswith("/USDT")
    )


def main() -> None:
    adapter = BybitAdapter()
    conn = db.connect()
    db.init_schema(conn)  # creates the open_interest table if absent
    legs = _direct_usdt_legs(conn)
    print(f"Z0 OI backfill — {EXCHANGE} {len(legs)} USDT perps, {TIMEFRAME}\n")

    total = 0
    covered = 0
    for leg in legs:
        perp = f"{leg}:USDT"  # unified linear-perp form, same convention as funding
        try:
            rows = adapter.fetch_open_interest_history(perp, timeframe=TIMEFRAME)
        except Exception as exc:
            print(f"  {perp:20s} SKIP ({type(exc).__name__}: {exc})")
            continue
        if not rows:
            print(f"  {perp:20s} no OI history served")
            continue
        n = db.insert_open_interest(conn, EXCHANGE, perp, TIMEFRAME, rows)
        total += n
        covered += 1
        first = pd.to_datetime(rows[0][0], unit="ms").date()
        last = pd.to_datetime(rows[-1][0], unit="ms").date()
        print(f"  {perp:20s} {n:>4} points  {first} -> {last}")

    conn.close()
    print(f"\nbackfilled {total} OI points across {covered}/{len(legs)} perps into open_interest")


if __name__ == "__main__":
    main()
