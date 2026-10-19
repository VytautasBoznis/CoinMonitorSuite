"""F8 live ladder: tune the rung depth, take-profit and time-stop on a grid. Pre-registered.

The owner asked (2026-10-19) to calibrate the live ladder's bid and exits more closely. The GA is
banned ([[ga-parked]]) and not needed: three knobs make a grid small enough to run every cell.
The danger is the search itself ([[search-overfits-not-strategy]]), so the pick is made on old
data and judged ONCE on the recent 24 months, against the rule the bot runs now. Written before
the grid was run; nothing below was chosen after seeing a grid result.

THE GRID (all 180 cells run and printed, none dropped):
  DEPTH   rung below the prior 1m close: 1.5 2 2.5 3 3.5 4 %
  TARGET  take-profit from the fill:     0.6 0.8 1.0 1.2 1.6 2.0 %
  HOLD    time-stop, minutes:            15 30 60 120 240
  BASE = 2.5 / 1.2 / 60, the frozen F8 rule the bot runs.

THE REPLAY, per coin on Binance USDT-M perp 1m (the six live COINS), as the live bot trades:
  * Bid at close[i-1] * (1 - DEPTH), re-pegged every minute. The live bot's re-peg deadband was
    priced at no measurable cost (probes/f8_repeg_deadband.py) and is left out.
  * Touch-fill at the bid. Take-profit on a LATER bar within HOLD minutes, maker both legs;
    otherwise out at the close of minute HOLD, and that leg pays TAKER (the bot closes with IOC).
  * The coin bids again from the bar after the exit (the bot re-bids once the take-profit fills).
  Those last two depart from the F8 probe, which blocked the coin until minute 60 and priced the
  time-stop as maker. A self-check first replays the F8 conventions and must reproduce the
  deadband probe's frozen row (N=1,338, +0.543%). All F8 caveats carry over unchanged: touch-fills,
  Binance prints standing in for Hyperliquid, no queue position, unlevered.

THE PICK (data before the holdout only): the cell with the highest MEDIAN calendar-year account
yield (sum of net / 6 slices / years covered, 1x). Median, so 2021 alone cannot carry it.

THE TEST, once, on the last 730 days of data (2024-10 -> 2026-09):
  T1 BEATS BASE  95% CI on (pick - BASE) holdout account yield excludes zero; paired bootstrap
                 over UTC days.
  T2 PLATEAU     every grid neighbour of the pick (one step on one axis, BASE excluded) also has
                 a higher holdout account yield than BASE.
  Both pass -> CHANGE the bot's constants to the pick. Anything else, or the pick IS BASE -> KEEP.
  BASE has ~200 holdout events, so only a large difference can show; KEEP is a likely outcome.

Run:
  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
  PYTHONPATH="src;." .venv/Scripts/python probes/f8_param_grid.py
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

from coinmon.data import db
from probes.f8_cascade_ladder_proxy import MAKER, SEED, TAKER
from probes.f8_repeg_deadband import EXCHANGE, SYMBOLS

DEPTHS = (0.015, 0.02, 0.025, 0.03, 0.035, 0.04)
TARGETS = (0.006, 0.008, 0.01, 0.012, 0.016, 0.02)
HOLDS = (15, 30, 60, 120, 240)
BASE = (0.025, 0.012, 60)
HOLDOUT_DAYS = 730
BOOT = 10_000


def simulate(t, low, high, close, depth, target, hold, frozen=False):
    """One coin's round trips: (fill time, net, worst low / bid - 1 from fill to exit)."""
    n = len(close)
    cand = np.flatnonzero(low[1:] <= close[:-1] * (1.0 - depth)) + 1
    out, free = [], 1
    for i in cand:
        if i < free:
            continue
        bid = close[i - 1] * (1.0 - depth)
        end = min(i + hold, n - 1)
        hit = np.flatnonzero(high[i + 1:end + 1] >= bid * (1.0 + target))
        if hit.size:
            exit_bar, net = i + 1 + int(hit[0]), target - 2 * MAKER
        else:
            exit_bar = end
            net = close[end] / bid - 1.0 - MAKER - (MAKER if frozen else TAKER)
        out.append((int(t[i]), net, float(low[i:exit_bar + 1].min() / bid - 1.0)))
        free = (end if frozen else exit_bar) + 1
    return out


def _cell(c) -> str:
    return f"{c[0] * 100:.1f}% / {c[1] * 100:.1f}% / {c[2]}m"


