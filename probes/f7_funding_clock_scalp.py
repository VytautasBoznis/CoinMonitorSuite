"""F7 — FUNDING-SETTLEMENT CLOCK SCALP (Binance USDT-M perps, 1m candles).

Pre-registered 2026-10-08, written BEFORE any Binance funding rate was pulled (the stored funding
is Bybit's; the 1m perp candles are Binance's, and a dodge flow belongs to the venue whose funding
it dodges, so Binance funding is fetched here). Idea 7 of the Fable batch
([[fable-batch-10-probe-queue]]). **Fable's pre-registered expectation: this dies** (fees, turnover).

THE TRADE. When funding is extreme, the side that pays it closes before settlement and reopens
after, paying impact on a clock regardless of price. Fade it: funding very positive -> short at
T-30min, cover at T+15min; very negative -> the mirror long. Sub-hour hold. NOT the refuted
funding-direction signal ([[b16-funding-signal-refuted]]): this is flow around a timestamp.

EVENTS. Every Binance funding settlement T (timestamps from the funding history itself, so 4h and
8h intervals are both handled) on the 10 perps the F8 runs use, 2021-01 -> 2026-09, where the
SIGNAL rate is extreme: |f| >= 0.05% per settlement (5x the 0.01% baseline).
  SIGNAL = the PREVIOUS settlement's rate, fully known at T-30. (Binance streams an estimate of
  the pending rate that is ~94% fixed by T-30; using the settled rate at T would be a small
  look-ahead, so it is a sensitivity only.)
  G = d * (P(T+15) / P(T-30) - 1), d = -sign(signal); P(t) = open of the 1m bar starting at t.
  G is the PRICE move only. The funding the position collects across T is reported separately
  (that is carry, W3/F1 territory), never inside the verdict.

THE FROZEN RULE (all five must hold; ANY miss = KILL):
  R1 SIZE        mean G >= 2 x maker round trip = 8bp. Below = KILL, do not proceed to net.
  R2 SIGNIFICANCE  t >= 3, clustered by settlement: events sharing a T are averaged into one
                 value first (one market move hits every symbol at once), t over those means.
  R3 SAMPLE      N >= 500 events.
  R4 OUT-OF-ASSET  mean G > 0 in >= 2/3 of the symbols that have >= 20 events.
  R5 REGIME      mean G > 0 in >= 2 disjoint calendar years.

HONESTY CAVEATS (flagged before running): maker entry exactly at T-30 and exit at T+15 is not
guaranteed (a resting order may not fill on a clock); the 1m open is a mid proxy, not a fill;
survivor-only universe of 10 large perps.

Run:
  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
  PYTHONPATH="src;." .venv/Scripts/python probes/f7_funding_clock_scalp.py
"""
from __future__ import annotations

import json
import urllib.request

import numpy as np
import pandas as pd

from coinmon.data import db

EXCHANGE, TIMEFRAME = "binance", "1m"
FUNDING_URL = "https://fapi.binance.com/fapi/v1/fundingRate"
SYMBOLS = {  # unified (as the 1m perp candles are stored) -> Binance id
    "BTC/USDT:USDT": "BTCUSDT", "ETH/USDT:USDT": "ETHUSDT", "SOL/USDT:USDT": "SOLUSDT",
    "DOGE/USDT:USDT": "DOGEUSDT", "AVAX/USDT:USDT": "AVAXUSDT", "NEAR/USDT:USDT": "NEARUSDT",
    "LINK/USDT:USDT": "LINKUSDT", "1000SHIB/USDT:USDT": "1000SHIBUSDT", "ADA/USDT:USDT": "ADAUSDT",
    "XRP/USDT:USDT": "XRPUSDT",
}
START_MS = int(pd.Timestamp("2021-01-01", tz="UTC").timestamp() * 1000)
END_MS = int(pd.Timestamp("2026-10-01", tz="UTC").timestamp() * 1000)

THRESH = 0.0005
PRE_MIN, POST_MIN = 30, 15
MAKER = 0.0002
R1_MIN = 2 * 2 * MAKER
R2_MIN_T = 3.0
R3_MIN_N = 500
R4_MIN_EVENTS = 20
R4_FRAC = 2 / 3


def _fetch_funding(conn, symbol: str, native: str) -> pd.DataFrame:
    """Binance settled funding, stored as exchange 'binance' (natural key; re-runs upsert)."""
    rows, start = [], START_MS
    while start < END_MS:
        url = f"{FUNDING_URL}?symbol={native}&startTime={start}&endTime={END_MS}&limit=1000"
        with urllib.request.urlopen(url, timeout=60) as r:
            page = json.load(r)
        if not page:
            break
        rows += [(int(p["fundingTime"]), float(p["fundingRate"])) for p in page]
        start = int(page[-1]["fundingTime"]) + 1
    db.insert_funding(conn, EXCHANGE, symbol, rows)
    return pd.DataFrame(rows, columns=["funding_time", "rate"])


