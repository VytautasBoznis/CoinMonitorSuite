"""Swarm baselines: each paper bot's own backtest, frozen before its first run.

The swarm scoreboard scores every bot against its OWN backtest ([[swarm-and-cross-market-ideas]]):
N, a CI, and "too early" until the sample can say anything. This probe produces those reference
numbers once, before any paper bot runs, so nothing forward can move them. It is a measurement,
not a test: there is no verdict, and the promotion bar (``swarm.PROMOTION``) is unchanged.

THE REPLAY is the paper venue's (``live/paper.py``), the one ``tests/test_paper.py`` proves
trade-for-trade equal to a paper bot:
  * touch-fill at close[i-1] * (1 - drop), re-pegged every minute;
  * take-profit on a LATER bar within hold minutes at the bid * (1 + target), maker; else out at
    the close of minute hold, taker; Hyperliquid tier-0 fees on each leg's own notional;
  * the coin bids again from the bar after the exit;
  * f8-trend's gate: bid in minute i only if close[i-1] >= the close of the newest 1h candle that
    closed at or before minute i - 30 days (no such candle: no bid).
Binance USDT-M perp 1m stands in for Hyperliquid's candles, for the six live coins.

THE WINDOW is the F8 grid's holdout, the last 730 days (2024-10 -> 2026-09): the recent regime,
which is what a forward run trades in. Per bot: N and its pace per year, mean net per round trip
with a 95% CI (bootstrap over UTC days, ``live/score.py``), the take-profit hit rate, and the
yield as the promotion bar defines it (sum of net / 6 coins / years, 1x).

SELF-CHECK first: the replay at the grid's fees must reproduce the grid's holdout rows for F8 and
the wide cell (runs/f8_param_grid.log: N=246 +0.489%, N=666 +0.303%; means to the log's 0.001%).

Run (loads ~18M 1m rows, a few minutes):
  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
  PYTHONPATH="src;." .venv/Scripts/python probes/swarm_baselines.py
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from coinmon.data import db
from coinmon.live import swarm
from coinmon.live.ladder import F8
from coinmon.live.paper import HOUR, MAKER, MIN, TAKER
from coinmon.live.score import day_ci
from probes import f8_cascade_ladder_proxy as f8
from probes.f8_param_grid import HOLDOUT_DAYS
from probes.f8_repeg_deadband import EXCHANGE, SYMBOLS


def trend_gate(t, close, trend_ms):
    """Per bar i: is close[i-1] at or above the 1h close ``trend_ms`` before minute i?"""
    ref = (t - trend_ms) // HOUR * HOUR - MIN  # the last 1m bar of that hour carries its close
    j = np.clip(np.searchsorted(t, ref), 0, len(t) - 1)
    ok = np.zeros(len(t), bool)
    ok[1:] = (t[j[1:]] == ref[1:]) & (close[:-1] >= close[j[1:]])
    return ok


def replay(t, low, high, close, rule, maker=MAKER, taker=TAKER):
    """(fill time, net, hit take-profit) per round trip, as a paper bot trades it."""
    n, depth, target, hold = len(close), rule.drop, rule.target, rule.hold_ms // MIN
    cand = np.flatnonzero(low[1:] <= close[:-1] * (1.0 - depth)) + 1
    if rule.trend_ms is not None:
        cand = cand[trend_gate(t, close, rule.trend_ms)[cand]]
    out, free = [], 1
    for i in cand:
        if i < free:
            continue
        bid = close[i - 1] * (1.0 - depth)
        end = min(i + hold, n - 1)
        hit = np.flatnonzero(high[i + 1:end + 1] >= bid * (1.0 + target))
        if hit.size:
            exit_bar, px, fee = i + 1 + int(hit[0]), bid * (1.0 + target), maker
        else:
            exit_bar, px, fee = end, close[end], taker
        out.append((int(t[i]), px / bid - 1.0 - maker - px / bid * fee, bool(hit.size)))
        free = exit_bar + 1
    return out


def main() -> None:
    conn = db.connect()
    data = {}
    for s in SYMBOLS:
        started = time.monotonic()
        df = db.read_candles(conn, EXCHANGE, s, "1m")
        data[s] = (df["open_time"].to_numpy("int64"), df["low"].to_numpy(float),
                   df["high"].to_numpy(float), df["close"].to_numpy(float))
        print(f"  {s}: {len(df):,} bars ({time.monotonic() - started:.0f}s)")
    last = pd.Timestamp(max(int(v[0][-1]) for v in data.values()), unit="ms", tz="UTC")
    cut = (last - pd.Timedelta(days=HOLDOUT_DAYS)).normalize()
    k, years = len(SYMBOLS), HOLDOUT_DAYS / 365.25

    def holdout(rule, **fees) -> pd.DataFrame:
        rows = [e for v in data.values() for e in replay(*v, rule, **fees)]
        ev = pd.DataFrame(rows, columns=["t", "net", "tp"])
        ev["day"] = pd.to_datetime(ev["t"], unit="ms", utc=True).dt.normalize()
        return ev[ev["day"] >= cut]

    print(f"\nholdout {cut.date()} -> {last.date()} ({HOLDOUT_DAYS} days), {k} coins")
    grid_fees = {"maker": f8.MAKER, "taker": f8.TAKER}
    ok = True
    for rule, want_n, want_mean in ((F8, 246, 0.00489), (swarm.BOTS[1].rule, 666, 0.00303)):
        ev = holdout(rule, **grid_fees)
        # The grid charges the exit fee on the entry notional, this replay on the exit's: ~2e-6.
        good = len(ev) == want_n and abs(ev["net"].mean() - want_mean) < 1e-5
        ok &= good
        print(f"self-check at the grid's fees, {rule.drop:.1%} / {rule.target:.1%} /"
              f" {rule.hold_ms // MIN}m: N={len(ev)} mean {ev['net'].mean() * 100:+.3f}%"
              f"  (grid: N={want_n} {want_mean * 100:+.3f}%) {'OK' if good else 'MISMATCH'}")
    if not ok:
        print("SELF-CHECK FAILED: the replay does not reproduce the grid; stopping.")
        return

    print("\nBASELINES at Hyperliquid fees (maker 0.015%, taker 0.045%):")
    print(f"{'bot':<9} {'rule':<26} {'N':>5} {'N/yr':>6} {'mean':>8} {'95% CI (UTC days)':>21}"
          f" {'TP hit':>7} {'yield/yr':>9}")
    for spec in swarm.BOTS:
        r = spec.rule
        ev = holdout(r)
        lo, hi = day_ci(ev["net"], ev["day"])
        gate = " +30d gate" if r.trend_ms else ""
        print(f"{spec.name:<9} {f'{r.drop:.1%} / {r.target:.1%} / {r.hold_ms // MIN}m{gate}':<26}"
              f" {len(ev):>5} {len(ev) / years:>6.1f} {ev['net'].mean() * 100:>+7.3f}%"
              f"  [{lo * 100:+.3f}%, {hi * 100:+.3f}%] {ev['tp'].mean() * 100:>6.1f}%"
              f" {ev['net'].sum() / k / years * 100:>+8.2f}%")


if __name__ == "__main__":
    main()
