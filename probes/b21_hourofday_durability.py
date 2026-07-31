"""B21 — does the B20 hour-of-day window SURVIVE the four questions that decide deployability?

Pre-registered 2026-07-29, BEFORE running (rules frozen below). B20 passed its confirmation rule
(median +16.1%/yr net-maker, 5/5 majors positive, out-of-ASSET t up to 6.0 — `runs/b20_hourofday_
window.log`), making it the project's first path-to-hurdle anomaly ([[anomaly-hourofday-lead]]).
Its stated next step was "live-paper the maker fills". That is expensive infra. This probe asks the
CHEAPER kill-questions first, all on data already in the DB — if any of them fails, we never build
the execution rig.

The four questions (each with a frozen rule; the lead SURVIVES only if all four pass):

  D1 DURABILITY (does it still exist?). The deploy hurdle is a FORWARD yield >= 5%/yr with the recent
     regime weighted ([[live-yield-hurdle]]). B20's recent-HALF read (+11%/yr median) spans ~3.7 years
     and hid a negative XRP. Here: net-maker per CALENDAR YEAR per coin.
     PASS iff the median-across-coins net-maker POOLED over the last 3 full calendar years is
     >= +5%/yr AND is positive in >= 2 of those 3 years.

  D2 OUTLIER CONCENTRATION (is it a handful of days?). A mean over 2743 days can be carried by a few
     crash/squeeze afternoons that no live book would have caught.
     PASS iff, after dropping each coin's BEST 1% of days, the median-across-coins net-maker stays
     >= 0 AND the pooled day-level fraction of positive gross returns is > 50%.

  D3 OUT-OF-VENUE / OUT-OF-QUOTE (is it a binance-USDT artifact?). The bybit USDC 1h series
     (2025-06 -> now, ~420 days) is a different venue, a different quote, and a LATER period — the
     pristine test set by [[train-usdt-certify-usdc]] discipline.
     PASS iff net-maker is positive on BOTH bybit USDC series (each needs >= 300 days).

  D4 EXECUTION REALISM (can a passive order actually get the price?). B20's +16%/yr assumes a maker
     fill AT the reference price on both legs; the sensitivity said 52-90% fills are needed. Here we
     SIMULATE working the order: post a buy limit at `ref_entry*(1-off)` during the 20:00 bar (ref =
     close of the 19:00 bar, i.e. the price at 20:00) and call it filled iff that bar's LOW touches
     it; symmetrically post a sell limit at `ref_exit*(1+off)` during the 23:00 bar (ref = close of
     the 22:00 bar, i.e. the price at 23:00 — the window's own exit price), filled iff the HIGH
     touches it. Two books: FALLBACK (an unfilled leg crosses the spread at that bar's close, paying
     taker) and SKIP (an unfilled ENTRY means no trade that day; an unfilled exit still crosses,
     since the strategy must be flat).
     PASS iff the best offset's median-across-coins net return (FALLBACK book) is >= +5%/yr.
     A passive book CANNOT trade the boundary prices B20 assumed: to own the 21:00 price you must
     rest an order before 21:00 (so your limit is the 20:00 price), and to leave at the 23:00 price
     you must rest one during the 23:00 hour. So the honest passive hold is ~20:00->23:00, which
     necessarily drags in the adjacent hours' drift. That is a property of the anomaly, not a
     modelling choice — reported as `exit@23:00` below. The first coded run rested the exit during
     the 22:00 bar (exiting an hour early, against this stated intent); that variant is kept as
     `exit@22:00` for transparency since it was run first. Both are reported; `exit@23:00` decides D4.

  HONESTY CAVEAT on D4: "the hourly bar touched my limit" is an UPPER BOUND on the fill rate — it
  ignores queue position (touching != filling) and treats a 20:05 fill the same as a 20:59 one. So
  D4 can only KILL the lead cheaply, never confirm it; a pass still needs 1m-resolution or live-paper
  measurement. This is the same asymmetry B20 flagged, tested at the resolution we already own.

Run:
  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
  PYTHONPATH="src;." .venv/Scripts/python probes/b21_hourofday_durability.py
"""
from __future__ import annotations

import statistics

import pandas as pd

from coinmon.data import db
from probes.b20_hourofday_window import ENTER_H, EXIT_H, MAJORS, MAKER, TAKER, net_ann, window_returns

