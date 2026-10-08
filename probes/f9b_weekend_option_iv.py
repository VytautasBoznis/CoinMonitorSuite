"""F9b — WEEKEND VARIANCE RISK PREMIUM, stage 2: real Monday-expiry option prints, not DVOL.

Pre-registered 2026-10-08, written BEFORE any option IV or price was pulled. Stage 1
(`f9_weekend_vrp_proxy.py`, log `runs/f9_weekend_vrp_proxy.log`) PASSED on both coins (DVOL beat
weekend RV by ~+15 vol pts) but its own pre-declared control showed the gap is mostly the weekend
calendar effect: the same 30-day index beats WEEKDAY RV by only +3.4 (BTC) / +1.0 (ETH) pts, and
weekend RV runs ~0.8x weekday RV. The only question left is whether the options that actually span
the weekend already price that discount. This probe asks it on Deribit's own trade prints.

Data seen before writing this (declared): Deribit trade COUNTS per expiry for a handful of
Fri/Sat 08:00-10:00 windows (2021-06, 2022-03, 2024-03, 2026-09), to learn the listing schedule.
No iv, price or index field was looked at. The listing schedule decided the trade's shape: at
Fri 08:00 no Monday expiry exists (dailies list ~2 days ahead), so the pure-weekend option is the
MONDAY 08:00 expiry bought on SATURDAY.

THE TRADE. Sat 10:00 UTC: sell one ATM straddle on the Monday 08:00 UTC expiry (46h to expiry),
1x underlying notional per weekend, hold to expiry, unhedged. (Delta hedging changes the variance,
not the expectation, up to drift; unhedged makes the t-test conservative.)

MEASUREMENT (point-in-time: everything used at Sat 10:00 is printed before Sat 10:00):
  IV_w   median `iv` of Monday-expiry option trades in [Sat 08:00, Sat 10:00) whose taker SOLD
         (direction == "sell": the trade printed at the bid, i.e. what a seller crossing the
         spread receives) and whose strike is within 2% of that trade's index price. A weekend
         needs >= 3 such trades, else it is not counted.
  S0     Binance spot (BTC/USDT, ETH/USDT) at Sat 10:00; the straddle strike is set to S0.
  S_T    mean of Binance 1m closes over (Mon 07:30, Mon 08:00], mirroring Deribit's 30-minute
         index TWAP at delivery.
  r_w    net PnL per unit notional = straddle(IV_w, T=46h)/S0 - |S_T/S0 - 1| - FEES, with
         straddle = 2*(2*N(sigma*sqrt(T)/2) - 1) (Black-76 at the money, zero rates) and FEES = 0.09%
         (0.03% trade fee x 2 legs + 0.015% delivery fee x 2 legs, Deribit's schedule, caps ignored).
  RV_w   realized vol of 5m Binance spot log returns, Sat 10:00 -> Mon 08:00, annualized on
         calendar time; gap_w = IV_w - RV_w in vol points. >= 95% of 5m points must exist.
  CORRECTION (2026-10-08, AFTER the first run printed): the frozen text priced the straddle as
  2*N(s/2) - 1, which is ONE at-the-money call; a straddle is call + put = twice that. The first
  run (KILL on both coins) therefore halved the premium and understated r_w by ~1.2%/weekend. The
  fix is the textbook identity, not a choice; it moves S4/S5 only. S2/S3 (IV vs RV) never touched
  the formula and FAILED on both coins in both runs, so the KILL did not depend on the bug.

THE FROZEN RULE, per coin (all five must hold; ANY miss = KILL for that coin):
  S1 SAMPLE     >= 150 valid weekends. (Fewer = UNDECIDED for lack of listings, not PASS.)
  S2 PREMIUM    mean gap >= +3.0 vol pts (Fable's stage-1 size bar, now on the real option).
  S3 SIGNIFICANCE  HAC (Newey-West, 4 lags) t of the gap >= 3.
  S4 YIELD      52 x mean r_w >= +5.00%/yr on 1x notional ([[live-yield-hurdle]]) AND HAC t of
                r_w >= 2.0.
  S5 REGIME     mean r_w > 0 in EACH calendar year 2022, 2023, 2024, 2025.
  IDEA VERDICT: PASS iff BOTH BTC and ETH pass. Either KILL = the weekend-VRP idea is KILLED.

HONESTY CAVEATS (flagged before running, not after):
  * Bid-side IV from TAKER sells is the price of crossing the spread; resting as a maker would earn
    more. Median of ALL trades (~mid) is printed as the upper-bound sensitivity, never the verdict.
  * 1x notional is the unlevered base; Deribit margin would let the same book run ~5-7x, which
    scales the yield and the crash weekends together. The verdict is judged at 1x, like F8.
  * Synthetic strike K = S0 and one IV per weekend: real strikes are discrete, and the 2h IV is
    an average over moves inside the window.
  * Binance spot stands in for the Deribit index; at 5m sampling the gap is noise, not regime.
  * A PASS is not a deployment and not a certificate: it licenses proposing options plumbing to
    the owner, nothing more. Short convexity: the tail is the trade; read the worst weekends.

Run:
  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
  PYTHONPATH="src;." .venv/Scripts/python probes/f9b_weekend_option_iv.py
"""
from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from coinmon.data import db