def _events(fund: pd.DataFrame, candles: pd.DataFrame, symbol: str) -> pd.DataFrame:
    opens = pd.Series(candles["open"].to_numpy(float), index=candles["open_time"].to_numpy("int64"))
    t = (fund["funding_time"].to_numpy("int64") + 30_000) // 60_000 * 60_000  # snap to the minute
    rate = fund["rate"].to_numpy(float)
    out = []
    for k in range(1, len(t)):
        signal, settled = rate[k - 1], rate[k]
        if abs(signal) < THRESH:
            continue
        p_pre = opens.get(t[k] - PRE_MIN * 60_000)
        p_set = opens.get(t[k])
        p_post = opens.get(t[k] + POST_MIN * 60_000)
        if p_pre is None or p_set is None or p_post is None:
            continue
        d = -np.sign(signal)
        out.append({"symbol": symbol, "T": t[k], "year": pd.Timestamp(t[k], unit="ms").year,
                    "signal": signal, "settled": settled,
                    "G": d * (p_post / p_pre - 1.0),
                    "G_pre": d * (p_set / p_pre - 1.0), "G_post": d * (p_post / p_set - 1.0),
                    "funding_rcvd": -d * settled})  # a short receives positive funding
    return pd.DataFrame(out)


def _cluster_t(ev: pd.DataFrame, col: str = "G") -> float:
    m = ev.groupby("T")[col].mean().to_numpy()
    return float(m.mean() / (m.std(ddof=1) / np.sqrt(len(m)))) if len(m) > 1 else 0.0


def main() -> None:
    conn = db.connect()
    frames = []
    for symbol, native in SYMBOLS.items():
        fund = _fetch_funding(conn, symbol, native)
        candles = db.read_candles(conn, EXCHANGE, symbol, TIMEFRAME)
        ev = _events(fund, candles, symbol)
        print(f"  {symbol:<20} {len(fund):>5} settlements  ->  {len(ev):>4} extreme events")
        frames.append(ev)
    ev = pd.concat(frames, ignore_index=True)

    mean, t = ev["G"].mean(), _cluster_t(ev)
    print(f"\n{'=' * 72}\nF7 FUNDING-CLOCK SCALP — {len(ev)} events, {ev['T'].nunique()} settlement "
          f"clusters, |signal| >= {THRESH * 100:.2f}%\n{'=' * 72}")
    print(f"  mean gross G (T-30 -> T+15) : {mean * 1e4:+.2f} bp   cluster t {t:+.2f}")
    by_sym = ev.groupby("symbol")["G"].agg(["mean", "count"])
    print("  per symbol:")
    for s, row in by_sym.iterrows():
        print(f"    {s:<20} {row['mean'] * 1e4:+7.2f} bp  n={int(row['count'])}")
    by_year = ev.groupby("year")["G"].agg(["mean", "count"])
    print("  per year:")
    for y, row in by_year.iterrows():
        print(f"    {y}  {row['mean'] * 1e4:+7.2f} bp  n={int(row['count'])}")

    eligible = by_sym[by_sym["count"] >= R4_MIN_EVENTS]
    r1 = mean >= R1_MIN
    r2 = t >= R2_MIN_T
    r3 = len(ev) >= R3_MIN_N
    r4 = len(eligible) > 0 and (eligible["mean"] > 0).mean() >= R4_FRAC
    r5 = int((by_year["mean"] > 0).sum()) >= 2
    print(f"\n  R1 mean G >= {R1_MIN * 1e4:.0f} bp (2x maker RT) : {'PASS' if r1 else 'FAIL'}")
    print(f"  R2 cluster t >= {R2_MIN_T:.0f}              : {'PASS' if r2 else 'FAIL'}")
    print(f"  R3 N >= {R3_MIN_N}                      : {'PASS' if r3 else 'FAIL'} (N={len(ev)})")
    print(f"  R4 >= 2/3 symbols positive        : {'PASS' if r4 else 'FAIL'} "
          f"({int((eligible['mean'] > 0).sum())}/{len(eligible)} with >= {R4_MIN_EVENTS} events)")
    print(f"  R5 positive in >= 2 years         : {'PASS' if r5 else 'FAIL'}")
    verdict = "PASS" if all((r1, r2, r3, r4, r5)) else "KILL"
    print(f"\n  VERDICT: {verdict}")
    _diagnostics(ev)


# ============================================================ POST-VERDICT DIAGNOSTICS (not frozen)


def _diagnostics(ev: pd.DataFrame) -> None:
    print(f"\n{'=' * 72}\nDIAGNOSTICS — not the verdict\n{'=' * 72}")
    print(f"  dodge-then-reopen split: T-30 -> T {ev['G_pre'].mean() * 1e4:+.2f} bp "
          f"(t {_cluster_t(ev, 'G_pre'):+.2f}),  T -> T+15 {ev['G_post'].mean() * 1e4:+.2f} bp "
          f"(t {_cluster_t(ev, 'G_post'):+.2f})")
    for side, g in (("short (signal > 0)", ev[ev["signal"] > 0]), ("long (signal < 0)", ev[ev["signal"] < 0])):
        if len(g):
            print(f"  {side:<20} n={len(g):>4}  G {g['G'].mean() * 1e4:+.2f} bp  t {_cluster_t(g):+.2f}")
    net = ev["G"] + ev["funding_rcvd"] - 2 * MAKER
    print(f"  with funding collected at T, minus maker RT: {net.mean() * 1e4:+.2f} bp/event "
          f"(funding alone {ev['funding_rcvd'].mean() * 1e4:+.2f} bp)")
    same = ev[ev["settled"].abs() >= THRESH]
    print(f"  look-ahead sensitivity (settled-at-T also extreme): n={len(same)}  "
          f"G {same['G'].mean() * 1e4:+.2f} bp  t {_cluster_t(same):+.2f}")


if __name__ == "__main__":
    main()