def main() -> None:
    conn = db.connect()
    data = {}
    for s in SYMBOLS:
        df = db.read_candles(conn, EXCHANGE, s, "1m")
        data[s] = (df["open_time"].to_numpy("int64"), df["low"].to_numpy(float),
                   df["high"].to_numpy(float), df["close"].to_numpy(float))
        print(f"  {s}: {len(df):,} bars")
    first = pd.Timestamp(min(int(v[0][0]) for v in data.values()), unit="ms", tz="UTC")
    last = pd.Timestamp(max(int(v[0][-1]) for v in data.values()), unit="ms", tz="UTC")
    cut = (last - pd.Timedelta(days=HOLDOUT_DAYS)).normalize()
    k = len(SYMBOLS)
    ho_years = HOLDOUT_DAYS / 365.25

    def run(cell, frozen=False) -> pd.DataFrame:
        rows = [(s, *e) for s, v in data.items() for e in simulate(*v, *cell, frozen=frozen)]
        ev = pd.DataFrame(rows, columns=["sym", "t", "net", "mae"])
        ev["day"] = pd.to_datetime(ev["t"], unit="ms", utc=True).dt.normalize()
        return ev

    check = run(BASE, frozen=True)
    print(f"\nself-check, F8 conventions: N={len(check)}  mean {check['net'].mean() * 100:+.3f}%"
          "  (deadband probe frozen row: N=1338, +0.543%)")
    if len(check) != 1338:
        print("SELF-CHECK FAILED: the replay does not reproduce F8; stopping.")
        return

    def year_frac(y: int) -> float:
        lo = max(first, pd.Timestamp(f"{y}-01-01", tz="UTC"))
        hi = min(cut, pd.Timestamp(f"{y + 1}-01-01", tz="UTC"))
        return (hi - lo).days / 365.25

    years = range(first.year, cut.year + 1)
    res = {}
    for cell in itertools.product(DEPTHS, TARGETS, HOLDS):
        ev = run(cell)
        tr, ho = ev[ev["day"] < cut], ev[ev["day"] >= cut]
        yearly = [tr.loc[tr["day"].dt.year == y, "net"].sum() / k / year_frac(y) for y in years]
        res[cell] = dict(ev=ev, ho=ho, n_tr=len(tr), tr_mean=tr["net"].mean(),
                         score=float(np.median(yearly)), n_ho=len(ho), ho_mean=ho["net"].mean(),
                         ho_acct=ho["net"].sum() / k / ho_years)

    order = sorted(res, key=lambda c: -res[c]["score"])
    print(f"\ntrain {first.date()} -> {cut.date()} (score = median of {len(years)} calendar-year"
          f" account yields), holdout {cut.date()} -> {last.date()}; ALL {len(order)} cells:")
    print(f"{'rank':>4} {'depth':>6} {'TP':>5} {'hold':>5} | {'Ntr':>5} {'mean':>7} {'med-yr':>8} |"
          f" {'Nho':>4} {'mean':>7} {'acct/yr':>8}")
    for rank, c in enumerate(order, 1):
        r = res[c]
        print(f"{rank:>4} {c[0] * 100:>5.1f}% {c[1] * 100:>4.1f}% {c[2]:>4}m | {r['n_tr']:>5}"
              f" {r['tr_mean'] * 100:+.3f}% {r['score'] * 100:>+7.2f}% | {r['n_ho']:>4}"
              f" {r['ho_mean'] * 100:+.3f}% {r['ho_acct'] * 100:>+7.2f}%"
              f"{'  <- BASE' if c == BASE else ''}")

    pick, base = order[0], res[BASE]
    print(f"\nPICK (train only): {_cell(pick)}, median-year {res[pick]['score'] * 100:+.2f}%;"
          f" BASE ranks {order.index(BASE) + 1} of {len(order)} ({base['score'] * 100:+.2f}%)")
    print(f"holdout account: pick {res[pick]['ho_acct'] * 100:+.2f}%/yr (N={res[pick]['n_ho']})"
          f"  vs BASE {base['ho_acct'] * 100:+.2f}%/yr (N={base['n_ho']})")
    if pick == BASE:
        print("\nVERDICT: KEEP (the pick is the rule the bot runs)")
        return

    a = res[pick]["ho"].groupby("day")["net"].sum()
    b = base["ho"].groupby("day")["net"].sum()
    diff = a.sub(b, fill_value=0.0).to_numpy()
    rng = np.random.default_rng(SEED)
    boots = diff[rng.integers(0, len(diff), (BOOT, len(diff)))].sum(axis=1) / k / ho_years
    lo, hi = np.percentile(boots, [2.5, 97.5])
    t1 = lo > 0
    print(f"  T1 pick - BASE {diff.sum() / k / ho_years * 100:+.2f}%/yr, 95% CI"
          f" [{lo * 100:+.2f}%, {hi * 100:+.2f}%] over {len(diff)} days : {'PASS' if t1 else 'FAIL'}")

    axes = (DEPTHS, TARGETS, HOLDS)
    idx = [ax.index(v) for ax, v in zip(axes, pick)]
    nbrs = []
    for d, step in itertools.product(range(3), (-1, 1)):
        j = list(idx)
        j[d] += step
        if 0 <= j[d] < len(axes[d]):
            c = tuple(ax[x] for ax, x in zip(axes, j))
            if c != BASE:
                nbrs.append(c)
    t2 = all(res[c]["ho_acct"] > base["ho_acct"] for c in nbrs)
    print(f"  T2 plateau, {len(nbrs)} neighbours vs BASE {base['ho_acct'] * 100:+.2f}%/yr :"
          f" {'PASS' if t2 else 'FAIL'}")
    for c in nbrs:
        print(f"       {_cell(c):<22} {res[c]['ho_acct'] * 100:+.2f}%/yr")
    print(f"\nVERDICT: {'CHANGE to ' + _cell(pick) if t1 and t2 else 'KEEP'}")

    # Post-verdict diagnostic, not part of the rule: the live book runs levered in isolated
    # margin, and a longer hold or a deeper rung changes how far a fill can run against it.
    print("\nMAE from fill to exit, full span (long liq ~ entry * (1 - 1/L + 0.5%)):")
    for name, c in (("BASE", BASE), ("pick", pick)):
        mae = res[c]["ev"]["mae"].to_numpy()
        breach = "  ".join(f"{lev}x {(mae <= -(1.0 / lev - 0.005)).mean() * 100:.1f}%"
                           for lev in (3, 5, 10))
        print(f"  {name:<4} {_cell(c):<22} median {np.median(mae) * 100:+.2f}%  5th pct"
              f" {np.percentile(mae, 5) * 100:+.2f}%  breach {breach}")


if __name__ == "__main__":
    main()
