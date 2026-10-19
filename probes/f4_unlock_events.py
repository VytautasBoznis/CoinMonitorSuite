"""F4 input: the frozen list of insider / private-sale token unlocks, from DefiLlama's schedules.

Reads the offline-evaluated schedules (`probes/f4_emissions/stage.py` -> schedules.json) and writes
`runs/f4_unlock_events.json`. No price is read here, so the event list is fixed before any return
is seen. The rules below are part of the F4 pre-registration (`probes/f4_unlock_cliff_short.py`).

EVENT. One per (coin, UTC day): the sum of that day's discrete tranches (`cliff`, and each step of
a `step` schedule) in sections DefiLlama tags `insiders` or `privateSale`, when that sum is >= 1%
of the coin's schedule-unlocked supply at the end of the previous day. Linear vesting is not an
event. Days 2020-01-01 .. 2026-09-30.

SUPPLY. Everything the schedules have unlocked by then, all sections whatever their category
(DefiLlama's "unlocked"; treasuries tagged noncirculating still trade). Sections that need a chain
or API call are missing from it, so the share is an overestimate for some coins.

COIN -> PERP. The schedule's `meta.token` is a CoinGecko id (`coingecko:<id>`) or a contract
(`<chain>:<address>`, looked up in CoinGecko's platform list). The CoinGecko symbol is matched to a
Binance USDT-M perp in the DB (loaded by `probes/z2_backfill_um_1d.py`, delisted ones included):
`<SYM>/USDT:USDT`, else `1000<SYM>`, else `1000000<SYM>`. Ticker collisions are not checked.

Run:
  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
  PYTHONPATH="src;." .venv/Scripts/python probes/f4_unlock_events.py <schedules.json>
"""
from __future__ import annotations

import json
import math
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime

import requests

from coinmon.data import db

OUT = "runs/f4_unlock_events.json"
T0 = datetime(2020, 1, 1, tzinfo=UTC).timestamp()
T1 = datetime(2026, 9, 30, tzinfo=UTC).timestamp()
DAY = 86400
MIN_SHARE = 0.01
INSIDER_CATEGORIES = ("insiders", "privateSale")
FIELDS = {"cliff": ("start", "amount"), "step": ("start", "stepDuration", "steps", "amount"),
          "linear": ("start", "end", "amount")}


def _valid(r: dict) -> bool:
    return all(isinstance(r.get(k), int | float) for k in FIELDS[r["type"]])


def _tranches(r: dict) -> list[tuple[float, float]]:
    if r["type"] == "cliff":
        return [(r["start"], r["amount"])]
    if r["type"] == "step":  # upstream loops `i < steps`: a fractional count rounds up
        return [(r["start"] + (i + 1) * r["stepDuration"], r["amount"])
                for i in range(math.ceil(r["steps"]))]
    return []


def _unlocked(r: dict, t: float) -> float:
    if r["type"] == "linear":
        span = max(r["end"] - r["start"], 1)
        return r["amount"] * min(1.0, max(0.0, (t - r["start"]) / span))
    return sum(a for ts, a in _tranches(r) if ts <= t)


def main() -> None:
    sched = json.load(open(sys.argv[1], encoding="utf-8"))
    cg = requests.get("https://api.coingecko.com/api/v3/coins/list?include_platform=true",
                      timeout=60).json()
    by_id = {c["id"]: c for c in cg}
    by_addr = {a.lower(): c for c in cg for a in (c.get("platforms") or {}).values() if a}
    conn = db.connect()
    perps = {r[0] for r in conn.execute(
        "SELECT DISTINCT symbol FROM candles WHERE exchange = 'binance' AND timeframe = '1d'"
        " AND symbol LIKE '%%/USDT:USDT'").fetchall()}

    stats, events = Counter(), []
    for name, p in sorted(sched.items()):
        if "error" in p:
            stats["schedule file failed to evaluate"] += 1
            continue
        cats = p.get("categories") or {}
        insider = {k for c in INSIDER_CATEGORIES for k in cats.get(c, [])}
        ok = {k: v for k, v in p["sections"].items()
              if v != "unsupported" and all(_valid(r) for r in v)}
        ins = {k: v for k, v in ok.items() if k in insider}
        if not ins:
            stats["no evaluable insider/privateSale section"] += 1
            continue
        chain, _, ref = ((p.get("meta") or {}).get("token") or "").partition(":")
        coin = by_id.get(ref) if chain == "coingecko" else by_addr.get(ref.lower())
        if not coin:
            stats["token not found on CoinGecko"] += 1
            continue
        sym = coin["symbol"].upper()
        perp = next((f"{pre}{sym}/USDT:USDT" for pre in ("", "1000", "1000000")
                     if f"{pre}{sym}/USDT:USDT" in perps), None)
        if not perp:
            stats["no Binance USDT-M perp, live or delisted"] += 1
            continue
        stats["matched to a perp"] += 1
        supply = [r for v in ok.values() for r in v]
        day_amt, day_kind = defaultdict(float), defaultdict(set)
        for v in ins.values():
            for r in v:
                for ts, a in _tranches(r):
                    if T0 <= ts <= T1 and a > 0:
                        d = int(ts // DAY) * DAY
                        day_amt[d] += a
                        day_kind[d].add(r["type"])
        for d in sorted(day_amt):
            unlocked = sum(_unlocked(r, d - 1) for r in supply)
            if unlocked > 0 and day_amt[d] / unlocked >= MIN_SHARE:
                events.append({
                    "protocol": name.removesuffix(".ts"), "coingecko_id": coin["id"],
                    "perp": perp, "day": datetime.fromtimestamp(d, UTC).date().isoformat(),
                    "share": day_amt[d] / unlocked, "kind": "+".join(sorted(day_kind[d]))})

    for k, v in stats.items():
        print(f"  {k:<44} {v}")
    print(f"\n{len(events)} events on {len({e['perp'] for e in events})} perps -> {OUT}")
    print("  by year:", dict(sorted(Counter(e["day"][:4] for e in events).items())))
    json.dump(events, open(OUT, "w", encoding="utf-8"), indent=1)


if __name__ == "__main__":
    main()
