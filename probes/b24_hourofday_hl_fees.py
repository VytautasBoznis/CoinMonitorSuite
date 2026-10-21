"""B24 — the B20 hour-of-day window re-priced at Hyperliquid perp fees.

Pre-registered 2026-10-21, BEFORE any Hyperliquid candle was pulled and before any number at these
fees was computed. B20 ([[anomaly-hourofday-lead]]) was priced with Binance SPOT fees (taker 0.10% /
maker 0.02% per side), where the window only paid at maker. The execution venue is now Hyperliquid
perps ([[bybit-dropped-no-eu-leverage]]): taker 0.045% / maker 0.015% (tier 0, docs checked
2026-10-20), so a round trip costs 0.09% at taker, 0.06% maker-in/taker-out, 0.03% at maker. B21
kept the lead alive (durable, out-of-venue, passive-fill upper bound), B22 killed the alt basket,
B23 refuted the US-close story. Nothing here re-selects the window, the coins or the offsets: all
are B20/B21's.

THE BOOKS (all on B21's `hour_frame`; bar h covers [h:00, h+1:00), close(h) = the price at h+1:00):
  MT (PRIMARY, decides the verdict) — maker in, taker out. A post-only buy rests during the 20:00
     bar at the 20:00 price (close of the 19:00 bar). Filled iff that bar's low trades THROUGH it
     (strictly below; on price-time priority a print below your level means it was cleared).
     Unfilled -> buy at the 21:00 price paying taker. Exit at the 23:00 price paying taker (the live
     bot's IOC close). Only the entry needs a maker fill, the bet B20 could not afford at Binance
     taker fees.
  TT (diagnostic) — B20's exact window, 21:00 -> 23:00, taker both legs.
  MM (diagnostic) — B21's D4 passive book at offset 0 (exit sell resting during the 23:00 bar at
     the 23:00 price, unfilled -> taker at 00:00), with the strict trade-through fill rule on both
     legs.
  Funding: longs pay Hyperliquid's baseline 0.00125%/h (11%/yr, where funding sits 42-84% of
  hours, [[h1-hl-funding-carry-killed]]) for every hourly mark the book can hold through: TT 2h,
  MT 3h, MM 4h. Conservative: realized BTC/ETH funding averaged ~7.6%/yr.

DATA:
  Binance SPOT 1h, the 5 B20 majors (BTC ETH BNB XRP SOL), through 2026-07-06: the long sample.
  Hyperliquid PERP 1h for the same 5 (the venue's own candles, last 5000 bars, ~2026-03 -> now),
  cached to data/b24_hl_1h.parquet on first run. The in-progress bar is dropped.

FROZEN RULE. PASS iff ALL of:
  G1 RECENT   — median across the 5 majors of MT net over each coin's last 730 days of Binance
                data >= +5%/yr ([[live-yield-hurdle]]: the recent regime is the forward estimate).
  G2 BREADTH  — MT net over those 730 days positive on >= 4 of 5 majors.
  G3 FULL     — median across the 5 majors of MT net over the full Binance sample >= +5%/yr.
  G4 FORWARD  — Hyperliquid candles from 2026-08-01 (every hour-of-day probe so far saw data only
                up to 2026-07-31): daily equal-weight basket of the 5 coins' MT net. KILL iff its
                t-stat <= -2. About 80 days cannot confirm a ~0.06%/day edge, so G4 can only kill;
                the point estimate and its standard error are printed as they are.
  Any miss = KILL.

WHAT A PASS LICENSES: B20 as a PAPER bot in the swarm (owner, 2026-10-21: paper by default, cash
only after a bar written in advance; [[swarm-and-cross-market-ideas]]). Paper settles whether the
drift continues; only a cash book settles the maker-fill rate, so moving to cash stays the owner's
call. Never a certificate ([[alpha-definition-edge-certificate]]).

DIAGNOSTICS (not gates): TT and MM next to MT; MT net by calendar year; MT after dropping each
coin's best 1% of days; Hyperliquid vs Binance on their overlapping days (does the venue's window
track Binance's?).

Run:
  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
  PYTHONPATH="src;." .venv/Scripts/python probes/b24_hourofday_hl_fees.py
"""
from __future__ import annotations

import math
import statistics
import time
from datetime import date
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

from coinmon.data import db
from probes.b20_hourofday_window import MAJORS
from probes.b21_hourofday_durability import hour_frame

