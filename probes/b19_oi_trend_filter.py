"""Plan-B P2 probe B19 — OI-CONFIRMED trend following (does OI rescue the trend signal B17 failed on?).

Pre-registered 2026-07-18, directly building on two results from the same session:
  * B17 (vol-targeted TSMOM portfolio) FAILED — raw time-series trend has no edge on this universe
    (median Sharpe 0.24, 3/16 net-positive).
  * B18 (OI crowding) FAILED as a tradeable book but its diagnostic showed OI carries a WEAK,
    correctly-signed cross-sectional signal (next-bar IC ~-0.03).
Futures-market lore says OI is a TREND-QUALITY filter, not a standalone signal: RISING open interest
confirms a trend (fresh positioning entering — new longs in an uptrend, new shorts in a downtrend),
while FALLING OI warns the move is just position-closing (short-covering / long-liquidation) and is
out of fuel. The crisp, motivated hypothesis: take B17's exact trend position ONLY when OI is rising
over the same window; skip (stay flat on) trends OI does not confirm.

This is B17's construction with ONE variable added (the OI-rising gate) — a disciplined single-factor
test, not a sign-flip fishing trip. Same honest funding/fee model, same LEV=2 vol-targeted inverse-vol
portfolio, same frozen rule. The comparison of record is against B17: does the filter lift the median
Sharpe out of the 0.24 hole toward the 0.70 bar? SURVIVORSHIP caveat stands (41 survivors).

FROZEN RULE (pre-registered before any run — identical to B17's; never adjusted after seeing results).
Grid (M=16): L in {20,40,60,90} x rebalance in {5,20} x mode in {LS,LO}, LEV=2 fixed, OI-rising gate ON.
PASS (informational — funds a full Edge-Certificate run) iff ALL of:
  (a) >= 12/16 configs net-positive, AND (b) median config net Sharpe >= 0.70, AND
  (c) median config annualized net >= +5%/yr, AND (d) median config recent-half net > 0, AND
  (e) median config ex-2022 annualized net >= +5%/yr AND no blow-ups in the median config.

Run:
  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
  PYTHONPATH="src;." .venv/Scripts/python probes/b19_oi_trend_filter.py
"""
from __future__ import annotations

import math
import statistics

import pandas as pd

from coinmon.backtest.xsectional import load_universe_closes
from coinmon.data import db
from probes.b14_lowvol_neutral import EXCHANGE, TIMEFRAME, FEE, _direct_usdt_legs, load_daily_funding, _turnover
from probes.b17_tsmom_portfolio import LEV, VOL_WIN, GRID, _sharpe, _maxdd
from probes.b18_oi_crowding import load_oi


def run_config(closes, funding, oi, L, rb, mode, fee=FEE):
    """B17's vol-targeted TSMOM book with an added OI-rising confirmation gate."""
    ret = closes.pct_change()
    oi_growth = oi / oi.shift(L) - 1.0
    times = closes.index
    year = pd.to_datetime(times, unit="ms").year
    n = len(times)
    warmup = max(L, VOL_WIN) + 1
    if n <= warmup + rb:
        return None
    rebalance_bars = list(range(warmup, n - 1, rb))
    seg_ends = rebalance_bars[1:] + [n - 1]

    eq = 1.0
    curve: list[float] = []
    daily: list[float] = []
    yr_ex22: list[float] = []
    prev_w: dict[str, float] = {}
    blown = False
    gated_frac: list[float] = []  # share of trend names kept after the OI gate (diagnostic)

    for start, end in zip(rebalance_bars, seg_ends, strict=True):
        volwin = ret.iloc[start - VOL_WIN + 1 : start + 1]
        vol = volwin.std()
        past = closes.iloc[start] / closes.iloc[start - L] - 1.0
        oig = oi_growth.iloc[start]
        price_now = closes.iloc[start]
        elig = vol[vol.notna() & price_now.notna() & (vol > 0) & past.notna()]
        if len(elig) < 4:
            continue
        raw: dict[str, float] = {}
        n_trend = n_kept = 0
        for s in elig.index:
            sign = 1.0 if past[s] > 0 else (-1.0 if past[s] < 0 else 0.0)
            if mode == "LO" and sign < 0:
                sign = 0.0
            if sign == 0.0:
                continue
            n_trend += 1
            g = oig.get(s)
            if not (g == g and g > 0):  # OI must be RISING to confirm; NaN/falling => flat
                continue
            n_kept += 1
            raw[s] = sign / float(vol[s])
        if n_trend:
            gated_frac.append(n_kept / n_trend)
        gross = sum(abs(v) for v in raw.values())
        if gross == 0:
            prev_w = {}
            continue
        w = {s: v / gross * LEV for s, v in raw.items()}

        eq *= 1.0 - fee * _turnover(prev_w, w)
        for d in range(start + 1, end + 1):
            rrow, frow = ret.iloc[d], funding.iloc[d]
            pnl = 0.0
            for s, wt in w.items():
                r = rrow.get(s)
                if r == r:
                    pnl += wt * r
                fr = frow.get(s)
                if fr == fr:
                    pnl -= wt * fr
            if 1.0 + pnl <= 0.0:
                blown = True
                eq = 1e-9
                curve.append(eq); daily.append(-1.0); continue
            eq *= 1.0 + pnl
            curve.append(eq); daily.append(pnl)
            if int(year[d]) != 2022:
                yr_ex22.append(pnl)
        prev_w = w

    if len(curve) < 4:
        return None
    years = len(curve) / 365.0
    m = len(curve) // 2
    ex22_ann = (math.prod(1.0 + p for p in yr_ex22) - 1.0) / (len(yr_ex22) / 365.0) if yr_ex22 else float("nan")
    return {
        "net_ann": (curve[-1] - 1.0) / years,
        "net_recent": curve[-1] / curve[m] - 1.0,
        "sharpe": _sharpe(daily),
        "maxdd": _maxdd(curve),
        "ex22_ann": ex22_ann,
        "blown": blown,
        "kept": statistics.mean(gated_frac) if gated_frac else float("nan"),
    }


