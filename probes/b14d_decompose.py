"""B14d — decomposition of the B14 market-neutral low/high-vol book (analysis, not a new probe).

B14 (long low-vol / short high-vol perps, dollar-neutral) PASSED its frozen rule (12/12 net-positive,
median +72%/yr) but was shelved as a "regime-timed short-vol / crash-hedge bet, not clean alpha"
([[b13-low-vol-fresh-lead]]) on three grounds: Sharpe 0.79-0.90, maxDD -64% to -82%, and a
SURVIVORSHIP-INFLATED short leg (the 41-coin universe is 100% survivors — verified 2026-07-18: every
Bybit USDT leg's last 1d bar is the DB max, zero delistings).

"Riskier strategies allowed" (user, 2026-07-18) relaxes the DRAWDOWN objection but NOT survivorship or
regime-dependence. This script answers the question that decides whether any version is deployable:
WHERE DOES THE BOOK'S RETURN COME FROM — the survivorship-robust LONG low-vol leg (no borrow, real
coins we hold), or the survivorship-SUSPECT SHORT high-vol leg (the leg the missing delisted coins
would most distort)?

Method (reuses B14's exact frozen mechanics, just tracks the two legs separately):
  * long leg  = equal-weight LOW-vol basket held long, funding PAID  (a standalone long book vs cash)
  * short leg = equal-weight HIGH-vol basket held short, funding RECEIVED (a standalone short book)
  * neutral   = long - short  (identically B14)
Reports per-leg annualized net return, per-CALENDAR-YEAR net return for each leg, and the neutral
book's Sharpe / maxDD, across B14's full 12-config grid. No frozen rule (this is diagnostic).

Run:
  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
  .venv/Scripts/python probes/b14d_decompose.py
"""
from __future__ import annotations

import math
import statistics

import pandas as pd

from coinmon.backtest.xsectional import load_universe_closes
from coinmon.data import db
from probes.b14_lowvol_neutral import (
    EXCHANGE, TIMEFRAME, FEE, GRID, _direct_usdt_legs, load_daily_funding, _turnover,
)


def _sharpe(rets: list[float]) -> float:
    if len(rets) < 2:
        return float("nan")
    sd = statistics.pstdev(rets)
    if sd == 0:
        return float("nan")
    return statistics.mean(rets) / sd * math.sqrt(365.0)  # daily -> annualized


def _maxdd(curve: list[float]) -> float:
    peak = curve[0]
    dd = 0.0
    for v in curve:
        peak = max(peak, v)
        dd = min(dd, v / peak - 1.0)
    return dd


def run_config_decomp(closes: pd.DataFrame, funding: pd.DataFrame, L: int, q: float, rb: int):
    """Same book as B14.run_config but tracks long-leg, short-leg and neutral separately.

    Returns dict with per-leg annualized net, per-year net per leg, and neutral Sharpe/maxDD."""
    ret = closes.pct_change()
    times = closes.index
    year = pd.to_datetime(times, unit="ms").year
    n = len(times)
    warmup = L + 1
    if n <= warmup + rb:
        return None
    rebalance_bars = list(range(warmup, n - 1, rb))
    seg_ends = rebalance_bars[1:] + [n - 1]

    eq_l = eq_s = eq_n = 1.0
    curve_n: list[float] = []
    daily_n: list[float] = []
    # per-year cumulative growth factors, per leg
    yr_l: dict[int, float] = {}
    yr_s: dict[int, float] = {}
    yr_n: dict[int, float] = {}
    prev_l: dict[str, float] = {}
    prev_s: dict[str, float] = {}

    for start, end in zip(rebalance_bars, seg_ends, strict=True):
        window = ret.iloc[start - L + 1 : start + 1]
        vol = window.std()
        price_now = closes.iloc[start]
        elig = vol[vol.notna() & price_now.notna() & (vol > 0)]
        if len(elig) < 4:
            continue
        ranked = list(elig.sort_values(ascending=True).index)
        k = max(1, round(len(ranked) * q))
        longs = ranked[:k]
        long_set = set(longs)
        shorts = [s for s in reversed(ranked) if s not in long_set][:k]
        if not shorts:
            continue
        wl = {s: 1.0 / len(longs) for s in longs}
        ws = {s: -1.0 / len(shorts) for s in shorts}

        # entry turnover fee, charged into each leg's equity
        eq_l *= 1.0 - FEE * _turnover(prev_l, wl)
        eq_s *= 1.0 - FEE * _turnover(prev_s, ws)
        eq_n *= 1.0 - FEE * (_turnover(prev_l, wl) + _turnover(prev_s, ws))

        for d in range(start + 1, end + 1):
            rrow, frow = ret.iloc[d], funding.iloc[d]
            pl = ps = 0.0
            for s, wt in wl.items():
                r = rrow.get(s)
                if r == r:
                    pl += wt * r
                fr = frow.get(s)
                if fr == fr:
                    pl -= wt * fr          # long pays funding
            for s, wt in ws.items():
                r = rrow.get(s)
                if r == r:
                    ps += wt * r
                fr = frow.get(s)
                if fr == fr:
                    ps -= wt * fr          # short (wt<0) receives funding
            pn = pl + ps
            eq_l *= 1.0 + pl
            eq_s *= 1.0 + ps
            eq_n *= 1.0 + pn
            curve_n.append(eq_n)
            daily_n.append(pn)
            y = int(year[d])
            yr_l[y] = yr_l.get(y, 1.0) * (1.0 + pl)
            yr_s[y] = yr_s.get(y, 1.0) * (1.0 + ps)
            yr_n[y] = yr_n.get(y, 1.0) * (1.0 + pn)
        prev_l, prev_s = wl, ws

    if len(curve_n) < 4:
        return None
    years = len(curve_n) / 365.0
    return {
        "long_ann": (eq_l - 1.0) / years,
        "short_ann": (eq_s - 1.0) / years,
        "neut_ann": (eq_n - 1.0) / years,
        "sharpe": _sharpe(daily_n),
        "maxdd": _maxdd(curve_n),
        "yr_l": {y: v - 1.0 for y, v in yr_l.items()},
        "yr_s": {y: v - 1.0 for y, v in yr_s.items()},
        "yr_n": {y: v - 1.0 for y, v in yr_n.items()},
    }