INFO = "https://api.hyperliquid.xyz/info"
HL_CACHE = Path("data") / "b24_hl_1h.parquet"
H = 3_600_000
HL_BARS = 5000  # candleSnapshot serves the most recent 5000 bars

HL_TAKER, HL_MAKER = 0.00045, 0.00015
FUND_H = 0.0000125  # baseline funding per hour, paid by longs
HURDLE = 0.05
RECENT_DAYS = 730
FORWARD_FROM = date(2026, 8, 1)
KILL_T = -2.0
DROP_FRACTION = 0.01


# --- data ---

def pull_hl() -> pd.DataFrame:
    """The venue's own 1h candles for the 5 majors, cached so a rerun reads the same bars."""
    if HL_CACHE.exists():
        return pd.read_parquet(HL_CACHE)
    now = int(time.time() * 1000)
    frames = []
    with httpx.Client(timeout=30.0) as c:
        for sym in MAJORS:
            coin = sym.split("/")[0]
            r = c.post(INFO, json={"type": "candleSnapshot", "req": {
                "coin": coin, "interval": "1h", "startTime": now - HL_BARS * H, "endTime": now}})
            r.raise_for_status()
            df = pd.DataFrame(r.json())
            frames.append(pd.DataFrame({
                "coin": sym, "open_time": df["t"].astype("int64"), "close": df["c"].astype(float),
                "low": df["l"].astype(float), "high": df["h"].astype(float)}))
            time.sleep(2.0)  # the live bot shares this IP's REST budget
    out = pd.concat(frames, ignore_index=True)
    out = out[out["open_time"] + H <= now]  # drop the bar still forming
    HL_CACHE.parent.mkdir(exist_ok=True)
    out.to_parquet(HL_CACHE)
    return out


# --- books ---

def books(f: pd.DataFrame) -> pd.DataFrame:
    """Per-day net return of the MT / TT / MM books at Hyperliquid fees, indexed by UTC date."""
    hit_in = f["low20"] < f["c19"]
    entry_px = f["c19"].where(hit_in, f["c20"])
    entry_fee = np.where(hit_in, HL_MAKER, HL_TAKER)

    mt = f["c22"] / entry_px - 1.0 - entry_fee - HL_TAKER - 3 * FUND_H
    tt = f["c22"] / f["c20"] - 1.0 - 2 * HL_TAKER - 2 * FUND_H
    hit_out = f["high23"] > f["c22"]
    exit_px = f["c22"].where(hit_out, f["c23"])
    exit_fee = np.where(hit_out, HL_MAKER, HL_TAKER)
    mm = exit_px / entry_px - 1.0 - entry_fee - exit_fee - 4 * FUND_H
    return pd.DataFrame({"MT": mt, "TT": tt, "MM": mm, "gross_TT": f["c22"] / f["c20"] - 1.0,
                         "fill_in": hit_in})


def ann(x: pd.Series) -> float:
    return float(x.mean() * 365.0) if len(x) else float("nan")


def drop_best(x: pd.Series, frac: float) -> float:
    """Annualized after flattening the best `frac` of days (kept in the calendar, as B21's D2)."""
    k = int(len(x) * frac)
    kept = x.sort_values().iloc[: len(x) - k] if k else x
    return float(kept.sum() / len(x) * 365.0)


def tstat(x: pd.Series) -> float:
    sd = x.std()
    return float(x.mean() / sd * math.sqrt(len(x))) if len(x) > 1 and sd else float("nan")


def ok(b: bool) -> str:
    return "PASS" if b else "FAIL"


# --- main ---

