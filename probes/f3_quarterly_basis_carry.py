"""F3 — QUARTERLY FUTURES BASIS CARRY, regime-gated (Binance USDT-M quarterlies, BTC + ETH).

Pre-registered 2026-10-08, written BEFORE any futures price was pulled (only the first/last
timestamps of the continuous-kline series were checked, to learn the history starts 2021-02).
Idea 3 of the Fable batch ([[fable-batch-10-probe-queue]]). Fable's rule; accounting choices
below are declared before data.

THE TRADE. Cash-and-carry: long spot, short the same coin's dated quarterly future, entered at a
daily close only when the annualized basis b = (F/S - 1) * 365 / dte exceeds 10% with dte >= 30
days; held to delivery, where the future settles to the index and the locked basis is captured
whatever the price does. Then flat until the next qualifying close. Pays: longs who want fixed-
date leverage without stochastic funding. On Bybit only BTC/ETH USDC expiries exist
([[bybit-only-leverage-doctrine]]), so research runs on Binance's deeper history.

MECHANICS (frozen):
  * Contracts: Binance continuous CURRENT_QUARTER and NEXT_QUARTER 1d klines. Expiry = last
    Friday of Mar/Jun/Sep/Dec, 08:00 UTC; at a bar close t, CURRENT = first expiry after t,
    NEXT = the second. Spot = Binance BTCUSDT/ETHUSDT 1d close at the same t.
  * On a flat day, eligible = contracts with dte >= 30 and b > 10%; take the higher b. One
    position per coin at a time; re-entry only on a close after the previous delivery.
  * Net locked return on notional = F/S - 1 - FEES, FEES = 4 maker legs x 2bp = 8bp.
  * 0.5x BOOK (the certified carry / F1 convention): per coin slice C, spot C/2 and 1x future
    margin C/2, so notional = C/2 and the slice earns half the net basis. Two coins = two equal
    slices of one account. Idle slices earn zero.
  * ACCRUAL: each trade's net return accrues linearly from entry to delivery, so a trade still
    open at the span end counts only its elapsed part, and calendar years get what accrued in them.

THE FROZEN RULE (all three must hold; ANY miss = KILL):
  Q1 YIELD      account calendar yield INCLUDING flat periods >= +5.00%/yr (0.5x book).
  Q2 REGIME     accrued PnL positive in >= 2 disjoint calendar years.
  Q3 NOT ONE REGIME  no single calendar year carries > 70% of total accrued PnL.
  Fable's reading: a KILL here demotes it to a regime overlay for F1, never a standalone.

HONESTY CAVEATS (flagged before running): basis is locked only if the short survives to delivery;
1x margin survives a +100% move but the mark-to-market swings are unmodelled. Daily closes are
not fills. Survivor issue is nil (BTC/ETH). The continuous series' roll is Binance's; a sanity
line prints the basis on the last close before each delivery (should be ~0).

Run:
  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
  PYTHONPATH="src;." .venv/Scripts/python probes/f3_quarterly_basis_carry.py
"""
from __future__ import annotations

import json
import urllib.request

import numpy as np
import pandas as pd

FUT_URL = "https://fapi.binance.com/fapi/v1/continuousKlines"
SPOT_URL = "https://api.binance.com/api/v3/klines"
COINS = ("BTCUSDT", "ETHUSDT")
START = pd.Timestamp("2021-01-01", tz="UTC")
END = pd.Timestamp("2026-10-01", tz="UTC")
DAY_MS = 86_400_000

MIN_B = 0.10
MIN_DTE = 30
FEES = 4 * 0.0002
BOOK = 0.5

Q1_MIN = 0.05
Q3_MAX_SHARE = 0.70


def _klines(url: str, params: dict) -> pd.Series:
    """Daily closes indexed by bar CLOSE time (ms), paged forward."""
    out: dict[int, float] = {}
    start = int(START.timestamp() * 1000)
    end = int(END.timestamp() * 1000)
    while start < end:
        q = "&".join(f"{k}={v}" for k, v in {**params, "interval": "1d", "startTime": start,
                                               "endTime": end, "limit": 1000}.items())
        with urllib.request.urlopen(f"{url}?{q}", timeout=60) as r:
            page = json.load(r)
        if not page:
            break
        for k in page:
            out[int(k[0]) + DAY_MS] = float(k[4])
        start = int(page[-1][0]) + DAY_MS
    return pd.Series(out).sort_index()


def _expiries() -> list[pd.Timestamp]:
    out = []
    for y in range(2020, 2028):
        for m in (3, 6, 9, 12):
            last = pd.Timestamp(year=y, month=m, day=1, tz="UTC") + pd.offsets.MonthEnd(0)
            last -= pd.Timedelta(days=(last.weekday() - 4) % 7)  # back to Friday
            out.append(last + pd.Timedelta(hours=8))
    return out