H1_EXCHANGE = "binance"
USDC_VENUE = [("bybit", "BTC/USDC"), ("bybit", "ETH/USDC")]
OFFSETS = [0.0, 0.0005, 0.0010]  # how far INSIDE the reference price the passive order rests
LAST_N_YEARS = 3
DROP_FRACTION = 0.01  # D2: drop each coin's best 1% of days


def hour_frame(h1: pd.DataFrame) -> pd.DataFrame:
    """Per-day frame of the hourly bars B21 needs, indexed by UTC date.

    Columns: c19/c20/c21/c22 (closes of those hours' bars) plus low20/high22 (the bars during which
    the passive entry/exit orders rest). Bar `h` covers [h:00, h+1:00), so close(h) is the price at
    (h+1):00 — B20's window is close(20) -> close(22), i.e. 21:00 -> 23:00.
    """
    dt = pd.to_datetime(h1["open_time"].values, unit="ms")
    df = pd.DataFrame(
        {
            "close": h1["close"].values,
            "low": h1["low"].values,
            "high": h1["high"].values,
            "day": dt.date,
            "hour": dt.hour,
        }
    )
    cols = {}
    for h in (19, 20, 21, 22, 23):
        cols[f"c{h}"] = df[df["hour"] == h].set_index("day")["close"]
    cols["low20"] = df[df["hour"] == 20].set_index("day")["low"]
    for h in (22, 23):
        cols[f"high{h}"] = df[df["hour"] == h].set_index("day")["high"]
    return pd.concat(cols, axis=1).dropna()


# ---------------------------------------------------------------- D1: durability by calendar year

def yearly_net_maker(daily: pd.Series) -> dict[int, tuple[float, int]]:
    """{year: (net-maker annualized, n_days)} — mean daily net return * 365 within each year."""
    years = pd.Series([d.year for d in daily.index], index=daily.index)
    return {int(y): (net_ann(g, MAKER), len(g)) for y, g in daily.groupby(years)}


# ------------------------------------------------------------ D2: outlier / concentration analysis

def net_maker_dropping_best(daily: pd.Series, frac: float) -> float:
    """Net-maker annualized after removing the `frac` best days (still divided by the FULL calendar).

    Dropping days means those days are flat, not deleted from the year — so the annualization keeps
    the original day count, which is the honest way to ask "what if I had missed the best days".
    """
    k = int(len(daily) * frac)
    kept = daily.sort_values(ascending=True).iloc[: len(daily) - k] if k else daily
    per = kept - 2.0 * MAKER
    return per.sum() / len(daily) * 365.0


# ------------------------------------------------------------------- D4: passive-fill simulation

