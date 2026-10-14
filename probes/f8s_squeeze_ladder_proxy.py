"""F8S — SHORT-SQUEEZE LADDER ASKS: F8 mirrored, proxy probe on 1m perp candles.

Pre-registered 2026-10-14, written BEFORE anything was run on the short side. The question comes
from the owner after the first live long fill: in a falling market the liquidation tape is mostly
longs being wiped, so a long-only ladder harvests one side of the forced flow. Should the book
also rest asks above price to catch the other side: the forced BUYING of a short squeeze?

THE TRADE. F8 ([[f8-cascade-ladder-result]]) mirrored: a resting post-only SELL (a short) at the
prior 1m close +2.5%; a take-profit (buy back) at -1.2% from the fill if any later bar within 60
minutes trades down to it, else exit at the close of minute 60. One position per symbol at a time.
The fill comes from forced market buys (short liquidations) instead of forced sells.

THE FROZEN RULE: identical to F8's, same constants, seed and day-clustered bootstrap, on the same
10 Binance USDT-M perps over the same span as F8's perp run. All four must hold; ANY miss = KILL,
and the short side is NOT added to the live book.
  R1 REVERSION     mean net return per event >= 3x the round-trip maker cost (12bp).
  R2 SIGNIFICANCE  95% CI on the mean excludes zero, cluster-bootstrapped BY UTC DAY.
  R3 SAMPLE        N >= 300 events.
  R4 REGIME        mean net return positive in >= 2 disjoint calendar years.

WHY THE MIRROR MAY FAIL (stated before running):
  * Squeezes are not cascades turned upside down. Price has no floor going up, crypto has a long
    upward drift, and a squeeze that breaks resistance can keep running instead of snapping back.
  * Short-liquidation volume is smaller than long-liquidation volume in most of the sample, so the
    forced buyer may be a thinner, less reliable counterparty.

SAME HONESTY CAVEATS AS F8: no queue position (a candle that trades through the ask does not
prove a fill), funding ignored (holds <= 60m), unlevered returns. A PASS licenses only the owner's
choice to add a short ladder to the micro-live book. Never a deployment ([[live-yield-hurdle]]).

SELF-CHECK. The long side is computed with the same generalized code and must reproduce F8's
frozen perp result exactly (2261 events, mean +0.509%). A mismatch means the mirror is wrong and
the verdict is void.

PRE-REGISTERED DIAGNOSTICS (not part of the verdict), for the owner's regime question:
  Q1 Does the tape's side follow the trend? Events and mean net for each side, split by the coin's
     trailing 30-day return at the event (down market vs up market).
  Q2 Does the two-sided book beat long-only, per year and over the recent 24 months?
  plus the F8 diagnostics, mirrored: trade-through, recent 24 months, day concentration, and
  adverse excursion against a short's isolated-liquidation distance.

Run (about 5-10 minutes, mostly loading ~30M 1m bars):
  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
  PYTHONPATH="src;." .venv/Scripts/python probes/f8s_squeeze_ladder_proxy.py
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from coinmon.data import db
from probes import f8_cascade_ladder_proxy as f8
from probes.f8_cascade_ladder_proxy import (
    BOOT,
    DROP,
    EXCHANGE,
    HOLD,
    MAKER,
    PERP_SYMBOLS,
    R1_MIN,
    R3_MIN_N,
    RT_COST,
    SEED,
    TAKER,
    TARGET,
    TIMEFRAME,
)

LONG, SHORT = "long", "short"
TREND_MIN = 30 * 24 * 60  # trailing window for the regime split: 30 days of 1m bars
F8_PERP = (2261, 0.00509)  # F8's frozen perp result, for the self-check


@dataclass(frozen=True)
class Event:
    symbol: str
    side: str
    day: pd.Timestamp
    year: int
    net: float  # entry at the ladder rung (the verdict)
    net_taker_stop: float  # time-stop exits pay taker (sensitivity)
    hit_target: bool
    depth: float  # how far the wick traded THROUGH the order, as a fraction of the rung
    after_gap: bool
    mae: float  # worst move against the position from fill to exit (>= 0, fraction of the rung)
    trend30: float | None  # the coin's trailing 30-day return at the event; None near the start


def _events(df: pd.DataFrame, symbol: str, side: str) -> list[Event]:
    """One series, one side: an event per rung touched, no overlapping holds. ``long`` is F8."""
    ts = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    open_time = df["open_time"].to_numpy("int64")
    low = df["low"].to_numpy(float)
    high = df["high"].to_numpy(float)
    close = df["close"].to_numpy(float)
    prior_close = np.roll(close, 1)
    sign = 1.0 if side == LONG else -1.0

    out: list[Event] = []
    i, n = 1, len(df)
    while i < n:
        rung = prior_close[i] * (1.0 - sign * DROP)
        if (low[i] > rung) if side == LONG else (high[i] < rung):
            i += 1
            continue
        # As in F8: the exit can only happen on a LATER bar (1m OHLC cannot order intrabar ticks).
        end = min(i + HOLD, n - 1)
        target = rung * (1.0 + sign * TARGET)
        later = high[i + 1 : end + 1] if side == LONG else low[i + 1 : end + 1]
        reached = (later >= target) if side == LONG else (later <= target)
        hit = bool(reached.any())
        exit_px = target if hit else close[end]
        net = sign * (exit_px / rung - 1.0) - RT_COST
        exit_bar = i + 1 + int(np.flatnonzero(reached)[0]) if hit else end
        if side == LONG:
            depth = (rung - low[i]) / rung
            mae = -(low[i : exit_bar + 1].min() / rung - 1.0)
        else:
            depth = (high[i] - rung) / rung
            mae = high[i : exit_bar + 1].max() / rung - 1.0
        trend = close[i - 1] / close[i - 1 - TREND_MIN] - 1.0 if i - 1 - TREND_MIN >= 0 else None
        out.append(Event(
            symbol=symbol, side=side, day=ts.iloc[i].normalize(), year=int(ts.iloc[i].year),
            net=net, net_taker_stop=net if hit else net - (TAKER - MAKER), hit_target=hit,
            depth=depth, after_gap=bool(open_time[i] - open_time[i - 1] != 60_000),
            mae=max(mae, 0.0), trend30=trend,
        ))
        i = end + 1
    return out


def _ci(events: list[Event]) -> tuple[float, float]:
    """95% CI on the mean net, resampling whole UTC days (F8's bootstrap, same seed)."""
    frame = pd.DataFrame({"k": [e.day for e in events], "r": [e.net for e in events]})
    blocks = [g.to_numpy() for _, g in frame.groupby("k")["r"]]
    rng = np.random.default_rng(SEED)
    idx = np.arange(len(blocks))
    means = np.empty(BOOT)
    for b in range(BOOT):
        means[b] = np.concatenate([blocks[j] for j in rng.choice(idx, len(blocks))]).mean()
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def _summ(label: str, evs: list[Event]) -> None:
    if not evs:
        print(f"    {label:<40} N=    0")
        return
    lo, hi = _ci(evs)
    m = np.mean([e.net for e in evs])
    print(f"    {label:<40} N={len(evs):>5,}  mean {m * 100:+.3f}%  CI [{lo * 100:+.3f}%, "
          f"{hi * 100:+.3f}%]  days={len({e.day for e in evs})}")


def main() -> None:
    conn = db.connect()
    longs: list[Event] = []
    shorts: list[Event] = []
    f8_check: list = []
    span_ms: list[int] = []
    for symbol in PERP_SYMBOLS:
        df = db.read_candles(conn, EXCHANGE, symbol, TIMEFRAME)
        if df.empty:
            print(f"  {symbol}: NO 1m DATA")
            continue
        span_ms += [int(df["open_time"].iloc[0]), int(df["open_time"].iloc[-1])]
        lv, sv = _events(df, symbol, LONG), _events(df, symbol, SHORT)
        f8_check += f8._events(df, symbol)
        longs += lv
        shorts += sv
        print(f"  {symbol:<20} {len(df):>9,} bars  ->  long {len(lv):>4,}  short {len(sv):>4,}")

    # ---- self-check: the generalized long side must BE F8.
    same = [round(a.net, 12) for a in longs] == [round(b.net_ladder, 12) for b in f8_check]
    m_long = float(np.mean([e.net for e in longs]))
    print(f"\nSELF-CHECK long side vs F8's own code: N {len(longs)} vs {len(f8_check)}, "
          f"identical events: {same}; mean {m_long * 100:+.3f}% (F8 perp log: N={F8_PERP[0]}, "
          f"{F8_PERP[1] * 100:+.3f}%)")
    if not same:
        print("  MIRROR BROKEN: the verdict below is VOID.")

    # ---- the frozen verdict, short side only.
    net = np.array([e.net for e in shorts])
    mean = float(net.mean())
    lo, hi = _ci(shorts)
    by_year = pd.DataFrame({"y": [e.year for e in shorts], "r": net}).groupby("y")["r"]
    pos_years = int((by_year.mean() > 0).sum())
    print(f"\n{'=' * 72}")
    print(f"F8S SHORT-SQUEEZE LADDER — {len(shorts)} events, "
          f"{len({e.day for e in shorts})} distinct UTC days")
    print(f"{'=' * 72}")
    print(f"  mean net / event (ladder fill) : {mean * 100:+.3f}%")
    print(f"  95% CI (cluster bootstrap)     : [{lo * 100:+.3f}%, {hi * 100:+.3f}%]")
    print(f"  target hit rate                : {np.mean([e.hit_target for e in shorts]) * 100:.1f}%")
    print(f"  time-stop exits at TAKER       : "
          f"{np.mean([e.net_taker_stop for e in shorts]) * 100:+.3f}%  <- sensitivity")
    print("  per-year mean net:")
    for y, m in by_year.mean().items():
        print(f"    {y}  {m * 100:+.3f}%   n={int(by_year.count()[y]):>5,}")
    r1, r2, r3, r4 = mean >= R1_MIN, lo > 0, len(shorts) >= R3_MIN_N, pos_years >= 2
    print(f"\n  R1 mean >= {R1_MIN * 100:.2f}% (3x RT maker) : {'PASS' if r1 else 'FAIL'}")
    print(f"  R2 95% CI excludes zero          : {'PASS' if r2 else 'FAIL'}")
    print(f"  R3 N >= {R3_MIN_N}                       : {'PASS' if r3 else 'FAIL'} (N={len(shorts)})")
    print(f"  R4 positive in >= 2 years        : {'PASS' if r4 else 'FAIL'} ({pos_years} yr)")
    verdict = "PASS" if (all((r1, r2, r3, r4)) and same) else "KILL"
    print(f"\n  VERDICT: {verdict}")

    span = (pd.Timestamp(min(span_ms), unit="ms", tz="UTC"),
            pd.Timestamp(max(span_ms), unit="ms", tz="UTC"))
    _diagnostics(longs, shorts, span, len(PERP_SYMBOLS))


# ============================================================ PRE-REGISTERED DIAGNOSTICS (not frozen)


def _yield(evs: list[Event], slices: int, years: float) -> float:
    return sum(e.net for e in evs) / slices / years


def _diagnostics(longs: list[Event], shorts: list[Event],
                 span: tuple[pd.Timestamp, pd.Timestamp], slices: int) -> None:
    print(f"\n{'=' * 72}")
    print("DIAGNOSTICS — pre-registered, never change the verdict")
    print(f"{'=' * 72}")

    # ---- Q1: does the tape's side follow the trend?
    print("\nQ1  BY MARKET REGIME (the coin's trailing 30-day return at the event)")
    for side, evs in ((LONG, longs), (SHORT, shorts)):
        _summ(f"{side:<5} in a DOWN market (30d < 0)", [e for e in evs if e.trend30 is not None
                                                        and e.trend30 < 0])
        _summ(f"{side:<5} in an UP market (30d >= 0)", [e for e in evs if e.trend30 is not None
                                                        and e.trend30 >= 0])

    # ---- Q2: does the two-sided book beat long-only? (Equal-weight slices, 1x, a slice can hold
    # one long and one short ladder at once.)
    lo, hi = span
    years = (hi - lo).days / 365.25
    print(f"\nQ2  ONE-ACCOUNT BOOK, {slices} slices, 1x, simple %/yr")
    print(f"    full span ({years:.2f}y): long-only {_yield(longs, slices, years) * 100:+.2f}%  "
          f"short-only {_yield(shorts, slices, years) * 100:+.2f}%  "
          f"both {_yield(longs + shorts, slices, years) * 100:+.2f}%")
    for y in sorted({e.year for e in longs + shorts}):
        frac = (min(hi, pd.Timestamp(f"{y + 1}-01-01", tz="UTC"))
                - max(lo, pd.Timestamp(f"{y}-01-01", tz="UTC"))).days / 365.25
        lv = [e for e in longs if e.year == y]
        sv = [e for e in shorts if e.year == y]
        print(f"    {y}: long {_yield(lv, slices, frac) * 100:+6.2f}% (n={len(lv):>4})  "
              f"short {_yield(sv, slices, frac) * 100:+6.2f}% (n={len(sv):>4})  "
              f"both {_yield(lv + sv, slices, frac) * 100:+6.2f}%")
    cutoff = (hi - pd.Timedelta(days=730)).normalize()
    rl = [e for e in longs if e.day >= cutoff]
    rs = [e for e in shorts if e.day >= cutoff]
    print(f"    recent 24 months (from {cutoff.date()}): long-only {_yield(rl, slices, 2) * 100:+.2f}%  "
          f"short-only {_yield(rs, slices, 2) * 100:+.2f}%  both {_yield(rl + rs, slices, 2) * 100:+.2f}%")
    _summ("recent short events", rs)

    # ---- F8's diagnostics, mirrored for the short side.
    print("\nD-A  SHORT TRADE-THROUGH (fill only if the spike passes the ask by x)")
    for x in (0.0, 0.001, 0.0025, 0.005):
        _summ(f"x = {x * 100:.2f}%", [e for e in shorts if e.depth >= x])
    print("\nD-B  SHORT DAY CONCENTRATION")
    by_day = pd.Series([e.net for e in shorts], index=[e.day for e in shorts]).groupby(level=0).sum()
    by_day = by_day.sort_values()
    tot = by_day.sum()
    if tot:
        print(f"    top-5 days = {by_day.tail(5).sum() / tot * 100:.1f}% of summed PnL; "
              f"top-20 = {by_day.tail(20).sum() / tot * 100:.1f}%")
    print("    worst 5 days:", ", ".join(f"{d.date()} {v * 100:+.2f}%" for d, v in by_day.head(5).items()))
    mae = np.array([e.mae for e in shorts])
    print(f"\nD-C  SHORT ADVERSE EXCURSION (price above the fill): median {np.median(mae) * 100:.2f}%, "
          f"95th pct {np.percentile(mae, 95) * 100:.2f}%, worst {mae.max() * 100:.2f}%")
    for lev in (3, 5, 10, 20):
        liq = 1.0 / lev - 0.005  # short liq ~ entry * (1 + 1/L - MMR)
        k = int((mae >= liq).sum())
        print(f"    {lev:>2}x isolated (liq at +{liq * 100:.1f}%): {k:>4} of {len(mae)} fills breach "
              f"({k / len(mae) * 100:.1f}%)")


if __name__ == "__main__":
    main()