def main() -> None:
    conn = db.connect()
    legs = _direct_usdt_legs(conn)

    def read(sym):
        return db.read_candles(conn, EXCHANGE, sym, TIMEFRAME)

    closes = load_universe_closes(read, legs)
    have = [c for c in legs if c in closes.columns]
    funding = load_daily_funding(conn, have, closes.index)
    oi = load_oi(conn, have, closes.index)
    conn.close()
    years = len(closes) / 365.0

    print(f"B19 OI-confirmed TSMOM — {EXCHANGE} {len(have)} USDT perps, {TIMEFRAME}, "
          f"{pd.to_datetime(closes.index[0], unit='ms').date()} -> "
          f"{pd.to_datetime(closes.index[-1], unit='ms').date()}, LEV={LEV}, OI-rising gate ON\n")

    hdr = (f"{'L':>4}{'reb':>5}{'mode':>5}{'net/yr':>9}{'Sharpe':>8}{'maxDD':>8}"
           f"{'net_rec':>9}{'ex22/yr':>9}{'kept%':>7}{'blow':>6}")
    print(hdr)
    print("-" * len(hdr))
    anns, sharpes, recents, ex22s, blows = [], [], [], [], []
    n_pos = 0
    for L, rb, mode in GRID:
        r = run_config(closes, funding, oi, L, rb, mode)
        if r is None:
            print(f"{L:>4}{rb:>5}{mode:>5}   (insufficient history)")
            continue
        n_pos += r["net_ann"] > 0
        anns.append(r["net_ann"]); sharpes.append(r["sharpe"]); recents.append(r["net_recent"])
        ex22s.append(r["ex22_ann"]); blows.append(r["blown"])
        print(f"{L:>4}{rb:>5}{mode:>5}{r['net_ann']:>+8.1%}{r['sharpe']:>8.2f}{r['maxdd']:>+8.1%}"
              f"{r['net_recent']:>+8.1%}{r['ex22_ann']:>+8.1%}{r['kept']:>6.0%}{'YES' if r['blown'] else '-':>6}")

    med_ann = statistics.median(anns)
    med_sharpe = statistics.median(sharpes)
    med_recent = statistics.median(recents)
    med_ex22 = statistics.median(ex22s)
    print(f"\nconfigs net-positive: {n_pos}/{len(anns)}")
    print(f"median net: {med_ann:+.2%}/yr | median Sharpe: {med_sharpe:.2f} | "
          f"median recent-half: {med_recent:+.1%} | median ex-2022: {med_ex22:+.2%}/yr")
    print("(compare B17 no-gate: median Sharpe 0.24, median -11.6%/yr, 3/16 positive)")

    pass_a = n_pos >= 12
    pass_b = med_sharpe >= 0.70
    pass_c = med_ann >= 0.05
    pass_d = med_recent > 0
    pass_e = med_ex22 >= 0.05 and not any(blows)
    ok = lambda b: "#OK" if b else "no"
    verdict = "PASS" if all((pass_a, pass_b, pass_c, pass_d, pass_e)) else "FAIL"
    print(f"\nB19 VERDICT: {verdict} — >=12/16 pos [{ok(pass_a)}] AND med Sharpe>=0.70 [{ok(pass_b)}] "
          f"AND med>=+5%/yr [{ok(pass_c)}] AND med recent>0 [{ok(pass_d)}] AND ex-2022>=+5%/yr & no-blow "
          f"[{ok(pass_e)}] (informational; a PASS funds a full Edge-Certificate run).")


if __name__ == "__main__":
    main()
