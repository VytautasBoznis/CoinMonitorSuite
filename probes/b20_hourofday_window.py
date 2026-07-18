"""Anomaly probe B20 — the 21:00-23:00 UTC (US-session-close) hour-of-day window.

Pre-registered 2026-07-18. The anomaly scanner (`probes/anomaly_scan.py`) found BTC 1h returns have a
SIGNIFICANT positive mean at 21:00 UTC (t=3.63) and 22:00 UTC (t=3.08), with 23:00 negative — two
ADJACENT significant hours (harder to dismiss as multiple-testing noise than one), matching the
long-hypothesized US-equity-close effect (queued as B15, never run; [[b13-low-vol-fresh-lead]]).

This is the confirmation step. The window (21:00-23:00 UTC) was DISCOVERED on BTC full-sample, so BTC is
IN-SAMPLE — the honest tests are OUT-OF-ASSET (the 4 other 1h majors ETH/BNB/XRP/SOL) and OUT-OF-TIME
(the recent half). A real structural session effect should appear across coins and persist; a fluke
should not. Bar = "path to the deploy hurdle" per user 2026-07-18 ([[riskier-strategies-allowed]]).

STRATEGY (mechanical): each UTC day, hold the coin LONG across the [21:00, 23:00) window — enter at the
21:00 open (= close of the 20:00 bar), exit at the 23:00 open (= close of the 22:00 bar), flat the other
22h. One round-trip/day. Exposed only 2h/day, so almost no crypto beta — net return ~ the anomaly.
Costs reported at TAKER (0.001/side) and MAKER (0.0002/side); the per-hour edge is below a taker
round-trip, so maker (or as a tilt/overlay) is the only path. Baseline: the mean net return over ALL 24
two-hour windows — the window is only interesting if it beats the average window (i.e. it's the SPECIFIC
hour, not just "crypto drifts up").

FROZEN RULE (pre-registered; informational — a PASS funds a fuller certificate/live-paper test):
  PASS iff ALL of: (a) net-MAKER annualized >= +5%/yr on the MEDIAN of the 5 majors, AND (b) net-maker
  positive on >= 4/5 majors, AND (c) net-maker positive in the RECENT HALF (median of 5), AND (d) the
  window's gross beats the mean-of-all-24-windows baseline on the median major.

Run:
  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
  PYTHONPATH="src;." .venv/Scripts/python probes/b20_hourofday_window.py
"""
from __future__ import annotations

import math
import statistics

import pandas as pd

from coinmon.data import db

H1_EXCHANGE = "binance"
MAJORS = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "XRP/USDT", "SOL/USDT"]
ENTER_H, EXIT_H = 20, 22  # close of the 20:00 bar (=21:00) -> close of the 22:00 bar (=23:00)
TAKER, MAKER = 0.001, 0.0002


def window_returns(h1: pd.DataFrame, enter_h: int, exit_h: int) -> pd.Series:
    """Per-day close[exit_h]/close[enter_h]-1: the return of holding the [enter_h+1, exit_h+1) window."""
    dt = pd.to_datetime(h1["open_time"].values, unit="ms")
    df = pd.DataFrame({"close": h1["close"].values, "day": dt.date, "hour": dt.hour})
    ent = df[df["hour"] == enter_h].set_index("day")["close"]
    ext = df[df["hour"] == exit_h].set_index("day")["close"]
    j = pd.concat([ent.rename("ent"), ext.rename("ext")], axis=1).dropna()
    return (j["ext"] / j["ent"] - 1.0).rename(None)


def net_ann(daily: pd.Series, fee: float) -> float:
    """Annualized net return of taking the window every day, one round-trip/day at `fee`/side."""
    per = daily - 2.0 * fee
    return per.mean() * 365.0


def t_stat(daily: pd.Series) -> float:
    sd = daily.std()
    return daily.mean() / sd * math.sqrt(len(daily)) if sd else float("nan")


def main() -> None:
    conn = db.connect()
    print(f"B20 hour-of-day window [21:00,23:00) UTC — {H1_EXCHANGE} 1h majors\n")
    hdr = (f"{'coin':>9}{'gross/yr':>10}{'gross_t':>9}{'net_tk/yr':>11}{'net_mk/yr':>11}"
           f"{'recent_mk':>11}{'baseline':>10}{'N':>7}")
    print(hdr)
    print("-" * len(hdr))

    net_makers, recent_makers, beats_baseline, pos_flags = [], [], [], []
    for coin in MAJORS:
        h1 = db.read_candles(conn, H1_EXCHANGE, coin, "1h")
        if h1.empty:
            print(f"{coin:>9}   (no 1h data)")
            continue
        daily = window_returns(h1, ENTER_H, EXIT_H).dropna()
        if len(daily) < 200:
            print(f"{coin:>9}   (too short: {len(daily)})")
            continue
        nm = net_ann(daily, MAKER)
        nt = net_ann(daily, TAKER)
        gross = daily.mean() * 365.0
        gt = t_stat(daily)
        mid = len(daily) // 2
        recent_mk = net_ann(daily.iloc[mid:], MAKER)
        # baseline: mean net-maker over all 24 two-hour windows (enter_h -> enter_h+2)
        base = []
        for eh in range(24):
            d2 = window_returns(h1, eh, (eh + 2) % 24).dropna()
            if len(d2) > 200:
                base.append(net_ann(d2, MAKER))
        baseline = statistics.mean(base) if base else float("nan")
        net_makers.append(nm)
        recent_makers.append(recent_mk)
        beats_baseline.append(nm > baseline)
        pos_flags.append(nm > 0)
        print(f"{coin:>9}{gross:>+9.1%}{gt:>9.2f}{nt:>+10.1%}{nm:>+10.1%}{recent_mk:>+10.1%}"
              f"{baseline:>+9.1%}{len(daily):>7}")

    conn.close()
    if not net_makers:
        print("\nno data")
        return
    med_nm = statistics.median(net_makers)
    med_recent = statistics.median(recent_makers)
    n_pos = sum(pos_flags)
    n_beat = sum(beats_baseline)
    print(f"\nmedian net-maker: {med_nm:+.2%}/yr | positive: {n_pos}/{len(net_makers)} | "
          f"recent-half median: {med_recent:+.2%}/yr | beats baseline: {n_beat}/{len(net_makers)}")

    pass_a = med_nm >= 0.05
    pass_b = n_pos >= 4
    pass_c = med_recent > 0
    pass_d = n_beat >= 3
    ok = lambda b: "#OK" if b else "no"
    verdict = "PASS" if all((pass_a, pass_b, pass_c, pass_d)) else "FAIL"
    print(f"\nB20 VERDICT: {verdict} — median net-maker>=+5%/yr [{ok(pass_a)}] AND >=4/5 positive "
          f"[{ok(pass_b)}] AND recent-half median>0 [{ok(pass_c)}] AND beats-baseline>=3/5 [{ok(pass_d)}] "
          f"(BTC in-sample; the 4 other majors + recent-half are the out-of-sample confirmation).")


if __name__ == "__main__":
    main()
