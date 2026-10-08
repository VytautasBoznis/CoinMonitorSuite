"""F8 — LIQUIDATION-CASCADE LADDER BIDS, proxy probe on 1m candles.

Pre-registered 2026-07-31, written BEFORE the 1m data finished loading, so no rule below was
chosen after seeing a result. Idea 8 of the Fable batch ([[fable-batch-10-probe-queue]]) and the
one book already authorized for live money ([[cursed-100-eur-live-ladder]]).

THE TRADE. Resting limit bids laddered 1.5-4% below mid on liquid perps. Fills arrive from the
liquidation engine's forced market sells, not from a signal; exit into reversion within minutes to
hours. This is NOT the banned post-shock reversal ([[plan-b-p1-results]]) — there the entry was a
decision made after a bar printed; here the order is already resting and the cascade fills it.

WHY IT SHOULD PAY. A liquidation engine is a price-insensitive forced seller with a deadline. It
pays whatever the book asks. The premium is compensation for warehousing the risk that the cascade
runs further, which is exactly the risk this account is authorized to hold.

THE FROZEN RULE (all four must hold; ANY miss = KILL):
  R1 REVERSION  mean net return per event >= 3x the round-trip maker cost (3 * 2 * 2bp = 12bp).
  R2 SIGNIFICANCE  95% CI on the mean excludes zero, cluster-bootstrapped BY DAY (see below).
  R3 SAMPLE     N >= 300 events.
  R4 REGIME     mean net return positive in >= 2 disjoint calendar years.

ENTRY/EXIT (a mechanical rule, no lookahead):
  * EVENT: a 1m bar whose low <= prior close * (1 - 2.5%), i.e. the cascade reached the rung.
  * ENTRY: filled at the LADDER LEVEL (prior_close * 0.975), NOT at the bar's low. Fable's block
    specified fill-at-low; that is a strict upper bound (it assumes you bought the exact bottom
    tick of the wick). Judging R1 on the ladder level instead is a TIGHTENING of the frozen rule,
    declared here before any data was seen. Fill-at-low is still computed and reported as the
    upper-bound sensitivity, never as the verdict.
  * EXIT: take-profit at +1.2% from entry if the high reaches it within 60 minutes; otherwise exit
    at the close of minute 60. Both legs priced as maker fills (a resting bid and a resting
    take-profit both add liquidity); MAKER = 2bp, so RT = 4bp.
  * One position per symbol at a time: while a trade is open, later trigger bars are ignored.
    Without this the sample double-counts a single cascade as dozens of independent events.

WHY THE CI IS CLUSTER-BOOTSTRAPPED BY DAY. Cascade events are violently clustered — Oct 10 2025
alone can contribute hundreds of triggers across symbols. Treating them as independent draws would
shrink the CI by roughly sqrt(N) and manufacture significance. The bootstrap resamples whole
UTC days (every symbol's events that day together), so one crash day counts as roughly one
observation, not hundreds. (Fixed 2026-10-04 before the multi-symbol run: the first version
resampled (symbol, day) blocks, which let one cross-asset cascade count once PER SYMBOL. The only
prior output was the BTC-only smoke test, where the two are identical, so nothing leaked.)

HONESTY CAVEATS (flagged before running, not after):
  * NO QUEUE POSITION. A 1m OHLC bar says the price traded through your level; it does NOT say you
    were filled. Real fills need to be at the front of a book that everyone else is also bidding.
    This is the single largest unmodelled optimism and it CANNOT be settled by candles — only by
    the live book ([[cursed-100-eur-live-ladder]]) or a real L2/liquidation collector.
  * SPOT DATA, PERP TRADE. The 1m series are Binance spot; the live book is Bybit perps. Perp wicks
    run deeper than spot during cascades, which cuts both ways: more fills, worse continuation.
  * FUNDING IGNORED. Holds are <= 60 minutes, so at most one settlement is ever crossed; the
    omission is small but real and it is a cost, not a benefit.
  * NO LEVERAGE MODELLED. Returns are on unlevered notional. The live book runs levered at the
    owner's discretion ([[bybit-only-leverage-doctrine]]); leverage scales both the mean AND the
    liquidation risk this probe cannot see, so it is deliberately left out of the verdict.
  * A PASS LICENSES THE COLLECTOR AND THE MICRO-LIVE BOOK ONLY. Never a deployment, never a
    certificate ([[alpha-definition-edge-certificate]], [[live-yield-hurdle]]).

PERP RERUN (pre-registered 2026-10-08, written BEFORE any perp 1m bar was loaded). The spot run
PASSED 4/4 ([[f8-cascade-ladder-result]]) and named SPOT -> PERP as its biggest untested
assumption. `--perp` re-runs the IDENTICAL frozen rule (R1-R4, same constants, same seed, same
bootstrap) on Binance USDT-M perp 1m for the same 10 coins (SHIB as the 1000x contract). ANY miss on
R1-R4 = KILL of the proxy pass, and the live ladder book loses its license. A perp PASS changes
nothing else: still micro-live + collector only. Span: perp loads through the last complete month
(2026-09), one month past the spot run; that month is out-of-sample for both.

Run:
  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
  PYTHONPATH="src;." .venv/Scripts/python probes/f8_cascade_ladder_proxy.py [--perp]
"""
from __future__ import annotations

