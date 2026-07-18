"""Fresh-ideation probe B17 — vol-targeted TIME-SERIES-MOMENTUM (CTA/trend-following) PORTFOLIO
(pre-registered 2026-07-18, after "riskier strategies allowed" and the low-vol lead was closed by
the B14d decomposition).

WHY THIS IS DISTINCT FROM EVERYTHING ALREADY TESTED AND REFUTED:
  * NOT cross-sectional momentum (W5 ranked coins against each other — weak, [[xsectional-momentum-first-run]]).
    This is TIME-SERIES momentum: each coin's position is the sign of ITS OWN trailing return.
  * NOT the single-pair genome trend the GA searched (calibrated-negative, [[certified-sweep-calibrated-negative]]).
    The documented CTA edge is a PORTFOLIO effect: individual-asset trend is noisy, but an inverse-vol,
    risk-balanced basket across many assets has a respectable Sharpe. The rig never tested a diversified
    vol-targeted TSMOM book.
  * NOT B14's survivorship-suspect static short-high-vol leg. TSMOM captures downtrends HONESTLY: it goes
    short a LIQUID name only while that name is itself trending down, and exits when the trend turns — it
    does not depend on delisted-to-zero coins ([[b13-low-vol-fresh-lead]]).

Time-series momentum is the best-documented systematic crypto edge in the 2018-2024 literature and is
directional + leverageable — squarely inside the newly-allowed "riskier" envelope.

CONSTRUCTION (honest, executable):
  * Universe: 41 Bybit USDT direct perps, 1d. Same real per-symbol funding as CERTIFIED carry / B14
    (long pays, short receives), taker fee 0.001/side on turnover.
  * Signal per coin at each rebalance: s = sign(close_now / close_{L bars ago} - 1), point-in-time.
    mode LO (long-only) zeroes shorts; mode LS (long-short) keeps them.
  * Risk balancing: inverse-vol weights (1/recent-daily-vol), normalized so gross = LEV. Low-vol names
    get more weight; every name contributes ~equal risk. LEV=2 (moderate CTA leverage, bounded).
  * Book compounds per bar; a bar that would take equity <= 0 is a LIQUIDATION (flagged, not silently
    clipped) — the honest leverage treatment ([[leverage-breaks-fitness-scaling]]).

FROZEN RULE (pre-registered before any run — never adjusted after seeing results). Grid (M=16):
  L in {20,40,60,90} x rebalance in {5,20} x mode in {LS,LO}, LEV=2 fixed.
PASS (informational — a PASS funds a full Edge-Certificate run, never "trade it") iff ALL of:
  (a) >= 12/16 configs net-positive (after fees AND funding), AND
  (b) median config net Sharpe >= 0.70 (CTA-respectable, annualized from daily P&L), AND
  (c) median config annualized net return >= +5%/yr (the deploy hurdle, [[live-yield-hurdle]]), AND
  (d) median config recent-half net return > 0 (edge lives in the recent regime), AND
  (e) median config annualized net return EXCLUDING calendar-2022 still >= +5%/yr — the anti-crash-
      artifact guard that B14 FAILED (its whole edge was one crash year). No blow-ups in the median config.

Run:
  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
  PYTHONPATH="src;." .venv/Scripts/python probes/b17_tsmom_portfolio.py
"""
from __future__ import annotations

import math
import statistics

import pandas as pd

from coinmon.backtest.xsectional import load_universe_closes
from coinmon.data import db
from probes.b14_lowvol_neutral import (
    EXCHANGE, TIMEFRAME, FEE, _direct_usdt_legs, load_daily_funding, _turnover,
)

LEV = 2.0
VOL_WIN = 30  # bars of trailing daily vol for the inverse-vol risk weights
GRID = [
    (L, rb, mode)
    for L in (20, 40, 60, 90)
    for rb in (5, 20)
    for mode in ("LS", "LO")
]


def _sharpe(rets: list[float]) -> float:
    if len(rets) < 2:
        return float("nan")
    sd = statistics.pstdev(rets)
    return statistics.mean(rets) / sd * math.sqrt(365.0) if sd else float("nan")


def _maxdd(curve: list[float]) -> float:
    peak, dd = curve[0], 0.0
    for v in curve:
        peak = max(peak, v)
        dd = min(dd, v / peak - 1.0)
    return dd