TRADES_URL = "https://history.deribit.com/api/v2/public/get_last_trades_by_currency_and_time"
CACHE = Path("data/f9b_option_trades.parquet")  # raw Monday-expiry prints (gitignored /data/)
COINS = {"BTC": "BTC/USDT", "ETH": "ETH/USDT"}
EXCHANGE, TIMEFRAME = "binance", "1m"
FIRST_SAT = pd.Timestamp("2021-01-02", tz="UTC")

T_HOURS = 46.0  # Sat 10:00 -> Mon 08:00
ATM_BAND = 0.02
MIN_TRADES = 3
FEES = 0.0009
STEP_MS = 5 * 60_000
MIN_COVERAGE = 0.95

S1_MIN_N = 150
S2_MIN_GAP = 3.0
S3_MIN_T = 3.0
S4_MIN_YIELD = 0.05
S4_MIN_T = 2.0
S5_YEARS = (2022, 2023, 2024, 2025)
HAC_LAGS = 4


def _ms(ts: pd.Timestamp) -> int:
    return int(ts.timestamp() * 1000)


def _expiry_token(day: pd.Timestamp) -> str:
    return f"{day.day}{day.strftime('%b').upper()}{day:%y}"  # Deribit style, e.g. 11MAR24


def _pull(coin: str, sat: pd.Timestamp) -> list[dict]:
    """All option trades in [Sat 08:00, Sat 10:00), kept only for the Monday expiry."""
    token = _expiry_token(sat + pd.Timedelta(days=2))
    start, end = _ms(sat + pd.Timedelta(hours=8)), _ms(sat + pd.Timedelta(hours=10)) - 1
    keep: list[dict] = []
    while True:
        q = {"currency": coin, "kind": "option", "start_timestamp": start, "end_timestamp": end,
             "count": 1000, "sorting": "asc"}
        for attempt in range(8):
            try:
                with urllib.request.urlopen(f"{TRADES_URL}?{urllib.parse.urlencode(q)}",
                                            timeout=60) as r:
                    res = json.load(r)["result"]
                break
            except (urllib.error.URLError, TimeoutError) as exc:  # 429 / timeouts: back off
                if getattr(exc, "code", 429) != 429 or attempt == 7:
                    raise
                time.sleep(2**attempt)
        for t in res["trades"]:
            _, exp, strike, cp = t["instrument_name"].split("-")
            if exp == token:
                keep.append({"coin": coin, "sat": sat, "ts": t["timestamp"], "strike": float(strike),
                             "cp": cp, "direction": t["direction"], "iv": t.get("iv"),
                             "index_price": t["index_price"]})
        if not res["has_more"] or not res["trades"]:
            return keep
        start = res["trades"][-1]["timestamp"] + 1


def _trades(last_sat: pd.Timestamp) -> pd.DataFrame:
    if CACHE.exists():
        return pd.read_parquet(CACHE)
    sats = pd.date_range(FIRST_SAT, last_sat, freq="7D")
    jobs = [(c, s) for c in COINS for s in sats]
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = [r for chunk in pool.map(lambda j: _pull(*j), jobs) for r in chunk]
    df = pd.DataFrame(rows)
    CACHE.parent.mkdir(exist_ok=True)
    df.to_parquet(CACHE)
    return df


def _ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _straddle(iv_pct: float) -> float:
    """ATM straddle premium / S0 under Black-76 with zero rates (call + put = 2 x call at F = K)."""
    s = iv_pct / 100.0 * math.sqrt(T_HOURS / (365.0 * 24.0))
    return 2.0 * (2.0 * _ncdf(s / 2.0) - 1.0)