def main() -> None:
    conn = db.connect()
    legs = _direct_usdt_legs(conn)

    def read(sym: str) -> pd.DataFrame:
        return db.read_candles(conn, EXCHANGE, sym, TIMEFRAME)

    closes = load_universe_closes(read, legs)
    have = [c for c in legs if c in closes.columns]
    funding = load_daily_funding(conn, have, closes.index)
    conn.close()

    print(f"B14d DECOMPOSITION — {EXCHANGE} {len(have)} USDT perps, {TIMEFRAME}, "
          f"{pd.to_datetime(closes.index[0], unit='ms').date()} -> "
          f"{pd.to_datetime(closes.index[-1], unit='ms').date()}")
    print("long = low-vol basket (survivorship-ROBUST), short = high-vol basket (survivorship-SUSPECT)\n")

    hdr = f"{'L':>4}{'q':>5}{'reb':>5}{'long/yr':>10}{'short/yr':>10}{'neut/yr':>10}{'Sharpe':>8}{'maxDD':>8}"
    print(hdr)
    print("-" * len(hdr))
    longs_ann: list[float] = []
    shorts_ann: list[float] = []
    all_yr_l: dict[int, list[float]] = {}
    all_yr_s: dict[int, list[float]] = {}
    all_yr_n: dict[int, list[float]] = {}
    for L, q, rb in GRID:
        r = run_config_decomp(closes, funding, L, q, rb)
        if r is None:
            continue
        longs_ann.append(r["long_ann"])
        shorts_ann.append(r["short_ann"])
        for y, v in r["yr_l"].items():
            all_yr_l.setdefault(y, []).append(v)
        for y, v in r["yr_s"].items():
            all_yr_s.setdefault(y, []).append(v)
        for y, v in r["yr_n"].items():
            all_yr_n.setdefault(y, []).append(v)
        print(f"{L:>4}{q:>5.1f}{rb:>5}{r['long_ann']:>+9.1%}{r['short_ann']:>+9.1%}"
              f"{r['neut_ann']:>+9.1%}{r['sharpe']:>8.2f}{r['maxdd']:>+8.1%}")

    print(f"\nmedian long-leg  net: {statistics.median(longs_ann):+.1%}/yr  (survivorship-robust)")
    print(f"median short-leg net: {statistics.median(shorts_ann):+.1%}/yr  (survivorship-suspect)")
    print("\nper-calendar-year median net across configs (long / short / neutral):")
    print(f"{'year':>6}{'long':>10}{'short':>10}{'neutral':>10}")
    for y in sorted(all_yr_n):
        ml = statistics.median(all_yr_l.get(y, [float('nan')]))
        ms = statistics.median(all_yr_s.get(y, [float('nan')]))
        mn = statistics.median(all_yr_n.get(y, [float('nan')]))
        print(f"{y:>6}{ml:>+9.1%}{ms:>+9.1%}{mn:>+9.1%}")

    print("\nREAD: if neutral-book return tracks the SHORT column (and is negative in calm years), the"
          "\nedge lives in the survivorship-suspect short leg + crash-regime timing, not clean alpha.")


if __name__ == "__main__":
    main()