def run_config(closes: pd.DataFrame, funding: pd.DataFrame, L: int, rb: int, mode: str,
               fee: float = FEE):
    """Vol-targeted TSMOM book. Returns dict or None if history too short."""
    ret = closes.pct_change()
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
    yr: dict[int, float] = {}
    yr_ex22: list[float] = []  # per-bar pnl excluding calendar 2022
    prev_w: dict[str, float] = {}
    blown = False

    for start, end in zip(rebalance_bars, seg_ends, strict=True):
        volwin = ret.iloc[start - VOL_WIN + 1 : start + 1]
        vol = volwin.std()
        past = closes.iloc[start] / closes.iloc[start - L] - 1.0
        price_now = closes.iloc[start]
        elig = vol[vol.notna() & price_now.notna() & (vol > 0) & past.notna()]
        if len(elig) < 4:
            continue
        raw: dict[str, float] = {}
        for s in elig.index:
            sign = 1.0 if past[s] > 0 else (-1.0 if past[s] < 0 else 0.0)
            if mode == "LO" and sign < 0:
                sign = 0.0
            if sign == 0.0:
                continue
            raw[s] = sign / float(vol[s])  # inverse-vol risk weight
        gross = sum(abs(v) for v in raw.values())
        if gross == 0:
            prev_w = {}
            continue
        w = {s: v / gross * LEV for s, v in raw.items()}  # normalize gross -> LEV

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
                    pnl -= wt * fr  # long pays / short receives funding
            if 1.0 + pnl <= 0.0:
                blown = True
                eq = 1e-9
                curve.append(eq)
                daily.append(-1.0)
                continue
            eq *= 1.0 + pnl
            curve.append(eq)
            daily.append(pnl)
            y = int(year[d])
            yr[y] = yr.get(y, 1.0) * (1.0 + pnl)
            if y != 2022:
                yr_ex22.append(pnl)
        prev_w = w

    if len(curve) < 4:
        return None
    years = len(curve) / 365.0
    m = len(curve) // 2
    net_abs = curve[-1] - 1.0
    net_recent = curve[-1] / curve[m] - 1.0
    ex22_ann = (math.prod(1.0 + p for p in yr_ex22) - 1.0) / (len(yr_ex22) / 365.0) if yr_ex22 else float("nan")
    return {
        "net_ann": net_abs / years,
        "net_recent": net_recent,
        "sharpe": _sharpe(daily),
        "maxdd": _maxdd(curve),
        "ex22_ann": ex22_ann,
        "blown": blown,
        "yr": {y: v - 1.0 for y, v in yr.items()},
    }


def main() -> None:
    conn = db.connect()
    legs = _direct_usdt_legs(conn)

    def read(sym: str) -> pd.DataFrame:
        return db.read_candles(conn, EXCHANGE, sym, TIMEFRAME)

    closes = load_universe_closes(read, legs)
    have = [c for c in legs if c in closes.columns]
    funding = load_daily_funding(conn, have, closes.index)
    conn.close()
    years = len(closes) / 365.0

    print(f"B17 vol-targeted TSMOM portfolio — {EXCHANGE} {len(have)} USDT perps, {TIMEFRAME}, "
          f"{pd.to_datetime(closes.index[0], unit='ms').date()} -> "
          f"{pd.to_datetime(closes.index[-1], unit='ms').date()}, LEV={LEV}\n")

    hdr = (f"{'L':>4}{'reb':>5}{'mode':>5}{'net/yr':>9}{'Sharpe':>8}{'maxDD':>8}"
           f"{'net_rec':>9}{'ex22/yr':>9}{'blow':>6}")
    print(hdr)
    print("-" * len(hdr))
    anns: list[float] = []
    sharpes: list[float] = []
    recents: list[float] = []
    ex22s: list[float] = []
    blows: list[bool] = []
    all_yr: dict[int, list[float]] = {}
    n_pos = 0
    for L, rb, mode in GRID:
        r = run_config(closes, funding, L, rb, mode)
        if r is None:
            print(f"{L:>4}{rb:>5}{mode:>5}   (insufficient history)")
            continue
        n_pos += r["net_ann"] > 0
        anns.append(r["net_ann"]); sharpes.append(r["sharpe"]); recents.append(r["net_recent"])
        ex22s.append(r["ex22_ann"]); blows.append(r["blown"])
        for y, v in r["yr"].items():
            all_yr.setdefault(y, []).append(v)
        print(f"{L:>4}{rb:>5}{mode:>5}{r['net_ann']:>+8.1%}{r['sharpe']:>8.2f}{r['maxdd']:>+8.1%}"
              f"{r['net_recent']:>+8.1%}{r['ex22_ann']:>+8.1%}{'YES' if r['blown'] else '-':>6}")

    ran = len(anns)
    med_ann = statistics.median(anns)
    med_sharpe = statistics.median(sharpes)
    med_recent = statistics.median(recents)
    med_ex22 = statistics.median(ex22s)

    btc = closes.get("BTC/USDT")
    btc_hold = float(btc.dropna().iloc[-1] / btc.dropna().iloc[0] - 1.0) if btc is not None else float("nan")
    print(f"\nBTC buy-and-hold: {btc_hold:+.1%} ({btc_hold / years:+.1%}/yr) — the passive alternative")
    print("per-calendar-year median net across configs:")
    for y in sorted(all_yr):
        print(f"  {y}: {statistics.median(all_yr[y]):+.1%}")

    print(f"\nconfigs net-positive: {n_pos}/{ran}")
    print(f"median net: {med_ann:+.2%}/yr | median Sharpe: {med_sharpe:.2f} | "
          f"median recent-half: {med_recent:+.1%} | median ex-2022: {med_ex22:+.2%}/yr")

    pass_a = n_pos >= 12
    pass_b = med_sharpe >= 0.70
    pass_c = med_ann >= 0.05
    pass_d = med_recent > 0
    pass_e = med_ex22 >= 0.05 and not any(blows[i] for i in range(len(blows)))
    ok = lambda b: "#OK" if b else "no"
    verdict = "PASS" if all((pass_a, pass_b, pass_c, pass_d, pass_e)) else "FAIL"
    print(f"\nB17 VERDICT: {verdict} — >=12/16 pos [{ok(pass_a)}] AND med Sharpe>=0.70 [{ok(pass_b)}] "
          f"AND med>=+5%/yr [{ok(pass_c)}] AND med recent>0 [{ok(pass_d)}] AND ex-2022>=+5%/yr & no-blow "
          f"[{ok(pass_e)}] (informational; a PASS funds a full Edge-Certificate run).")


if __name__ == "__main__":
    main()