def fill_returns(
    f: pd.DataFrame, off: float, skip_unfilled_entry: bool, exit_bar: int = 23
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Per-day net return series of the passive book, plus the entry/exit fill flags.

    Split out of `fill_book` so B22 can build a basket from the per-day streams; `fill_book` is the
    same numbers reduced to annualized scalars. Entry: buy limit at
    c19*(1-off) resting during the 20:00 bar, filled iff low20 <= limit. Exit: sell limit at the
    close of bar `exit_bar - 1` lifted by `off`, resting during bar `exit_bar`, filled iff that
    bar's high touches it (`exit_bar=23` = leave at the window's own 23:00 price, the pre-registered
    intent; `exit_bar=22` = the first coded run's early exit). An unfilled leg crosses at its bar's
    close paying TAKER; `skip_unfilled_entry` instead sits the whole day out.
    """
    lim_in = f["c19"] * (1.0 - off)
    lim_out = f[f"c{exit_bar - 1}"] * (1.0 + off)
    hit_in = f["low20"] <= lim_in
    hit_out = f[f"high{exit_bar}"] >= lim_out

    entry_px = lim_in.where(hit_in, f["c20"])
    exit_px = lim_out.where(hit_out, f[f"c{exit_bar}"])
    fee = hit_in.map({True: MAKER, False: TAKER}) + hit_out.map({True: MAKER, False: TAKER})
    ret = exit_px / entry_px - 1.0 - fee
    if skip_unfilled_entry:
        ret = ret.where(hit_in, 0.0)
    return ret, hit_in, hit_out


def fill_book(
    f: pd.DataFrame, off: float, skip_unfilled_entry: bool, exit_bar: int = 23
) -> tuple[float, float, float]:
    """`fill_returns` reduced to (annualized net return, entry fill rate, exit fill rate)."""
    ret, hit_in, hit_out = fill_returns(f, off, skip_unfilled_entry, exit_bar)
    return ret.mean() * 365.0, float(hit_in.mean()), float(hit_out.mean())


# ------------------------------------------------------------------------------------------ main

def main() -> None:
    conn = db.connect()
    print("B21 hour-of-day durability + execution realism — window [21:00,23:00) UTC\n")

    daily_by_coin: dict[str, pd.Series] = {}
    frames: dict[str, pd.DataFrame] = {}
    for coin in MAJORS:
        h1 = db.read_candles(conn, H1_EXCHANGE, coin, "1h")
        if h1.empty:
            continue
        d = window_returns(h1, ENTER_H, EXIT_H).dropna()
        if len(d) >= 200:
            daily_by_coin[coin] = d
            frames[coin] = hour_frame(h1)

    # ---- D1
    print("D1 DURABILITY — net-maker %/yr by calendar year (n days in parens)")
    per_year = {c: yearly_net_maker(d) for c, d in daily_by_coin.items()}
    years = sorted({y for v in per_year.values() for y in v})
    hdr = f"{'year':>6}" + "".join(f"{c.split('/')[0]:>12}" for c in daily_by_coin) + f"{'median':>10}"
    print(hdr)
    print("-" * len(hdr))
    year_median: dict[int, float] = {}
    for y in years:
        vals = [per_year[c][y][0] for c in daily_by_coin if y in per_year[c]]
        year_median[y] = statistics.median(vals)
        row = f"{y:>6}"
        for c in daily_by_coin:
            if y in per_year[c]:
                v, n = per_year[c][y]
                row += f"{v:>+8.1%}({n:>3})"
            else:
                row += f"{'-':>12}"
        print(row + f"{year_median[y]:>+10.1%}")

    full_years = [y for y in years if all(per_year[c].get(y, (0, 0))[1] >= 300 for c in daily_by_coin)]
    recent = full_years[-LAST_N_YEARS:]
    pooled_recent = {}
    for c, d in daily_by_coin.items():
        mask = pd.Series([dd.year in recent for dd in d.index], index=d.index)
        pooled_recent[c] = net_ann(d[mask], MAKER)
    med_recent = statistics.median(pooled_recent.values())
    n_pos_years = sum(1 for y in recent if year_median[y] > 0)
    d1 = med_recent >= 0.05 and n_pos_years >= 2
    print(f"\n  last {LAST_N_YEARS} full years {recent}: pooled median net-maker {med_recent:+.2%}/yr, "
          f"median>0 in {n_pos_years}/{len(recent)} years  ->  D1 {'PASS' if d1 else 'FAIL'}")

    # ---- D2
    print(f"\nD2 OUTLIER CONCENTRATION — net-maker %/yr after dropping the best {DROP_FRACTION:.0%} of days")
    hdr = f"{'coin':>9}{'full':>10}{'drop-best':>11}{'pos-days':>10}{'N':>7}"
    print(hdr)
    print("-" * len(hdr))
    dropped, pos_fracs, n_tot, n_pos_days = [], [], 0, 0
    for c, d in daily_by_coin.items():
        full = net_ann(d, MAKER)
        dr = net_maker_dropping_best(d, DROP_FRACTION)
        pf = float((d > 0).mean())
        dropped.append(dr)
        pos_fracs.append(pf)
        n_tot += len(d)
        n_pos_days += int((d > 0).sum())
        print(f"{c:>9}{full:>+9.1%}{dr:>+10.1%}{pf:>9.1%}{len(d):>7}")
    med_drop = statistics.median(dropped)
    pooled_pos = n_pos_days / n_tot
    d2 = med_drop >= 0.0 and pooled_pos > 0.50
    print(f"\n  median after drop {med_drop:+.2%}/yr | pooled positive days {pooled_pos:.2%} "
          f"({n_pos_days}/{n_tot})  ->  D2 {'PASS' if d2 else 'FAIL'}")

    # ---- D3
    print("\nD3 OUT-OF-VENUE / OUT-OF-QUOTE — bybit USDC 1h (different venue, quote AND period)")
    hdr = f"{'series':>16}{'gross/yr':>10}{'net_mk/yr':>11}{'N':>7}"
    print(hdr)
    print("-" * len(hdr))
    usdc_nets = []
    for ex, sym in USDC_VENUE:
        h1 = db.read_candles(conn, ex, sym, "1h")
        if h1.empty:
            print(f"{ex + ' ' + sym:>16}   (no data)")
            continue
        d = window_returns(h1, ENTER_H, EXIT_H).dropna()
        if len(d) < 300:
            print(f"{ex + ' ' + sym:>16}   (too short: {len(d)})")
            continue
        usdc_nets.append(net_ann(d, MAKER))
        print(f"{ex + ' ' + sym:>16}{d.mean() * 365:>+9.1%}{usdc_nets[-1]:>+10.1%}{len(d):>7}")
    d3 = len(usdc_nets) == len(USDC_VENUE) and all(v > 0 for v in usdc_nets)
    print(f"\n  positive on {sum(v > 0 for v in usdc_nets)}/{len(USDC_VENUE)} USDC series  ->  "
          f"D3 {'PASS' if d3 else 'FAIL'}")

    # ---- hour-by-hour drift (diagnostic: which hours a passive book is forced to own)
    print("\nHOUR DRIFT (diagnostic) — mean gross %/yr of holding each single hour, median across coins")
    hdr = f"{'bar (UTC hour)':>15}" + "".join(f"{h:>9}" for h in range(19, 24))
    print(hdr)
    row = f"{'gross/yr':>15}"
    for h in range(19, 24):
        vals = [(f[f"c{h}"] / f[f"c{h - 1}"] - 1.0).mean() * 365.0 for f in frames.values()
                if f"c{h - 1}" in f]
        row += f"{statistics.median(vals):>+8.1%}" if vals else f"{'-':>9}"
    print(row + "   (bars 21+22 = the B20 window; a passive book also owns 20 and 23)")

    # ---- D4
    print("\nD4 EXECUTION REALISM — passive limit worked at `off` inside the reference price")
    hdr = (f"{'coin':>9}{'off':>7}{'fill_in':>9}{'fill_out':>10}{'fallback/yr':>13}{'skip/yr':>10}"
           f"{'exit':>9}")
    print(hdr)
    print("-" * len(hdr))
    fallback_by_off: dict[tuple[int, float], list[float]] = {}
    for exit_bar in (23, 22):
        for c, f in frames.items():
            for off in OFFSETS:
                fb, fi, fo = fill_book(f, off, skip_unfilled_entry=False, exit_bar=exit_bar)
                sk, _, _ = fill_book(f, off, skip_unfilled_entry=True, exit_bar=exit_bar)
                fallback_by_off.setdefault((exit_bar, off), []).append(fb)
                print(f"{c:>9}{off:>7.2%}{fi:>9.1%}{fo:>10.1%}{fb:>+12.1%}{sk:>+10.1%}"
                      f"{str(exit_bar) + ':00':>9}")
        print()
    best = {}
    for exit_bar in (23, 22):
        bo, bm = None, float("-inf")
        for off in OFFSETS:
            med = statistics.median(fallback_by_off[(exit_bar, off)])
            print(f"  exit@{exit_bar}:00 offset {off:.2%}: median fallback {med:+.2%}/yr")
            if med > bm:
                bo, bm = off, med
        best[exit_bar] = (bo, bm)
    d4 = best[23][1] >= 0.05
    print(f"\n  PRIMARY exit@23:00: best offset {best[23][0]:.2%} at {best[23][1]:+.2%}/yr | "
          f"early exit@22:00: {best[22][0]:.2%} at {best[22][1]:+.2%}/yr")
    print(f"  ->  D4 {'PASS' if d4 else 'FAIL'} (fill rates are an UPPER BOUND — touching the limit "
          f"on an hourly bar is not a fill)")

    conn.close()
    verdict = "SURVIVES" if all((d1, d2, d3, d4)) else "KILLED"
    ok = lambda b: "PASS" if b else "FAIL"
    print(f"\nB21 VERDICT: lead {verdict} — D1 durability [{ok(d1)}] D2 outlier-robust [{ok(d2)}] "
          f"D3 out-of-venue [{ok(d3)}] D4 execution-realism [{ok(d4)}]")


if __name__ == "__main__":
    main()
