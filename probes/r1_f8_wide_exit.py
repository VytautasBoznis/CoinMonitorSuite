"""R1: is the live ladder's +1.2% take-profit too early? Pre-registered; DECLARED POST-HOC.

The owner asked (2026-11-10) whether the live bot sells too soon. The F8 grid
(runs/f8_param_grid.log) already showed a wider take-profit paying more at every hold, in train
and holdout, but that pattern was read off the grid after its holdout was seen, and the grid's
only formal test compared two rules with different bids. This probe runs the one comparison
never run: the same bids, the same hold, only the take-profit changed. The rules below are
copied from docs/strategy-review-2026-11-10.md (R1), written before this file was run.

THE TWO RULES, on the grid's replay (``f8_param_grid.simulate``, live conventions, six coins):
  BASE  2.5% / 1.2% / 60m   the rule the bot runs
  WIDE  2.5% / 2.0% / 60m

THE TEST: paired difference in account yield, WIDE - BASE (sum of net / 6 slices / years, 1x),
95% CI by bootstrap over UTC days, separately on the grid's train (before the last 730 days)
and holdout (the last 730 days).
  R1a  the train CI excludes zero
  R1b  the holdout CI excludes zero
  R1c  WIDE's worst calendar-year account yield is no worse than BASE's worst
  All three -> PASS. Either CI spanning zero, or R1c failing -> KILL: +1.2% stays, question closed.

WHAT A PASS LICENSES: paper bots f8-tp20 (and f8-tp20-240), each with a frozen baseline. Never a
change to the live rule: the holdout was already seen, so this is not an out-of-sample result.

A self-check first reproduces the grid's two holdout rows (BASE N=246 +0.489%, WIDE N=232
+0.872%). The 240m hold is printed as a diagnostic only. All F8 caveats carry over: touch-fills,
Binance prints standing in for Hyperliquid, no queue position, unlevered.

Run:
  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
  PYTHONPATH="src;." .venv/Scripts/python probes/r1_f8_wide_exit.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from coinmon.data import db
from probes.f8_cascade_ladder_proxy import MAKER, SEED
from probes.f8_param_grid import BASE, BOOT, HOLDOUT_DAYS, simulate
from probes.f8_repeg_deadband import EXCHANGE, SYMBOLS

WIDE = (0.025, 0.020, 60)
WIDE_240 = (0.025, 0.020, 240)  # diagnostic only


def main() -> None:
    conn = db.connect()
    data = {}
    for s in SYMBOLS:
        df = db.read_candles(conn, EXCHANGE, s, "1m")
        data[s] = (df["open_time"].to_numpy("int64"), df["low"].to_numpy(float),
                   df["high"].to_numpy(float), df["close"].to_numpy(float))
    first = pd.Timestamp(min(int(v[0][0]) for v in data.values()), unit="ms", tz="UTC")
    last = pd.Timestamp(max(int(v[0][-1]) for v in data.values()), unit="ms", tz="UTC")
    cut = (last - pd.Timedelta(days=HOLDOUT_DAYS)).normalize()
    k = len(SYMBOLS)

    def run(cell) -> pd.DataFrame:
        rows = [(s, *e) for s, v in data.items() for e in simulate(*v, *cell)]
        ev = pd.DataFrame(rows, columns=["sym", "t", "net", "mae"])
        ev["day"] = pd.to_datetime(ev["t"], unit="ms", utc=True).dt.normalize()
        return ev

    ev = {c: run(c) for c in (BASE, WIDE, WIDE_240)}
    ho = {c: e[e["day"] >= cut] for c, e in ev.items()}
    print(f"self-check, holdout {cut.date()} -> {last.date()}:")
    for c, want in ((BASE, (246, 0.489)), (WIDE, (232, 0.872))):
        n, mean = len(ho[c]), ho[c]["net"].mean() * 100
        ok = n == want[0] and round(mean, 3) == want[1]
        print(f"  {c[1] * 100:.1f}% TP: N={n} mean {mean:+.3f}%  (grid: N={want[0]}"
              f" {want[1]:+.3f}%) {'OK' if ok else 'MISMATCH'}")
        if not ok:
            print("SELF-CHECK FAILED: the replay does not reproduce the grid; stopping.")
            return

    def paired(wide, lo_day, hi_day, label) -> bool:
        years = (hi_day - lo_day).days / 365.25
        parts = []
        for c in (wide, BASE):
            e = ev[c][(ev[c]["day"] >= lo_day) & (ev[c]["day"] < hi_day)]
            parts.append(e.groupby("day")["net"].sum())
        diff = parts[0].sub(parts[1], fill_value=0.0).to_numpy()
        rng = np.random.default_rng(SEED)
        boots = diff[rng.integers(0, len(diff), (BOOT, len(diff)))].sum(axis=1) / k / years
        lo, hi = np.percentile(boots, [2.5, 97.5])
        a, b = (p.sum() / k / years * 100 for p in parts)
        print(f"  {label:<8} wide {a:+6.2f}%/yr  base {b:+6.2f}%/yr  diff {a - b:+6.2f}%/yr"
              f"  95% CI [{lo * 100:+.2f}%, {hi * 100:+.2f}%]  ({len(diff)} days)"
              f"  {'ex-zero' if lo > 0 or hi < 0 else 'spans zero'}")
        return bool(lo > 0)

    end = last.normalize() + pd.Timedelta(days=1)
    print("\nWIDE 2.5/2.0/60 - BASE 2.5/1.2/60, paired by UTC day:")
    r1a = paired(WIDE, first.normalize(), cut, "train")
    r1b = paired(WIDE, cut, end, "holdout")

    def yearly(c) -> dict[int, float]:
        out = {}
        for y in range(first.year, last.year + 1):
            lo = max(first, pd.Timestamp(f"{y}-01-01", tz="UTC"))
            hi = min(end, pd.Timestamp(f"{y + 1}-01-01", tz="UTC"))
            e = ev[c]
            out[y] = e.loc[e["day"].dt.year == y, "net"].sum() / k / ((hi - lo).days / 365.25)
        return out

    yb, yw, yw240 = yearly(BASE), yearly(WIDE), yearly(WIDE_240)
    print("\naccount yield by calendar year (1x):")
    print("  year    base    wide  wide-240m")
    for y in yb:
        print(f"  {y}  {yb[y] * 100:+6.2f}% {yw[y] * 100:+6.2f}%  {yw240[y] * 100:+6.2f}%")
    r1c = min(yw.values()) >= min(yb.values())
    print(f"  worst year: base {min(yb.values()) * 100:+.2f}%  wide {min(yw.values()) * 100:+.2f}%")

    print(f"\nR1a train CI ex-zero     : {'PASS' if r1a else 'FAIL'}")
    print(f"R1b holdout CI ex-zero   : {'PASS' if r1b else 'FAIL'}")
    print(f"R1c worst year not worse : {'PASS' if r1c else 'FAIL'}")
    print(f"\nVERDICT: {'PASS (paper bots only; post-hoc)' if r1a and r1b and r1c else 'KILL'}")

    # Diagnostics, not part of the verdict.
    print("\ndiagnostics (not the verdict):")
    print("  rule              N   TP hit    mean   MAE med  MAE 5th  breach 3x / 10x / 20x")
    for name, c in (("base 1.2/60", BASE), ("wide 2.0/60", WIDE), ("wide 2.0/240", WIDE_240)):
        e = ev[c]
        hit = np.isclose(e["net"], c[1] - 2 * MAKER).mean()
        mae = e["mae"].to_numpy()
        breach = " / ".join(f"{(mae <= -(1.0 / lev - 0.005)).mean() * 100:.1f}%"
                            for lev in (3, 10, 20))
        print(f"  {name:<13} {len(e):>5}  {hit * 100:5.1f}%  {e['net'].mean() * 100:+.3f}%"
              f"  {np.median(mae) * 100:+.2f}%  {np.percentile(mae, 5) * 100:+.2f}%   {breach}")
    paired(WIDE_240, first.normalize(), cut, "240 train")
    paired(WIDE_240, cut, end, "240 hold")


if __name__ == "__main__":
    main()
