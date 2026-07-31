"""B22 — the hour-of-day window as an equal-weight BASKET, on a genuinely out-of-asset universe.

Pre-registered 2026-07-29 BEFORE the new 1h data finished downloading (rules frozen below).

WHY a basket. B21 (`runs/b21_hourofday_durability.log`) cleared the four cheap kill-tests — the
21:00-23:00 UTC effect is durable (2023-25 pooled median +20.6%/yr net-maker, positive median in 3/3
recent years), survives out-of-venue AND out-of-quote (bybit USDC 1h, a later period: BTC +13.1%/yr,
ETH +34.4%/yr over 423 days), and a passively-executed version clears the hurdle. But its ONE weak
result was D2: per-coin returns are FAT-TAIL dependent — dropping each coin's best 1% of days takes
BTC +16.1% -> +1.9%/yr, XRP to -10.3%, SOL to -23.1% (median +1.9%) — even though the day-level
direction bias is overwhelming (54.16% of 13,127 coin-days positive, ~9 sigma). A single-coin book is
therefore a lottery on a few dozen US-close pumps.

An equal-weight basket is the direct fix, and it is the natural shape of this trade anyway:
  * it averages idiosyncratic fat tails into a smoother stream (the 9-sigma direction bias is the
    part that survives averaging; one coin's outlier is 1/N of a basket day),
  * every added coin is fresh OUT-OF-ASSET evidence (the window was discovered on BTC),
  * it tolerates a LOWER per-coin fill rate — a missed maker fill costs 1/N of the book, not the day.

DATA. `coinmon backfill --exchange binance --timeframes 1h --since 2019-01-01` was run for ~20 coins
beyond B20's five majors, so the universe splits into:
  * IN-SAMPLE-ish (set A) = the 5 B20 majors (BTC discovery + its 4 confirmation coins).
  * OUT-OF-ASSET (set B) = every OTHER binance USDT 1h series. Never inspected for this window.
Set B decides the verdict; set A is reported for comparison only.

EXECUTION. Per coin, per day, B21's `fill_returns` passive sim (exit@23:00, the pre-registered
bracketing): rest a buy limit `off` inside the 20:00 price during the 20:00 bar, rest a sell limit
`off` inside the 23:00 price during the 23:00 bar, maker fees on filled legs. PRIMARY book = SKIP an
unfilled entry (B21 showed chasing an unfilled limit with a taker order strictly hurts at every
offset); FALLBACK (chase) reported as a secondary. Capital is spread 1/N over the coins trading that
day. Offsets 0 / 0.05% / 0.10% bracket fill aggressiveness; 0.05% is the CONSERVATIVE reference
(~88% fills at 1h resolution) and the one the frozen rule uses — the 0% row's ~99% fill rate is an
artifact of hourly bars (touching a price is not a fill), so it is NOT allowed to carry the verdict.

FROZEN RULE — on the OUT-OF-ASSET basket (set B) at the 0.05% offset, PRIMARY (skip) book:
  (a) net >= +5%/yr                                  [the deploy hurdle, [[live-yield-hurdle]]]
  (b) t-stat of the daily net returns > 3            [real, not noise]
  (c) net positive in >= 4 of the last 5 full years   [durable, not one regime]
  (d) net >= +5%/yr after dropping the best 1% of BASKET-days   [the D2 outlier test, on the basket]
PASS iff all four. (d) is the whole point: if diversification worked, the basket keeps clearing the
hurdle without its best days; if the effect is still just a few pumps, (d) fails and this is a
lottery, not a yield.

Run:
  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
  PYTHONPATH="src;." .venv/Scripts/python probes/b22_hourofday_basket.py
"""
from __future__ import annotations

import math
import statistics

import pandas as pd

from coinmon.data import db
from probes.b20_hourofday_window import ENTER_H, EXIT_H, MAJORS, MAKER, net_ann, window_returns
from probes.b21_hourofday_durability import H1_EXCHANGE, OFFSETS, fill_returns, hour_frame

MIN_DAYS = 400  # a coin needs this many usable window-days to join the basket
MIN_COINS = 5  # a basket day needs this many coins trading
CONSERVATIVE_OFF = 0.0005  # the offset the frozen rule reads
DROP_FRACTION = 0.01


