"""F9 — WEEKEND VARIANCE RISK PREMIUM, proxy probe (Deribit DVOL vs weekend realized vol).

Pre-registered 2026-10-08, written BEFORE any DVOL value was pulled. Idea 9 of the Fable batch
([[fable-batch-10-probe-queue]]). The thresholds are Fable's; the HAC t-stat and the both-coins
requirement are tightenings declared here, before data.

THE TRADE (later, only on a pass): sell delta-hedged short-dated BTC/ETH strangles on Friday, cover
Monday. Weekend realized vol is said to run systematically under short-dated implied vol.

WHY IT SHOULD PAY. Lottery-call buyers and crash hedgers overpay for convexity; the seller is paid
to warehouse crash risk, which this account is authorized to hold ([[riskier-strategies-allowed]]).

THE PROXY. Per weekend w:
  IV_w  = DVOL (Deribit's 30-day implied vol index) at Fri 00:00 UTC, the open of the 12h bar.
  RV_w  = realized vol of 5-minute log returns of Binance spot (BTC/USDT, ETH/USDT), Fri 00:00 ->
          Mon 00:00 UTC (864 returns), annualized on calendar time: sqrt(sum r^2 * 365 / 3).
  gap_w = IV_w - RV_w, in vol points.
A weekend counts only if DVOL has its Fri 00:00 bar and >= 95% of the 865 five-minute price
points exist (missing points are forward-filled for the returns, never invented at the edges).

THE FROZEN RULE, per coin (all five must hold; ANY miss = KILL for that coin):
  R1 SAMPLE      >= 150 valid weekends.
  R2 SIZE        mean gap >= +3.0 vol pts (Fable's KILL at <= 1.5 is inside this).
  R3 SIGNIFICANCE  t >= 3, Newey-West HAC with 4 lags (vol regimes span weeks, so weekends are
                 not independent draws; a plain t would overstate significance).
  R4 HIT         gap > 0 in >= 60% of weekends.
  R5 REGIME      mean gap > 0 in EACH calendar year 2022, 2023, 2024, 2025.
  IDEA VERDICT: PASS iff BOTH BTC and ETH pass. Either KILL = the idea is KILLED.

HONESTY CAVEATS (flagged before running, not after):
  * THE PROXY IS BIASED TOWARD PASSING, and this is the main thing to know about it. DVOL is a
    30-day constant-maturity index; weekends are known to be quieter than weekdays, and Deribit's
    short-dated options already price weekend variance lower than the 30-day surface. So IV_w - RV_w
    mixes a real premium with a known calendar effect that a Friday strangle seller is NOT paid
    for. Pre-declared control (part of the reading, not the verdict): the same construction on
    WEEKDAYS (IV at Mon 00:00, RV Mon 00:00 -> Thu 00:00). Weekend gap ~ weekday gap = a generic
    vol premium, nothing weekend-specific. Weekend gap >> weekday gap = mostly the calendar effect
    the market already prices.
  * Vol points are not yield. Nothing here says what a hedged strangle earns after spread, hedge
    cost and the crash weekends; it cannot be compared to the 5%/yr hurdle ([[live-yield-hurdle]]).
  * A PASS licenses ONE next step only: stage 2 on real short-dated option prints (Monday-expiry
    IVs at Friday 08:00 from Deribit's free trade history), with its own rule frozen before that
    pull. Never plumbing, never a deployment.
  * Price source: Binance spot, not the Deribit index (a multi-venue spot composite). At 5-minute
    sampling the two differ by noise, not by regime.

Run:
  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
  PYTHONPATH="src;." .venv/Scripts/python probes/f9_weekend_vrp_proxy.py
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

from coinmon.data import db

DVOL_URL = "https://www.deribit.com/api/v2/public/get_volatility_index_data"
COINS = {"BTC": "BTC/USDT", "ETH": "ETH/USDT"}
EXCHANGE, TIMEFRAME = "binance", "1m"

STEP_MS = 5 * 60_000  # 5-minute sampling
WINDOW_H = 72  # Fri 00:00 -> Mon 00:00, and Mon 00:00 -> Thu 00:00 for the weekday control
MIN_COVERAGE = 0.95

R1_MIN_N = 150
R2_MIN_GAP = 3.0
R3_MIN_T = 3.0
R4_MIN_HIT = 0.60
R5_YEARS = (2022, 2023, 2024, 2025)
HAC_LAGS = 4


def _dvol(currency: str) -> pd.Series:
    """DVOL 12h-bar opens indexed by bar start (ms). Pages backwards via `continuation`."""
    end = int(pd.Timestamp.now(tz="UTC").timestamp() * 1000)
    start = int(pd.Timestamp("2020-01-01", tz="UTC").timestamp() * 1000)
    rows: dict[int, float] = {}
    for _ in range(100):
        params = {"currency": currency, "start_timestamp": start, "end_timestamp": end,
                  "resolution": "43200"}
        with urllib.request.urlopen(f"{DVOL_URL}?{urllib.parse.urlencode(params)}", timeout=60) as r:
            result = json.load(r)["result"]
        for ts, o, *_ in result["data"]:
            rows[int(ts)] = float(o)
        if not result.get("continuation"):
            break
        end = int(result["continuation"])
    return pd.Series(rows).sort_index()


def _windows(dvol: pd.Series, px: pd.Series, weekday: int) -> pd.DataFrame:
    """One row per window starting 00:00 UTC on `weekday` (4 = Fri, 0 = Mon): IV, RV, gap."""
    first = pd.Timestamp(max(dvol.index[0], px.index[0]), unit="ms", tz="UTC").normalize()
    last = pd.Timestamp(px.index[-1], unit="ms", tz="UTC")
    out = []
    for day in pd.date_range(first, last, freq="D"):
        if day.weekday() != weekday or day + pd.Timedelta(hours=WINDOW_H) > last:
            continue
        t0 = int(day.timestamp() * 1000)
        if t0 not in dvol.index:
            continue
        grid = np.arange(t0, t0 + WINDOW_H * 3_600_000 + 1, STEP_MS)
        p = px.reindex(grid)
        if p.notna().mean() < MIN_COVERAGE or np.isnan(p.iloc[0]):
            continue
        r = np.diff(np.log(p.ffill().to_numpy()))
        rv = float(np.sqrt((r**2).sum() * 365.0 / (WINDOW_H / 24.0))) * 100.0
        out.append({"day": day, "year": day.year, "iv": float(dvol[t0]), "rv": rv})
    df = pd.DataFrame(out)
    df["gap"] = df["iv"] - df["rv"]
    return df


def _hac_t(x: np.ndarray, lags: int = HAC_LAGS) -> float:
    """Newey-West t-stat of the mean (Bartlett weights)."""
    n, e = len(x), x - x.mean()
    var = e @ e / n
    for k in range(1, lags + 1):
        var += 2.0 * (1.0 - k / (lags + 1)) * (e[k:] @ e[:-k]) / n
    return float(x.mean() / np.sqrt(var / n))


def _report(label: str, df: pd.DataFrame) -> dict[str, float]:
    g = df["gap"].to_numpy()
    stats = {"n": len(g), "mean": float(g.mean()), "t": _hac_t(g), "hit": float((g > 0).mean())}
    print(f"  {label:<26} N={stats['n']:>4}  IV {df['iv'].mean():6.2f}  RV {df['rv'].mean():6.2f}  "
          f"gap {stats['mean']:+6.2f} pts  HAC t {stats['t']:+5.2f}  hit {stats['hit'] * 100:5.1f}%")
    return stats


def main() -> None:
    conn = db.connect()
    verdicts = {}
    for coin, symbol in COINS.items():
        dvol = _dvol(coin)
        c = db.read_candles(conn, EXCHANGE, symbol, TIMEFRAME)
        # Price at minute boundary t = close of the 1m bar that opened at t - 60s.
        px = pd.Series(c["close"].to_numpy(float), index=c["open_time"].to_numpy("int64") + 60_000)
        wk = _windows(dvol, px, weekday=4)
        ctl = _windows(dvol, px, weekday=0)

        print(f"\n{'=' * 78}\n{coin}: DVOL {pd.Timestamp(dvol.index[0], unit='ms').date()} -> "
              f"{pd.Timestamp(dvol.index[-1], unit='ms').date()}, weekends "
              f"{wk['day'].iloc[0].date()} -> {wk['day'].iloc[-1].date()}\n{'=' * 78}")
        s = _report("WEEKEND Fri->Mon (verdict)", wk)
        print("  per year (weekend gap):")
        by_year = wk.groupby("year")["gap"].agg(["mean", "count"])
        for y, row in by_year.iterrows():
            print(f"    {y}  {row['mean']:+6.2f} pts  n={int(row['count'])}")

        r1 = s["n"] >= R1_MIN_N
        r2 = s["mean"] >= R2_MIN_GAP
        r3 = s["t"] >= R3_MIN_T
        r4 = s["hit"] >= R4_MIN_HIT
        r5 = all(y in by_year.index and by_year.loc[y, "mean"] > 0 for y in R5_YEARS)
        print(f"\n  R1 N >= {R1_MIN_N}                  : {'PASS' if r1 else 'FAIL'}")
        print(f"  R2 mean gap >= {R2_MIN_GAP:.1f} pts        : {'PASS' if r2 else 'FAIL'}")
        print(f"  R3 HAC t >= {R3_MIN_T:.0f}               : {'PASS' if r3 else 'FAIL'}")
        print(f"  R4 hit >= {R4_MIN_HIT * 100:.0f}%                : {'PASS' if r4 else 'FAIL'}")
        print(f"  R5 positive in each of 2022-2025 : {'PASS' if r5 else 'FAIL'}")
        verdicts[coin] = all((r1, r2, r3, r4, r5))
        print(f"  {coin}: {'PASS' if verdicts[coin] else 'KILL'}")

        print("\n  PRE-DECLARED CONTROL (reading, not verdict):")
        _report("WEEKDAY Mon->Thu", ctl)
        print(f"    weekend RV / weekday RV = {wk['rv'].mean() / ctl['rv'].mean():.2f}  "
              f"(IV is the same 30d index in both)")

    idea = "PASS" if all(verdicts.values()) else "KILL"
    per_coin = ", ".join(f"{k} {'PASS' if v else 'KILL'}" for k, v in verdicts.items())
    print(f"\n{'=' * 78}\nF9 PROXY VERDICT: {idea}  ({per_coin})")
    if idea == "PASS":
        print("  Licenses stage 2 (real Monday-expiry option IVs) ONLY — read the weekday control first.")


if __name__ == "__main__":
    main()