def main() -> None:
    conn = db.connect()
    print("B24 hour-of-day window at Hyperliquid perp fees — taker 0.045% / maker 0.015%, "
          "baseline funding 0.00125%/h\n")

    bn: dict[str, pd.DataFrame] = {}
    for sym in MAJORS:
        h1 = db.read_candles(conn, "binance", sym, "1h")
        bn[sym] = books(hour_frame(h1))
    conn.close()

    print("BINANCE SPOT 1h (long sample) — net %/yr per book; "
          "gross = B20's 21:00->23:00 before costs")
    hdr = (f"{'coin':>9}{'gross':>9}{'TT':>9}{'MT':>9}{'MM':>9}{'fill_in':>9}"
           f"{'MT_730d':>10}{'MT_drop1%':>11}{'N':>7}{'last day':>12}")
    print(hdr)
    print("-" * len(hdr))
    mt_full, mt_recent = {}, {}
    for sym, b in bn.items():
        last = b.index.max()
        rec = b[b.index > last - pd.Timedelta(days=RECENT_DAYS)]
        mt_full[sym], mt_recent[sym] = ann(b["MT"]), ann(rec["MT"])
        print(f"{sym:>9}{ann(b['gross_TT']):>+8.1%}{ann(b['TT']):>+8.1%}{mt_full[sym]:>+8.1%}"
              f"{ann(b['MM']):>+8.1%}{b['fill_in'].mean():>8.1%}{mt_recent[sym]:>+9.1%}"
              f"{drop_best(rec['MT'], DROP_FRACTION):>+10.1%}{len(b):>7}{str(last):>12}")

    print("\nMT net %/yr by calendar year (Binance)")
    years = sorted({d.year for b in bn.values() for d in b.index})
    print(f"{'year':>6}" + "".join(f"{s.split('/')[0]:>9}" for s in bn) + f"{'median':>9}")
    for y in years:
        vals = {s: b[[d.year == y for d in b.index]]["MT"] for s, b in bn.items()}
        row = f"{y:>6}" + "".join(f"{ann(v):>+8.1%}" if len(v) else f"{'-':>9}"
                                  for v in vals.values())
        print(row + f"{statistics.median(ann(v) for v in vals.values() if len(v)):>+8.1%}")

    # --- Hyperliquid ---
    hl_raw = pull_hl()
    hl: dict[str, pd.DataFrame] = {}
    for sym in MAJORS:
        g = hl_raw[hl_raw["coin"] == sym].sort_values("open_time")
        if len(g):
            hl[sym] = books(hour_frame(g))
    first = min(b.index.min() for b in hl.values())
    last = max(b.index.max() for b in hl.values())
    print(f"\nHYPERLIQUID PERP 1h — {first} -> {last}")

    print("\nHL vs BINANCE on overlapping days "
          "(diagnostic: does the venue's window track Binance's?)")
    print(f"{'coin':>9}{'days':>6}{'corr gross':>12}{'HL gross':>10}{'BN gross':>10}")
    for sym, b in hl.items():
        j = pd.concat([b["gross_TT"].rename("hl"), bn[sym]["gross_TT"].rename("bn")],
                      axis=1).dropna()
        if len(j) > 30:
            print(f"{sym:>9}{len(j):>6}{j['hl'].corr(j['bn']):>12.3f}{ann(j['hl']):>+9.1%}"
                  f"{ann(j['bn']):>+9.1%}")

    fwd = pd.concat({s: b["MT"] for s, b in hl.items()}, axis=1)
    fwd = fwd[[d >= FORWARD_FROM for d in fwd.index]]
    basket = fwd.mean(axis=1, skipna=True)
    t4 = tstat(basket)
    se = basket.std() / math.sqrt(len(basket)) * 365.0 if len(basket) > 1 else float("nan")
    print(f"\nFORWARD (unseen by every earlier hour-of-day probe) "
          f"{FORWARD_FROM} -> {basket.index.max()}:")
    print("  per coin MT net %/yr: " + ", ".join(f"{s.split('/')[0]} {ann(fwd[s].dropna()):+.1%}"
                                                 for s in fwd.columns))
    print(f"  basket MT net {ann(basket):+.1%}/yr, SE {se:.1%}/yr, t {t4:+.2f}, "
          f"N {len(basket)} days")

    # --- verdict ---
    med_recent = statistics.median(mt_recent.values())
    n_pos = sum(v > 0 for v in mt_recent.values())
    med_full = statistics.median(mt_full.values())
    g1, g2, g3 = med_recent >= HURDLE, n_pos >= 4, med_full >= HURDLE
    g4 = not (t4 <= KILL_T)
    print(f"\nG1 recent-730d median MT {med_recent:+.2%}/yr (>= +5%)  -> {ok(g1)}")
    print(f"G2 recent-730d MT positive on {n_pos}/5 (>= 4)  -> {ok(g2)}")
    print(f"G3 full-sample median MT {med_full:+.2%}/yr (>= +5%)  -> {ok(g3)}")
    print(f"G4 forward basket t {t4:+.2f} (KILL iff <= {KILL_T})  -> {ok(g4)}")
    verdict = "PASS" if all((g1, g2, g3, g4)) else "KILL"
    print(f"\nB24 VERDICT: {verdict}")


if __name__ == "__main__":
    main()
