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
(symbol, UTC day) blocks, so one crash day counts as roughly one observation, not hundreds.

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

Run:
  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
  PYTHONPATH="src;." .venv/Scripts/python probes/f8_cascade_ladder_proxy.py
"""
from __future__ import annotations

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

MAKER = 0.0002  # probe-standard maker fee (probes/b20_hourofday_window.py:42); Bybit perp maker
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
    net_low: float  # entry at the bar low (upper-bound sensitivity)
    hit_target: bool


def _events(df: pd.DataFrame, symbol: str) -> list[Event]:
    """Walk one 1m series, emitting one event per cascade rung touched (no overlapping holds)."""
    ts = pd.to_datetime(df["open_time"], unit="ms", utc=True)
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
        out.append(
            Event(
                symbol=symbol,
                day=ts.iloc[i].normalize(),
                year=int(ts.iloc[i].year),
                net_ladder=net_ladder,
                net_low=net_low,
                hit_target=hit_ladder,
            )
        )
        i = end + 1  # one position per symbol at a time
    return out


def _cluster_bootstrap(events: list[Event], rng: np.random.Generator) -> tuple[float, float]:
    """95% CI on the mean net return, resampling whole (symbol, day) blocks."""
    frame = pd.DataFrame({"k": [(e.symbol, e.day) for e in events],
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
    events: list[Event] = []
    for symbol in SYMBOLS:
        df = db.read_candles(conn, EXCHANGE, symbol, TIMEFRAME)
        if df.empty:
            print(f"  {symbol}: NO 1m DATA — run probes/z1_backfill_1m.py first")
            continue
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

    hit_rate = float(np.mean([e.hit_target for e in events]))
    counts = by_year.count()
    print(f"\n{'=' * 68}")
    print(f"F8 CASCADE LADDER PROXY — {len(events)} events, {n_days} distinct symbol-days")
    print(f"{'=' * 68}")
    print(f"  mean net / event (ladder fill) : {mean * 100:+.3f}%")
    print(f"  95% CI (cluster bootstrap)     : [{lo * 100:+.3f}%, {hi * 100:+.3f}%]")
    print(f"  target hit rate                : {hit_rate * 100:.1f}%")
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


if __name__ == "__main__":
    main()
