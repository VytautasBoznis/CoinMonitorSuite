"""B23 — is the hour-of-day anomaly really the US EQUITY CLOSE? (a mechanism test, via DST)

Pre-registered 2026-07-29 BEFORE running. This is the cheapest available test of the anomaly's
CAUSAL STORY, and it is a genuine falsifiable prediction rather than another robustness slice.

THE SETUP. B20/B21 hold a window fixed in UTC: [21:00, 23:00). But the US equity close is 16:00
America/New_York, which is **21:00 UTC only in winter (EST) and 20:00 UTC in summer (EDT)** — DST
moves it. So a UTC-fixed window is aligned with the close for ~4.5 months a year and one hour LATE
for ~7.5 months. B21's hour-drift diagnostic is consistent with exactly that smear: median gross/yr
by UTC bar was 20:+4.6%, 21:+19.6%, 22:+13.6%, 23:-8.4% — a two-hour hump straddling both possible
close hours.

THE PREDICTION. If the effect IS the US-close (index rebalance / cash-close order flow / risk
transfer into the futures session), then re-aligning the window to New York time should SHARPEN it,
and the sharpening must show up specifically on the EDT days — the ones the UTC window mis-times.
If the NY-aligned window is NOT better on EDT days, the "US-session-close" label is wrong; the
effect may still be real (B21 stands on its own) but its mechanism is unexplained, which weakens the
case that it will persist forward.

METHOD. Per UTC day, `close_hour(day)` = the UTC hour containing 16:00 ET (20 under EDT, 21 under
EST). Two books, same mechanics as B20 (hold two hours, gross and net-maker, one round-trip/day):
  * FIXED   = hold UTC bars 21 and 22           (B20's window, unchanged)
  * NY      = hold bars close_hour and close_hour+1  (the two hours starting AT the ET close)
On EST days these are identical by construction; the whole comparison lives on the EDT days, so the
EDT split is reported separately and is what the frozen rule reads.

FROZEN RULE — on the EDT-day subset, across the 5 majors:
  MECHANISM CONFIRMED iff (a) the NY-aligned gross t-stat exceeds the FIXED one on >= 4 of 5 majors,
  AND (b) the median NY-aligned net-maker beats the median FIXED net-maker.
  Otherwise MECHANISM REFUTED — the effect is not clocked to the US cash close.
Reported either way: the full-sample NY-aligned net-maker (does re-alignment raise the deployable
yield?), which is the number that matters for [[live-yield-hurdle]] if the mechanism confirms.

Run:
  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
  PYTHONPATH="src;." .venv/Scripts/python probes/b23_hourofday_ny_align.py
"""
from __future__ import annotations

import datetime as dt
import statistics
from zoneinfo import ZoneInfo

import pandas as pd

from coinmon.data import db
from coinmon.data.db import CANDLE_COLUMNS  # noqa: F401  (documents the frame shape read below)
from probes.b20_hourofday_window import MAJORS, MAKER, net_ann, t_stat
from probes.b21_hourofday_durability import H1_EXCHANGE

NY = ZoneInfo("America/New_York")
FIXED_ENTER = 20  # B20: entry ref = close of bar 20 (=21:00), exit = close of bar 22 (=23:00)


def close_hour(day: dt.date) -> int:
    """UTC hour of the bar containing 16:00 America/New_York on `day` (20 under EDT, 21 under EST)."""
    local = dt.datetime(day.year, day.month, day.day, 16, 0, tzinfo=NY)
    return local.astimezone(dt.timezone.utc).hour


def hourly_closes(h1: pd.DataFrame) -> pd.DataFrame:
    """Wide frame of hourly closes: index = UTC date, columns = UTC hour."""
    ts = pd.to_datetime(h1["open_time"].values, unit="ms")
    df = pd.DataFrame({"close": h1["close"].values, "day": ts.date, "hour": ts.hour})
    return df.pivot_table(index="day", columns="hour", values="close")


def window_series(wide: pd.DataFrame, enter_hours: pd.Series) -> pd.Series:
    """Per-day return of holding the two bars after `enter_hours` (entry ref = close of that bar)."""
    rows = {}
    for day, eh in enter_hours.items():
        try:
            ent, ext = wide.at[day, eh], wide.at[day, (eh + 2) % 24]
        except KeyError:
            continue
        if pd.notna(ent) and pd.notna(ext) and ent > 0:
            rows[day] = ext / ent - 1.0
    return pd.Series(rows).sort_index()


def main() -> None:
    conn = db.connect()
    print("B23 NY-alignment mechanism test — is the window clocked to the 16:00 ET equity close?\n")

    hdr = (f"{'coin':>9}{'set':>6}{'fx_gross':>10}{'fx_t':>7}{'ny_gross':>10}{'ny_t':>7}"
           f"{'fx_net_mk':>11}{'ny_net_mk':>11}{'N':>7}")
    print(hdr)
    print("-" * len(hdr))

    edt_t_better, edt_fx_net, edt_ny_net = [], [], []
    full_ny_net, full_fx_net = [], []
    for coin in MAJORS:
        h1 = db.read_candles(conn, H1_EXCHANGE, coin, "1h")
        if h1.empty:
            continue
        wide = hourly_closes(h1)
        days = pd.Series(wide.index, index=wide.index)
        ch = days.map(close_hour)
        fixed = window_series(wide, pd.Series(FIXED_ENTER, index=wide.index))
        ny = window_series(wide, ch - 1)  # entry ref = bar before the close hour
        for label, mask in (("EDT", ch == 20), ("EST", ch == 21), ("all", pd.Series(True, index=ch.index))):
            f = fixed[fixed.index.isin(mask[mask].index)].dropna()
            n = ny[ny.index.isin(mask[mask].index)].dropna()
            if len(f) < 100 or len(n) < 100:
                continue
            print(f"{coin:>9}{label:>6}{f.mean() * 365:>+9.1%}{t_stat(f):>7.2f}"
                  f"{n.mean() * 365:>+9.1%}{t_stat(n):>7.2f}"
                  f"{net_ann(f, MAKER):>+10.1%}{net_ann(n, MAKER):>+10.1%}{len(f):>7}")
            if label == "EDT":
                edt_t_better.append(t_stat(n) > t_stat(f))
                edt_fx_net.append(net_ann(f, MAKER))
                edt_ny_net.append(net_ann(n, MAKER))
            elif label == "all":
                full_ny_net.append(net_ann(n, MAKER))
                full_fx_net.append(net_ann(f, MAKER))
        print("-" * len(hdr))

    conn.close()
    if not edt_t_better:
        print("no EDT-day evidence")
        return
    n_better = sum(edt_t_better)
    med_fx, med_ny = statistics.median(edt_fx_net), statistics.median(edt_ny_net)
    ok_a = n_better >= 4
    ok_b = med_ny > med_fx
    ok = lambda b: "#OK" if b else "no"
    verdict = "CONFIRMED" if (ok_a and ok_b) else "REFUTED"
    print(f"\nEDT days: NY-aligned t beat fixed t on {n_better}/{len(edt_t_better)} majors "
          f"[{ok(ok_a)}]; median net-maker fixed {med_fx:+.1%}/yr -> NY {med_ny:+.1%}/yr [{ok(ok_b)}]")
    print(f"full sample: median net-maker fixed {statistics.median(full_fx_net):+.2%}/yr -> "
          f"NY-aligned {statistics.median(full_ny_net):+.2%}/yr")
    print(f"\nB23 VERDICT: US-close mechanism {verdict}")


if __name__ == "__main__":
    main()
