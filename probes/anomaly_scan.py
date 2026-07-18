"""Anomaly scanner — systematic map of cross-sectional + calendar/microstructure deviations from
efficiency, each scored by its NET-OF-FEE annualized long-short spread (the "path to the deploy hurdle"
number the user asked for), not just statistical significance.

Context (2026-07-18): after the edge-hunt exhausted candle+funding+OI on the survivor universe with 0
deployable winners, the user reframed the goal to ANOMALIES with the bar "path to the >=5%/yr deploy
hurdle" and "rank by fastest-doable, start there" ([[riskier-strategies-allowed]],
[[mission-find-edge-ship-ui]]). This scanner is the fastest tier: zero new data, reuses the 41-perp
Bybit USDT panel (1d closes/volume + real funding + the 5yr OI backfill).

WHAT IT MEASURES (all point-in-time, honest fees; SURVIVORSHIP caveat stands — 41 survivors):
  * Cross-sectional FACTORS (rank the universe daily, long top-quintile / short bottom-quintile in the
    signal's hypothesized-positive direction, hold H bars): short-horizon reversal, momentum, low-vol,
    OI de-crowding, low-funding, illiquidity. Reported: gross & NET annualized spread, t-stat, N.
    NET uses taker fee 0.001/side on the rebalance turnover — the "does it clear costs" test.
  * CALENDAR effects on BTC 1d/1h: day-of-week, hour-of-day (which UTC hours carry non-zero mean).
  * FUNDING-SETTLEMENT microstructure: mean 1h return in the settlement bars (00/08/16 UTC) vs others.

Honest reading: with N in the tens of thousands even a trivial effect gets a large |t|, so RANK BY NET
SPREAD, treat |t|>3 (not 2) as the bar, and remember ~20 tests run here (multiple comparisons). A factor
"has a path to the hurdle" iff its NET annualized spread >= +5%/yr at a tradeable turnover.

Run:
  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
  PYTHONPATH="src;." .venv/Scripts/python probes/anomaly_scan.py
"""
from __future__ import annotations

import math
import statistics

import pandas as pd

from coinmon.data import db
from probes.b14_lowvol_neutral import EXCHANGE, TIMEFRAME, FEE, _direct_usdt_legs, load_daily_funding
from probes.b18_oi_crowding import load_oi

Q = 0.2  # quintile long/short


def load_panels(conn, legs):
    """Return (closes, dollar_volume) daily panels aligned on a shared index."""
    close_cols, vol_cols = {}, {}
    for leg in legs:
        df = db.read_candles(conn, EXCHANGE, leg, TIMEFRAME)
        if df.empty:
            continue
        idx = df["open_time"].astype("int64")
        close_cols[leg] = pd.Series(df["close"].values, index=idx)
        vol_cols[leg] = pd.Series((df["close"] * df["volume"]).values, index=idx)  # dollar volume
    closes = pd.DataFrame(close_cols).sort_index()
    dvol = pd.DataFrame(vol_cols).reindex_like(closes)
    return closes, dvol


TAKER, MAKER = 0.001, 0.0002


def ls_spread(signal: pd.DataFrame, ret: pd.DataFrame, hold: int):
    """Long-top-quintile / short-bottom-quintile spread in the signal's positive direction, rebalanced
    every `hold` bars, held `hold` bars. Separates 'is the anomaly real' (GROSS t) from 'can it pay'
    (NET spread at taker vs maker fees, using measured turnover). Returns dict or None."""
    n = len(signal.index)
    warmup = next((i for i in range(n) if signal.iloc[i].notna().sum() >= 10), None)
    if warmup is None or n <= warmup + hold + 1:
        return None
    spreads_gross, turnovers = [], []
    prev_long, prev_short = set(), set()
    for start in range(warmup, n - hold, hold):
        s = signal.iloc[start]
        elig = s[s.notna()]
        if len(elig) < 10:
            continue
        ranked = elig.sort_values()
        k = max(1, round(len(ranked) * Q))
        shorts, longs = set(ranked.index[:k]), set(ranked.index[-k:])
        fwd = ret.iloc[start + 1 : start + 1 + hold]
        lr = ((1.0 + fwd[list(longs)]).prod() - 1.0).mean()
        sr = ((1.0 + fwd[list(shorts)]).prod() - 1.0).mean()
        if lr != lr or sr != sr:
            continue
        spreads_gross.append(lr - sr)
        # fraction of each leg replaced since last rebalance (0..1 per leg) -> round-trip turnover
        turn = (len(longs - prev_long) / max(len(longs), 1) + len(shorts - prev_short) / max(len(shorts), 1))
        turnovers.append(turn)
        prev_long, prev_short = longs, shorts
    if len(spreads_gross) < 8:
        return None
    per_year = 365.0 / hold
    mean_g = statistics.mean(spreads_gross)
    sd = statistics.pstdev(spreads_gross)
    gross_t = mean_g / sd * math.sqrt(len(spreads_gross)) if sd else float("nan")
    avg_turn = statistics.mean(turnovers)  # legs replaced per rebalance (0..2)
    gross_ann = mean_g * per_year
    # avg_turn = fraction of positions newly entered per rebalance (0..2 across both legs); each pays
    # fee on entry and again on its eventual exit -> 2*fee per unit turnover.
    net_taker = (mean_g - 2.0 * avg_turn * TAKER) * per_year
    net_maker = (mean_g - 2.0 * avg_turn * MAKER) * per_year
    return {"gross_ann": gross_ann, "gross_t": gross_t, "net_taker": net_taker,
            "net_maker": net_maker, "turn": avg_turn, "n": len(spreads_gross)}