def basket_returns(streams: dict[str, pd.Series], min_coins: int) -> pd.Series:
    """Equal-weight daily net return: mean across the coins trading that day (1/N sizing)."""
    wide = pd.DataFrame(streams)
    return wide.mean(axis=1).where(wide.count(axis=1) >= min_coins).dropna()


def ann(daily: pd.Series) -> float:
    return daily.mean() * 365.0


def t_stat(daily: pd.Series) -> float:
    sd = daily.std()
    return daily.mean() / sd * math.sqrt(len(daily)) if sd else float("nan")


def sharpe(daily: pd.Series) -> float:
    sd = daily.std()
    return daily.mean() / sd * math.sqrt(365.0) if sd else float("nan")


def maxdd(daily: pd.Series) -> float:
    eq, peak, dd = 1.0, 1.0, 0.0
    for r in daily:
        eq *= 1.0 + r
        peak = max(peak, eq)
        dd = min(dd, eq / peak - 1.0)
    return dd


def ann_dropping_best(daily: pd.Series, frac: float) -> float:
    """Annualized net return with the best `frac` of days forced flat (kept in the calendar)."""
    k = int(len(daily) * frac)
    kept = daily.sort_values().iloc[: len(daily) - k] if k else daily
    return kept.sum() / len(daily) * 365.0


def yearly(daily: pd.Series) -> dict[int, tuple[float, int]]:
    years = pd.Series([d.year for d in daily.index], index=daily.index)
    return {int(y): (ann(g), len(g)) for y, g in daily.groupby(years)}


def load_streams(conn, symbols: list[str], off: float, skip: bool) -> dict[str, pd.Series]:
    out = {}
    for sym in symbols:
        h1 = db.read_candles(conn, H1_EXCHANGE, sym, "1h")
        if h1.empty:
            continue
        f = hour_frame(h1)
        if len(f) < MIN_DAYS:
            continue
        ret, _, _ = fill_returns(f, off, skip_unfilled_entry=skip, exit_bar=23)
        out[sym] = ret
    return out


def report(name: str, daily: pd.Series, n_coins: int) -> dict:
    print(f"{name:>22}{ann(daily):>+10.1%}{t_stat(daily):>9.2f}{sharpe(daily):>9.2f}"
          f"{maxdd(daily):>+9.1%}{ann_dropping_best(daily, DROP_FRACTION):>+11.1%}"
          f"{float((daily > 0).mean()):>9.1%}{len(daily):>7}{n_coins:>7}")
    return {"ann": ann(daily), "t": t_stat(daily), "drop": ann_dropping_best(daily, DROP_FRACTION)}