import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd

from coinmon.data import db

EXCHANGE = "binance"
TIMEFRAME = "1m"
SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT",
    "DOGE/USDT", "AVAX/USDT", "NEAR/USDT", "LINK/USDT", "SHIB/USDT", "ADA/USDT", "XRP/USDT",
]
# Same coins as USDT-M perps (loaded by `probes/z1_backfill_1m.py --perp`).
PERP_SYMBOLS = [
    "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT",
    "DOGE/USDT:USDT", "AVAX/USDT:USDT", "NEAR/USDT:USDT", "LINK/USDT:USDT", "1000SHIB/USDT:USDT",
    "ADA/USDT:USDT", "XRP/USDT:USDT",
]

MAKER = 0.0002  # probe-standard maker fee (probes/b20_hourofday_window.py:42); Bybit perp maker
TAKER = 0.00055  # Bybit perp taker — sensitivity only: a minute-60 time-stop cannot rest as maker
RT_COST = 2 * MAKER  # resting bid in, resting take-profit out
DROP = 0.025  # ladder rung: 2.5% below the prior close
TARGET = 0.012  # take-profit, +1.2% from entry
HOLD = 60  # minutes to reach the target before exiting at market-ish close

R1_MIN = 3 * RT_COST  # >= 3x round-trip maker cost
R3_MIN_N = 300
BOOT = 10_000
SEED = 20260731


@dataclass(frozen=True)
class Event:
    symbol: str
    day: pd.Timestamp
    year: int
    net_ladder: float  # entry at the ladder rung (the verdict)
    net_ladder_taker_stop: float  # same, but time-stop exits pay taker (sensitivity)
    net_low: float  # entry at the bar low (upper-bound sensitivity)
    hit_target: bool
    depth: float  # (rung - low) / rung: how far the wick traded THROUGH the bid (diagnostic)
    after_gap: bool  # prior row is not the previous minute (exchange downtime; diagnostic)
    mae: float  # worst low / rung - 1 from the fill bar to the exit bar (diagnostic)