H1_EXCHANGE = "binance"  # 1h candles live on binance (BTC/ETH/BNB/XRP/SOL), not bybit


def calendar_effects(closes: pd.DataFrame, conn):
    """Day-of-week (1d) and hour-of-day (1h) mean-return effects on BTC, with per-group t-stats."""
    out = []
    btc = closes.get("BTC/USDT")
    if btc is not None:
        r = btc.pct_change().dropna()
        dow = pd.to_datetime(r.index, unit="ms").dayofweek
        for d, name in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
            g = r[dow == d]
            if len(g) > 20:
                t = g.mean() / g.std() * math.sqrt(len(g)) if g.std() else float("nan")
                out.append(("calendar-dow", f"BTC {name}", g.mean() * 365, t, len(g)))
    h1 = db.read_candles(conn, H1_EXCHANGE, "BTC/USDT", "1h")
    if not h1.empty:
        r = h1["close"].pct_change().dropna()
        hours = pd.to_datetime(h1["open_time"].iloc[1:].values, unit="ms").hour
        r.index = hours
        for h in range(24):
            g = r[r.index == h]
            if len(g) > 50:
                t = g.mean() / g.std() * math.sqrt(len(g)) if g.std() else float("nan")
                out.append(("calendar-hod", f"BTC {h:02d}:00 UTC", g.mean() * 24 * 365, t, len(g)))
    return out


def funding_settlement_effect(conn):
    """Mean 1h BTC return in settlement bars (00/08/16 UTC) vs all other hours."""
    h1 = db.read_candles(conn, H1_EXCHANGE, "BTC/USDT", "1h")
    if h1.empty:
        return []
    r = h1["close"].pct_change()
    hours = pd.to_datetime(h1["open_time"].values, unit="ms").hour
    settle = pd.Series(hours, index=r.index).isin([0, 8, 16])
    a, b = r[settle].dropna(), r[~settle].dropna()
    if len(a) < 50 or len(b) < 50:
        return []
    # Welch-ish t on the difference of means
    diff = a.mean() - b.mean()
    se = math.sqrt(a.var() / len(a) + b.var() / len(b))
    t = diff / se if se else float("nan")
    return [("microstructure", "BTC settle-hour vs other (1h)", diff * 24 * 365, t, len(a))]


def main() -> None:
    conn = db.connect()
    legs = _direct_usdt_legs(conn)
    closes, dvol = load_panels(conn, legs)
    have = list(closes.columns)
    funding = load_daily_funding(conn, have, closes.index)
    oi = load_oi(conn, have, closes.index)
    ret = closes.pct_change()

    span = pd.to_datetime(closes.index[0], unit="ms").date(), pd.to_datetime(closes.index[-1], unit="ms").date()
    print(f"ANOMALY SCAN — {EXCHANGE} {len(have)} USDT perps, {TIMEFRAME}, {span[0]} -> {span[1]}")
    print("cross-sectional factors: long top-quintile / short bottom-quintile (signal's positive dir), "
          "net of 0.1%/side fees\n")

    # signal panels, each defined so HIGH = hypothesized OUTPERFORMER
    signals = {
        "ST-reversal(3d)":   -closes.pct_change(3),
        "ST-reversal(1d)":   -ret,
        "momentum(30d)":     closes.pct_change(30),
        "low-vol(30d)":      -ret.rolling(30).std(),
        "oi-decrowd(30d)":   -(oi / oi.shift(30) - 1.0),
        "low-funding(30d)":  -funding.rolling(30).mean(),
        "illiquidity(30d)":  -dvol.rolling(30).mean(),
    }

    rows = []
    for name, sig in signals.items():
        for hold in (5, 20):
            r = ls_spread(sig, ret, hold)
            if r is None:
                continue
            r["name"] = f"{name} H{hold}"
            rows.append(r)

    rows.sort(key=lambda x: x["gross_t"], reverse=True)  # by GROSS significance (is the anomaly real?)
    print(f"{'factor':>22}{'gross/yr':>10}{'gross_t':>9}{'net_tk/yr':>11}{'net_mk/yr':>11}{'turn':>7}{'path?':>7}")
    print("-" * 77)
    for r in rows:
        # path to hurdle = a REAL anomaly (|gross_t|>=3) that clears +5%/yr NET at maker fees
        path = "YES" if r["net_maker"] >= 0.05 and abs(r["gross_t"]) >= 3 else ("weak" if abs(r["gross_t"]) >= 3 else "-")
        print(f"{r['name']:>22}{r['gross_ann']:>+9.1%}{r['gross_t']:>9.2f}{r['net_taker']:>+10.1%}"
              f"{r['net_maker']:>+10.1%}{r['turn']:>7.2f}{path:>7}")

    print("\ncalendar & microstructure (BTC; effect annualized, |t|>3 = notable):")
    cal = calendar_effects(closes, conn) + funding_settlement_effect(conn)
    cal.sort(key=lambda x: abs(x[3]), reverse=True)
    print(f"{'category':>16}{'effect':>26}{'ann':>10}{'t':>7}{'N':>8}")
    print("-" * 67)
    for cat, name, eff, t, n in cal[:12]:
        print(f"{cat:>16}{name:>26}{eff:>+9.1%}{t:>7.2f}{n:>8}")

    conn.close()
    print("\nREAD: 'path? YES' = REAL anomaly (|gross_t|>=3) that clears +5%/yr NET at maker fees "
          "(a standalone path).\n'weak' = real anomaly (|gross_t|>=3) but net<5% — a COMBINE candidate. "
          "gross_t separates\n'is the effect real' from 'can it pay'. ~20 tests — discount borderline |t|.")


if __name__ == "__main__":
    main()