def main() -> None:
    conn = db.connect()
    have = {s for _, s, tf in db.list_series(conn) if tf == "1h" and _ == H1_EXCHANGE}
    set_a = [s for s in MAJORS if s in have]
    set_b = sorted(have - set(MAJORS))
    print("B22 hour-of-day BASKET — window [21:00,23:00) UTC, passive execution, 1/N equal weight\n")
    print(f"set A (B20 majors, in-sample-ish): {len(set_a)} — {', '.join(s.split('/')[0] for s in set_a)}")
    print(f"set B (OUT-OF-ASSET):              {len(set_b)} — "
          f"{', '.join(s.split('/')[0] for s in set_b)}\n")
    if not set_b:
        print("no out-of-asset 1h series — run the 1h backfill first")
        return

    # ---- diagnostic FIRST: does the raw effect (B20 mechanics, no execution model) even exist
    # out-of-asset? Separates "altcoins don't have the anomaly" from "the passive sim is the problem".
    print("PER-COIN GROSS (diagnostic, B20 mechanics: close(20)->close(22), no execution model)")
    ghdr = f"{'coin':>10}{'gross/yr':>10}{'gross_t':>9}{'net_mk/yr':>11}{'N':>7}{'set':>5}"
    print(ghdr)
    print("-" * len(ghdr))
    gross_t: dict[str, list[float]] = {"A": [], "B": []}
    gross_net: dict[str, list[float]] = {"A": [], "B": []}
    for tag, syms in (("A", set_a), ("B", set_b)):
        for sym in syms:
            h1 = db.read_candles(conn, H1_EXCHANGE, sym, "1h")
            if h1.empty:
                continue
            d = window_returns(h1, ENTER_H, EXIT_H).dropna()
            if len(d) < MIN_DAYS:
                continue
            gt, nm = t_stat(d), net_ann(d, MAKER)
            gross_t[tag].append(gt)
            gross_net[tag].append(nm)
            print(f"{sym.split('/')[0]:>10}{ann(d):>+9.1%}{gt:>9.2f}{nm:>+10.1%}{len(d):>7}{tag:>5}")
    for tag in ("A", "B"):
        if gross_t[tag]:
            print(f"  set {tag}: median gross_t {statistics.median(gross_t[tag]):.2f} | "
                  f"gross_t>=3 on {sum(t >= 3 for t in gross_t[tag])}/{len(gross_t[tag])} | "
                  f"median net-maker {statistics.median(gross_net[tag]):+.1%}/yr | "
                  f"net-maker>0 on {sum(v > 0 for v in gross_net[tag])}/{len(gross_net[tag])}")
    print()

    hdr = (f"{'book':>22}{'net/yr':>10}{'t':>9}{'sharpe':>9}{'maxDD':>9}{'drop-best':>11}"
           f"{'pos-days':>9}{'N':>7}{'coins':>7}")
    results: dict[tuple[str, float, bool], dict] = {}
    for skip in (True, False):
        label = "skip" if skip else "chase"
        print(f"--- {label} unfilled entries {'(PRIMARY)' if skip else '(secondary)'} ---")
        print(hdr)
        print("-" * len(hdr))
        for off in OFFSETS:
            for name, syms in (("A majors", set_a), ("B out-of-asset", set_b), ("A+B all", set_a + set_b)):
                if not syms:
                    continue
                streams = load_streams(conn, syms, off, skip)
                if not streams:
                    continue
                daily = basket_returns(streams, MIN_COINS if len(streams) >= MIN_COINS else 1)
                results[(name, off, skip)] = report(f"{name} @{off:.2%}", daily, len(streams))
        print()

    # ---- the frozen rule, read off set B at the conservative offset, primary (skip) book
    streams = load_streams(conn, set_b, CONSERVATIVE_OFF, skip=True)
    daily = basket_returns(streams, MIN_COINS if len(streams) >= MIN_COINS else 1)
    per_year = yearly(daily)
    full = [y for y, (_, n) in per_year.items() if n >= 300]
    recent = sorted(full)[-5:]
    print(f"OUT-OF-ASSET basket @ {CONSERVATIVE_OFF:.2%}, per calendar year (n days)")
    for y in sorted(per_year):
        v, n = per_year[y]
        mark = "" if y in recent else "   (partial year)" if n < 300 else ""
        print(f"  {y}: {v:>+8.1%}/yr  ({n:>3} days){mark}")

    a = ann(daily)
    b = t_stat(daily)
    n_pos_years = sum(1 for y in recent if per_year[y][0] > 0)
    d = ann_dropping_best(daily, DROP_FRACTION)
    pa, pb, pc, pd_ = a >= 0.05, b > 3.0, n_pos_years >= 4, d >= 0.05
    ok = lambda x: "#OK" if x else "no"
    verdict = "PASS" if all((pa, pb, pc, pd_)) else "FAIL"
    print(f"\nB22 VERDICT: {verdict} — out-of-asset basket @{CONSERVATIVE_OFF:.2%} skip-book: "
          f"net {a:+.2%}/yr [{ok(pa)}] AND t={b:.2f}>3 [{ok(pb)}] AND positive in {n_pos_years}/"
          f"{len(recent)} of the last {len(recent)} full years [{ok(pc)}] AND drop-best-1% "
          f"{d:+.2%}/yr>=+5% [{ok(pd_)}]")
    print("  CAVEAT (unchanged from B21): hourly-bar fill simulation is an UPPER BOUND on fill rates "
          "— queue position is invisible at this resolution. Live-paper measurement still decides.")
    conn.close()


if __name__ == "__main__":
    main()