def _events(df: pd.DataFrame, symbol: str) -> list[Event]:
    """Walk one 1m series, emitting one event per cascade rung touched (no overlapping holds)."""
    ts = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    open_time = df["open_time"].to_numpy("int64")
    low = df["low"].to_numpy(float)
    high = df["high"].to_numpy(float)
    close = df["close"].to_numpy(float)
    prior_close = np.roll(close, 1)

    out: list[Event] = []
    i, n = 1, len(df)
    while i < n:
        rung = prior_close[i] * (1.0 - DROP)
        if low[i] > rung:
            i += 1
            continue

        # Exit window starts at i+1. Bar i's OWN high sits ~2.5% above the rung (it is the bar
        # that crashed INTO the rung), so including it lets the take-profit fill on the same
        # candle that filled the bid — exit before entry. 1m OHLC cannot order intrabar ticks,
        # so the only honest choice is to require the exit on a LATER bar.
        end = min(i + HOLD, n - 1)
        window_high = high[i + 1 : end + 1]

        def _net(entry_px: float, w=window_high, e=end) -> tuple[float, bool]:
            target_px = entry_px * (1.0 + TARGET)
            hit = bool((w >= target_px).any())
            exit_px = target_px if hit else close[e]
            return exit_px / entry_px - 1.0 - RT_COST, hit

        net_ladder, hit_ladder = _net(rung)
        net_low, _ = _net(low[i])
        tp = np.flatnonzero(window_high >= rung * (1.0 + TARGET))
        exit_bar = i + 1 + int(tp[0]) if tp.size else end
        out.append(
            Event(
                symbol=symbol,
                day=ts.iloc[i].normalize(),
                year=int(ts.iloc[i].year),
                net_ladder=net_ladder,
                net_ladder_taker_stop=net_ladder if hit_ladder else net_ladder - (TAKER - MAKER),
                net_low=net_low,
                hit_target=hit_ladder,
                depth=(rung - low[i]) / rung,
                after_gap=bool(open_time[i] - open_time[i - 1] != 60_000),
                mae=float(low[i : exit_bar + 1].min() / rung - 1.0),
            )
        )
        i = end + 1  # one position per symbol at a time
    return out


def _cluster_bootstrap(events: list[Event], rng: np.random.Generator) -> tuple[float, float]:
    """95% CI on the mean net return, resampling whole UTC days (all symbols together)."""
    frame = pd.DataFrame({"k": [e.day for e in events],
                          "r": [e.net_ladder for e in events]})
    blocks = [g.to_numpy() for _, g in frame.groupby("k")["r"]]
    idx = np.arange(len(blocks))
    means = np.empty(BOOT)
    for b in range(BOOT):
        pick = rng.choice(idx, size=len(blocks), replace=True)
        means[b] = np.concatenate([blocks[j] for j in pick]).mean()
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def main() -> None:
    conn = db.connect()
    symbols = PERP_SYMBOLS if "--perp" in sys.argv else SYMBOLS
    events: list[Event] = []
    span_ms: list[int] = []
    for symbol in symbols:
        df = db.read_candles(conn, EXCHANGE, symbol, TIMEFRAME)
        if df.empty:
            print(f"  {symbol}: NO 1m DATA — run probes/z1_backfill_1m.py first")
            continue
        span_ms += [int(df["open_time"].iloc[0]), int(df["open_time"].iloc[-1])]
        ev = _events(df, symbol)
        events.extend(ev)
        print(f"  {symbol}: {len(df):>9,} bars  ->  {len(ev):>5,} events")

    if not events:
        print("\nNo events — cannot evaluate.")
        return

    net = np.array([e.net_ladder for e in events])
    net_low = np.array([e.net_low for e in events])
    mean = float(net.mean())
    lo, hi = _cluster_bootstrap(events, np.random.default_rng(SEED))

    by_year = pd.DataFrame({"y": [e.year for e in events], "r": net}).groupby("y")["r"]
    year_means = by_year.mean()
    pos_years = int((year_means > 0).sum())
    n_days = len({(e.symbol, e.day) for e in events})
    n_clusters = len({e.day for e in events})
    taker_stop = np.mean([e.net_ladder_taker_stop for e in events])

    hit_rate = float(np.mean([e.hit_target for e in events]))
    counts = by_year.count()
    print(f"\n{'=' * 68}")
    print(f"F8 CASCADE LADDER PROXY — {len(events)} events, {n_days} distinct symbol-days, "
          f"{n_clusters} distinct UTC days (bootstrap clusters)")
    print(f"{'=' * 68}")
    print(f"  mean net / event (ladder fill) : {mean * 100:+.3f}%")
    print(f"  95% CI (cluster bootstrap)     : [{lo * 100:+.3f}%, {hi * 100:+.3f}%]")
    print(f"  target hit rate                : {hit_rate * 100:.1f}%")
    print(f"  time-stop exits at TAKER       : {taker_stop * 100:+.3f}%  <- sensitivity, not the verdict")
    print(f"  UPPER BOUND (fill at wick low) : {net_low.mean() * 100:+.3f}%  <- not the verdict")
    print("\n  per-year mean net (ladder fill):")
    for y, m in year_means.items():
        print(f"    {y}  {m * 100:+.3f}%   n={int(counts[y]):>5,}")

    r1 = mean >= R1_MIN
    r2 = lo > 0
    r3 = len(events) >= R3_MIN_N
    r4 = pos_years >= 2
    print(f"\n  R1 mean >= {R1_MIN * 100:.2f}% (3x RT maker) : {'PASS' if r1 else 'FAIL'}")
    print(f"  R2 95% CI excludes zero          : {'PASS' if r2 else 'FAIL'}")
    print(f"  R3 N >= {R3_MIN_N}                       : {'PASS' if r3 else 'FAIL'} (N={len(events)})")
    print(f"  R4 positive in >= 2 years        : {'PASS' if r4 else 'FAIL'} ({pos_years} yr)")
    verdict = "PASS" if all((r1, r2, r3, r4)) else "KILL"
    print(f"\n  VERDICT: {verdict}")
    if verdict == "PASS":
        print("  Licenses the liquidation collector + the micro-live book ONLY — not a deployment.")

    span = (pd.Timestamp(min(span_ms), unit="ms", tz="UTC"),
            pd.Timestamp(max(span_ms), unit="ms", tz="UTC"))
    _diagnostics(events, span, len(symbols))