def _trades(coin: str, exp: list[pd.Timestamp]) -> tuple[pd.DataFrame, pd.Series, list[float]]:
    spot = _klines(SPOT_URL, {"symbol": coin})
    cur = _klines(FUT_URL, {"pair": coin, "contractType": "CURRENT_QUARTER"})
    nxt = _klines(FUT_URL, {"pair": coin, "contractType": "NEXT_QUARTER"})
    exp_ms = np.array([int(e.timestamp() * 1000) for e in exp])

    # Sanity: basis on the last close before each delivery should be ~0 (roll is clean).
    last_basis = []
    for e in exp_ms:
        t = e - 8 * 3_600_000  # the 00:00 close on delivery day
        if t in cur.index and t in spot.index:
            last_basis.append(cur[t] / spot[t] - 1.0)

    trades, free_at = [], 0
    for t in spot.index:
        if t < free_at:
            continue
        k = int(np.searchsorted(exp_ms, t, side="right"))
        best = None
        for series, e in ((cur, exp_ms[k]), (nxt, exp_ms[k + 1])):
            if t not in series.index:
                continue
            dte = (e - t) / DAY_MS
            basis = series[t] / spot[t] - 1.0
            b = basis * 365.0 / dte
            if dte >= MIN_DTE and b > MIN_B and (best is None or b > best[0]):
                best = (b, basis, e)
        if best:
            b, basis, e = best
            trades.append({"coin": coin, "entry": t, "delivery": int(e), "b_ann": b,
                           "net": basis - FEES})
            free_at = int(e) + 1
    return pd.DataFrame(trades), spot, last_basis


def _accrue(trades: pd.DataFrame, lo: int, hi: int) -> pd.Series:
    """Per-calendar-year accrued slice return (0.5x book), linear over each trade's life."""
    by_year: dict[int, float] = {}
    for tr in trades.itertuples():
        life = tr.delivery - tr.entry
        for y in range(pd.Timestamp(tr.entry, unit="ms").year,
                       pd.Timestamp(tr.delivery, unit="ms").year + 1):
            y0 = int(pd.Timestamp(f"{y}-01-01", tz="UTC").timestamp() * 1000)
            y1 = int(pd.Timestamp(f"{y + 1}-01-01", tz="UTC").timestamp() * 1000)
            a, b = max(tr.entry, y0, lo), min(tr.delivery, y1, hi)
            if b > a:
                by_year[y] = by_year.get(y, 0.0) + BOOK * tr.net * (b - a) / life
    return pd.Series(by_year).sort_index()


def main() -> None:
    exp = _expiries()
    all_trades, spans, sanity = [], [], {}
    for coin in COINS:
        tr, spot, last_basis = _trades(coin, exp)
        all_trades.append(tr)
        spans.append((int(spot.index[0]), int(spot.index[-1])))
        sanity[coin] = last_basis
    trades = pd.concat(all_trades, ignore_index=True)
    lo, hi = max(s[0] for s in spans), min(s[1] for s in spans)
    years = (hi - lo) / DAY_MS / 365.25

    print(f"F3 QUARTERLY BASIS CARRY — {pd.Timestamp(lo, unit='ms').date()} -> "
          f"{pd.Timestamp(hi, unit='ms').date()} ({years:.2f}y), gate b > {MIN_B * 100:.0f}% ann, "
          f"dte >= {MIN_DTE}d")
    for coin, lb in sanity.items():
        print(f"  roll sanity {coin}: basis at the last close before delivery, median "
              f"{np.median(lb) * 100:+.3f}%, max |{np.max(np.abs(lb)) * 100:.3f}|% over {len(lb)} deliveries")
    print(f"\n  {len(trades)} trades:")
    for tr in trades.itertuples():
        print(f"    {tr.coin}  {pd.Timestamp(tr.entry, unit='ms').date()} -> "
              f"{pd.Timestamp(tr.delivery, unit='ms').date()}  entry b {tr.b_ann * 100:5.1f}%/yr  "
              f"locked net {tr.net * 100:+.2f}%")

    per_coin = [_accrue(trades[trades["coin"] == c], lo, hi) for c in COINS]
    by_year = pd.concat(per_coin, axis=1).fillna(0.0).sum(axis=1) / len(COINS)  # account
    total = float(by_year.sum())
    yld = total / years
    print("\n  account accrued PnL per calendar year (0.5x book, 2 slices):")
    for y, v in by_year.items():
        print(f"    {y}  {v * 100:+.2f}%")
    deployed = sum(min(t.delivery, hi) - max(t.entry, lo) for t in trades.itertuples()
                   if t.delivery > lo and t.entry < hi) / (len(COINS) * (hi - lo))
    print(f"  slices deployed {deployed * 100:.1f}% of the time")

    q1 = yld >= Q1_MIN
    q2 = int((by_year > 0).sum()) >= 2
    q3 = total > 0 and float(by_year.max()) / total <= Q3_MAX_SHARE
    print(f"\n  account yield incl. flat: {yld * 100:+.2f}%/yr")
    print(f"  Q1 yield >= {Q1_MIN * 100:.0f}%/yr incl. flat : {'PASS' if q1 else 'FAIL'}")
    print(f"  Q2 positive in >= 2 years     : {'PASS' if q2 else 'FAIL'}")
    print(f"  Q3 no year > 70% of PnL       : {'PASS' if q3 else 'FAIL'} "
          f"(max year {float(by_year.max()) / total * 100 if total > 0 else float('nan'):.0f}%)")
    print(f"\n  VERDICT: {'PASS' if all((q1, q2, q3)) else 'KILL'}")

    # ---- diagnostics (not the verdict)
    print("\n  diagnostics (not the verdict):")
    cut = hi - 730 * DAY_MS
    recent = sum(_accrue(trades[trades["coin"] == c], cut, hi).sum() for c in COINS) / len(COINS) / 2.0
    print(f"    recent 24mo account yield: {recent * 100:+.2f}%/yr (0.5x)  |  unified-margin 1x book "
          f"would double these: full {yld * 2 * 100:+.2f}%/yr, recent {recent * 2 * 100:+.2f}%/yr")


if __name__ == "__main__":
    main()