def _hac_t(x: np.ndarray, lags: int = HAC_LAGS) -> float:
    n, e = len(x), x - x.mean()
    var = e @ e / n
    for k in range(1, lags + 1):
        var += 2.0 * (1.0 - k / (lags + 1)) * (e[k:] @ e[:-k]) / n
    return float(x.mean() / np.sqrt(var / n))


def _weekends(trades: pd.DataFrame, px: pd.Series) -> pd.DataFrame:
    out = []
    for sat, g in trades.groupby("sat"):
        g = g[g["iv"].notna() & (g["iv"] > 0)]
        atm = g[(g["strike"] / g["index_price"] - 1.0).abs() <= ATM_BAND]
        bid = atm[atm["direction"] == "sell"]
        if len(bid) < MIN_TRADES:
            continue
        t0 = _ms(sat + pd.Timedelta(hours=10))
        t_exp = _ms(sat + pd.Timedelta(days=2, hours=8))
        grid = np.arange(t0, t_exp + 1, STEP_MS)
        p = px.reindex(grid)
        settle = px.reindex(np.arange(t_exp - 29 * 60_000, t_exp + 1, 60_000))
        if p.notna().mean() < MIN_COVERAGE or np.isnan(p.iloc[0]) or settle.isna().all():
            continue
        s0, s_t = float(p.iloc[0]), float(settle.mean())
        r = np.diff(np.log(p.ffill().to_numpy()))
        rv = float(np.sqrt((r**2).sum() * 365.0 * 24.0 / T_HOURS)) * 100.0
        iv_bid, iv_mid = float(bid["iv"].median()), float(atm["iv"].median())
        ask = atm[atm["direction"] == "buy"]
        iv_ask = float(ask["iv"].median()) if len(ask) >= MIN_TRADES else np.nan
        move = abs(s_t / s0 - 1.0)
        out.append({"sat": sat, "year": sat.year, "n_bid": len(bid), "iv": iv_bid, "iv_mid": iv_mid,
                    "rv": rv, "gap": iv_bid - rv, "move": move,
                    "r": _straddle(iv_bid) - move - FEES, "r_mid": _straddle(iv_mid) - move - FEES,
                    "r_long_ask": move - _straddle(iv_ask) - FEES if not np.isnan(iv_ask) else np.nan})
    return pd.DataFrame(out)


def main() -> None:
    conn = db.connect()
    prices = {}
    for coin, symbol in COINS.items():
        c = db.read_candles(conn, EXCHANGE, symbol, TIMEFRAME)
        # Price at minute boundary t = close of the 1m bar that opened at t - 60s.
        prices[coin] = pd.Series(c["close"].to_numpy(float),
                                 index=c["open_time"].to_numpy("int64") + 60_000)
    last = min(pd.Timestamp(p.index[-1], unit="ms", tz="UTC") for p in prices.values())
    last_sat = (last - pd.Timedelta(days=2, hours=8)).normalize()
    last_sat -= pd.Timedelta(days=(last_sat.weekday() - 5) % 7)
    trades = _trades(last_sat)
    print(f"F9b: {len(trades):,} Monday-expiry option prints cached, Saturdays "
          f"{FIRST_SAT.date()} -> {last_sat.date()}")

    verdicts: dict[str, str] = {}
    for coin in COINS:
        wk = _weekends(trades[trades["coin"] == coin], prices[coin])
        print(f"\n{'=' * 78}\n{coin}: {len(wk)} valid weekends, {wk['sat'].iloc[0].date()} -> "
              f"{wk['sat'].iloc[-1].date()}, median {int(wk['n_bid'].median())} bid prints/weekend"
              f"\n{'=' * 78}")
        g, r = wk["gap"].to_numpy(), wk["r"].to_numpy()
        t_gap, t_r, yld = _hac_t(g), _hac_t(r), 52.0 * r.mean()
        print(f"  IV (bid) {wk['iv'].mean():6.2f}   RV {wk['rv'].mean():6.2f}   gap {g.mean():+6.2f} pts"
              f"  HAC t {t_gap:+5.2f}   gap>0 {np.mean(g > 0) * 100:5.1f}%")
        print(f"  straddle net/weekend {r.mean() * 100:+.3f}%  HAC t {t_r:+5.2f}  ->  1x yield "
              f"{yld * 100:+6.2f}%/yr   win {np.mean(r > 0) * 100:5.1f}%")
        by_year = wk.groupby("year").agg(gap=("gap", "mean"), r=("r", "mean"), n=("r", "size"))
        print("  per year:")
        for y, row in by_year.iterrows():
            print(f"    {y}  gap {row['gap']:+6.2f} pts   net {row['r'] * 100:+.3f}%/wknd "
                  f"({row['r'] * 52 * 100:+6.2f}%/yr)  n={int(row['n'])}")

        s1 = len(wk) >= S1_MIN_N
        s2 = g.mean() >= S2_MIN_GAP
        s3 = t_gap >= S3_MIN_T
        s4 = yld >= S4_MIN_YIELD and t_r >= S4_MIN_T
        s5 = all(y in by_year.index and by_year.loc[y, "r"] > 0 for y in S5_YEARS)
        print(f"\n  S1 N >= {S1_MIN_N}                         : {'PASS' if s1 else 'FAIL'}")
        print(f"  S2 mean gap >= {S2_MIN_GAP:.1f} pts               : {'PASS' if s2 else 'FAIL'}")
        print(f"  S3 HAC t(gap) >= {S3_MIN_T:.0f}                 : {'PASS' if s3 else 'FAIL'}")
        print(f"  S4 yield >= {S4_MIN_YIELD * 100:.0f}%/yr AND t(r) >= {S4_MIN_T:.0f}  : {'PASS' if s4 else 'FAIL'}")
        print(f"  S5 net > 0 in each of 2022-2025         : {'PASS' if s5 else 'FAIL'}")
        verdicts[coin] = "PASS" if all((s2, s3, s4, s5)) and s1 else (
            "UNDECIDED" if not s1 and all((s2, s3, s4, s5)) else "KILL")
        print(f"  {coin}: {verdicts[coin]}")
        _diagnostics(wk)

    idea = ("PASS" if all(v == "PASS" for v in verdicts.values())
            else "KILL" if any(v == "KILL" for v in verdicts.values()) else "UNDECIDED")
    per_coin = ", ".join(f"{k} {v}" for k, v in verdicts.items())
    print(f"\n{'=' * 78}\nF9b VERDICT: {idea}  ({per_coin})")