# ============================================================ POST-VERDICT DIAGNOSTICS (not frozen)
# Added 2026-10-04 AFTER the verdict printed. They probe the verdict's weak spots; they never move it.


def _summ(label: str, evs: list[Event]) -> None:
    if not evs:
        print(f"    {label:<34} N=    0")
        return
    lo, hi = _cluster_bootstrap(evs, np.random.default_rng(SEED))
    m = np.mean([e.net_ladder for e in evs])
    print(f"    {label:<34} N={len(evs):>5,}  mean {m * 100:+.3f}%  CI [{lo * 100:+.3f}%, "
          f"{hi * 100:+.3f}%]  days={len({e.day for e in evs})}")


def _diagnostics(events: list[Event], span: tuple[pd.Timestamp, pd.Timestamp],
                 n_slices: int) -> None:
    print(f"\n{'=' * 68}")
    print("POST-VERDICT DIAGNOSTICS — not part of the frozen rule, do not change the verdict")
    print(f"{'=' * 68}")

    # ---- D-A: touch-fill adverse selection. A wick that only TOUCHES the rung is exactly where a
    # resting bid likely was NOT filled (the queue ahead ate the flow) and exactly where price
    # bounced. If the edge lives in shallow touches, it is a fill artifact. Require the wick to
    # trade THROUGH the bid by x before counting a fill.
    print("\nD-A  TRADE-THROUGH REQUIREMENT (fill only if low <= rung * (1 - x))")
    for x in (0.0, 0.001, 0.0025, 0.005, 0.01):
        _summ(f"x = {x * 100:.2f}%", [e for e in events if e.depth >= x])
    print("     by depth bucket (where does the PnL live?):")
    edges = (0.0, 0.001, 0.0025, 0.005, 0.01, 0.02, np.inf)
    for a, b in zip(edges[:-1], edges[1:]):
        _summ(f"depth [{a * 100:.2f}%, {b * 100:.2f}%)", [e for e in events if a <= e.depth < b])

    # ---- D-B: exchange-downtime artifacts — prior_close from before an outage is not a live mid.
    gap = [e for e in events if e.after_gap]
    print(f"\nD-B  EVENTS RIGHT AFTER A DATA GAP: {len(gap)} of {len(events)}")
    _summ("excluding gap events", [e for e in events if not e.after_gap])

    # ---- D-C: what ONE account earns — the number the live hurdle judges ([[live-yield-hurdle]]).
    # Capital split equally across the symbols; each fill uses its symbol's whole slice, UNLEVERED.
    # Resting orders reserve margin on Bybit, so idle slices are not free to do anything else.
    lo, hi = span
    years = (hi - lo).days / 365.25
    total = sum(e.net_ladder for e in events) / n_slices
    print(f"\nD-C  ONE-ACCOUNT EQUAL-WEIGHT BOOK ({n_slices} slices, 1x): "
          f"{total / years * 100:+.2f}%/yr simple over {years:.2f}y")
    for y in sorted({e.year for e in events}):
        y_lo = max(lo, pd.Timestamp(f"{y}-01-01", tz="UTC"))
        y_hi = min(hi, pd.Timestamp(f"{y + 1}-01-01", tz="UTC"))
        frac = (y_hi - y_lo).days / 365.25
        s = sum(e.net_ladder for e in events if e.year == y) / n_slices
        print(f"    {y}  {s / frac * 100:+6.2f}%/yr  (covers {frac:.2f}y)")

    # ---- D-D: the recent regime the deploy hurdle weights.
    cutoff = hi - pd.Timedelta(days=730)
    recent = [e for e in events if e.day >= cutoff.normalize()]
    r_yield = sum(e.net_ladder for e in recent) / n_slices / 2.0
    print(f"\nD-D  RECENT 24 MONTHS ({cutoff.date()} -> {hi.date()}): account {r_yield * 100:+.2f}%/yr")
    _summ("recent events", recent)

    # ---- D-E: concentration — does a handful of crash days carry the result?
    by_day = pd.Series([e.net_ladder for e in events],
                       index=[e.day for e in events]).groupby(level=0).sum().sort_values()
    tot = by_day.sum()
    print(f"\nD-E  DAY CONCENTRATION: top-5 days = {by_day.tail(5).sum() / tot * 100:.1f}% of "
          f"summed PnL; top-20 = {by_day.tail(20).sum() / tot * 100:.1f}%")
    print("     worst 5 days (summed net across symbols):")
    for d, v in by_day.head(5).items():
        print(f"       {d.date()}  {v * 100:+.2f}%")
    print("     best 5 days:")
    for d, v in by_day.tail(5).iloc[::-1].items():
        print(f"       {d.date()}  {v * 100:+.2f}%")

    # ---- D-F: max adverse excursion vs isolated-margin liquidation distance. The live book runs
    # levered at the owner's discretion ([[cursed-100-eur-live-ladder]]); this is the table that
    # says how to read its fills, not a recommendation. Long liq ~ entry * (1 - 1/L + MMR), MMR
    # 0.5% (Bybit low tier; worse on alts). On SPOT wicks these breach rates are a FLOOR for the
    # perp book; the `--perp` run measures them directly.
    mae = np.array([e.mae for e in events])
    print(f"\nD-F  MAX ADVERSE EXCURSION during the hold (fill -> exit): median "
          f"{np.median(mae) * 100:+.2f}%, 5th pct {np.percentile(mae, 5) * 100:+.2f}%, "
          f"worst {mae.min() * 100:+.2f}%")
    for lev in (3, 5, 10, 20):
        liq = -(1.0 / lev - 0.005)
        k = int((mae <= liq).sum())
        print(f"    {lev:>2}x isolated (liq at {liq * 100:+.1f}%): {k:>4} of {len(mae)} fills "
              f"breach ({k / len(mae) * 100:.1f}%)")

    # ---- D-G (added 2026-10-08, after the perp run): D-D under D-A's trade-through fills. D-D
    # counts a touch as a fill; on recent data that assumption alone decides whether the account
    # clears the hurdle, and a Binance print says nothing about queue position on Bybit.
    print("\nD-G  RECENT 24 MONTHS x TRADE-THROUGH (fill only if low <= rung * (1 - x))")
    for x in (0.0, 0.001, 0.0025, 0.005):
        r = [e for e in recent if e.depth >= x]
        acct = sum(e.net_ladder for e in r) / n_slices / 2.0
        _summ(f"x = {x * 100:.2f}%  acct {acct * 100:+.2f}%/yr", r)


if __name__ == "__main__":
    main()