# ============================================================ POST-VERDICT DIAGNOSTICS (not frozen)


def _diagnostics(wk: pd.DataFrame) -> None:
    print("  diagnostics (not the verdict):")
    cutoff = wk["sat"].iloc[-1] - pd.Timedelta(days=730)
    rec = wk[wk["sat"] >= cutoff]
    print(f"    recent 24mo: N={len(rec)}  net {rec['r'].mean() * 100:+.3f}%/wknd -> "
          f"{rec['r'].mean() * 52 * 100:+6.2f}%/yr  HAC t {_hac_t(rec['r'].to_numpy()):+5.2f}  "
          f"gap {rec['gap'].mean():+6.2f} pts")
    print(f"    mid-IV upper bound: net {wk['r_mid'].mean() * 100:+.3f}%/wknd -> "
          f"{wk['r_mid'].mean() * 52 * 100:+6.2f}%/yr (recent {rec['r_mid'].mean() * 52 * 100:+6.2f}%/yr)")
    worst = wk.nsmallest(5, "r")
    print("    worst 5 weekends: " + ", ".join(
        f"{row.sat.date()} {row.r * 100:+.2f}%" for row in worst.itertuples()))
    print(f"    weekends losing > 3% of notional: {int((wk['r'] < -0.03).sum())} of {len(wk)}")

    # Added AFTER the verdict: the sell side lost recently, so is BUYING weekend straddles a lead?
    # DATA-SNOOPED (idea read off this same sample); priced at the ASK (taker-buy prints).
    lg = wk.dropna(subset=["r_long_ask"])
    lr = lg[lg["sat"] >= cutoff]
    print(f"    REVERSE (long straddle at ask, snooped): N={len(lg)}  "
          f"{lg['r_long_ask'].mean() * 52 * 100:+6.2f}%/yr  HAC t "
          f"{_hac_t(lg['r_long_ask'].to_numpy()):+5.2f}  | recent 24mo N={len(lr)} "
          f"{lr['r_long_ask'].mean() * 52 * 100:+6.2f}%/yr  HAC t {_hac_t(lr['r_long_ask'].to_numpy()):+5.2f}")
    by_y = lg.groupby("year")["r_long_ask"].mean() * 52 * 100
    print("      per year %/yr: " + "  ".join(f"{y} {v:+.1f}" for y, v in by_y.items()))
    top = lr.nlargest(3, "r_long_ask")["r_long_ask"].sum() / lr["r_long_ask"].sum() * 100
    print(f"      recent: top-3 weekends = {top:.0f}% of summed PnL  "
          f"(win {np.mean(lr['r_long_ask'] > 0) * 100:.1f}%)")


if __name__ == "__main__":
    main()
