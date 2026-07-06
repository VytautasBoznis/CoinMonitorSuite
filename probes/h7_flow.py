"""Plan-B probe H7 — does per-bar taker-flow (CVD) imbalance predict the NEXT bar's return?

Order-flow direction hypothesis ([[order-flow-direction]]): the aggressor-side imbalance of a
bar (taker buys vs taker sells) carries directional information into the following bar. Binance
klines carry ``takerBuyBaseVolume`` natively and reach back years, so taker-delta is the deepest,
cheapest order-flow signal — no new scraper, no shallow OI history. Trained on USDT majors, the
pristine-USDC split untouched ([[train-usdt-certify-usdc]]).

Frozen rule (2026-07-06, before first run):
  imbalance_t = (takerBuyBase - takerSellBase) / totalVol = (2*takerBuyBase - vol) / vol  in [-1,1]
  Predictive IC = corr(imbalance_t, logret_{t+1}).  PASS if its bootstrap 95% CI excludes 0
  with the SAME sign on >= 2 of the 4 majors (positive sign = flow-momentum, negative =
  flow-contrarian; either is an edge). The contemporaneous corr(imbalance_t, logret_t) is
  MECHANICAL (taker buying moves price inside its own bar) and is reported for CONTEXT ONLY —
  it is not tradable. Fixed analysis, no tuning, no threshold search.

Read-only public Binance data via ccxt; no keys, no orders, no DB (taker volume is not stored).

Run:  .venv/Scripts/python probes/h7_flow.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
TIMEFRAME = "4h"
INTERVAL_MS = 4 * 3600 * 1000
START_MS = 1609459200000  # 2021-01-01 UTC
N_BOOT = 10_000
SEED = 0


def fetch_klines(exchange, symbol: str) -> pd.DataFrame:
    """Page Binance klines forward from START_MS to now, keeping taker-buy base volume
    (field 9), which ccxt's fetch_ohlcv drops. Returns oldest-first."""
    rows: list[list] = []
    start = START_MS
    while True:
        page = exchange.publicGetKlines(
            {"symbol": symbol, "interval": TIMEFRAME, "startTime": start, "limit": 1000}
        )
        if not page:
            break
        rows += page
        last_open = int(page[-1][0])
        if len(page) < 1000:
            break
        start = last_open + INTERVAL_MS
    frame = pd.DataFrame(
        {
            "open_time": [int(r[0]) for r in rows],
            "close": [float(r[4]) for r in rows],
            "volume": [float(r[5]) for r in rows],
            "taker_buy_base": [float(r[9]) for r in rows],
        }
    ).drop_duplicates("open_time").sort_values("open_time")
    return frame


def boot_corr_ci(x: np.ndarray, y: np.ndarray, rng: np.random.Generator):
    """Pearson corr + seeded pairs-bootstrap 95% CI (same estimator as h4/h6)."""
    n = len(x)
    idx = rng.integers(0, n, size=(N_BOOT, n))
    xs, ys = x[idx], y[idx]
    xs = xs - xs.mean(axis=1, keepdims=True)
    ys = ys - ys.mean(axis=1, keepdims=True)
    corrs = (xs * ys).sum(axis=1) / np.sqrt((xs**2).sum(axis=1) * (ys**2).sum(axis=1))
    return float(np.corrcoef(x, y)[0, 1]), *np.percentile(corrs, [2.5, 97.5])


def main() -> None:
    import ccxt

    rng = np.random.default_rng(SEED)
    exchange = ccxt.binance({"enableRateLimit": True})
    print(f"H7 taker-flow (CVD) next-bar prediction — {TIMEFRAME} majors (Binance USDT)")
    print(f"{'sym':<10}{'n':>7}{'contemp':>10}{'IC(t+1)':>10}{'IC 95% CI':>20}  sig")
    signs = []
    for symbol in SYMBOLS:
        k = fetch_klines(exchange, symbol)
        vol = k["volume"].to_numpy()
        vol_safe = np.where(vol > 0, vol, np.nan)
        imbalance = (2.0 * k["taker_buy_base"].to_numpy() - vol) / vol_safe
        logret = np.log(k["close"].to_numpy())
        logret = np.concatenate([[np.nan], np.diff(logret)])  # ret_t = log(c_t/c_{t-1})

        df = pd.DataFrame(
            {"imb": imbalance, "ret": logret, "next_ret": np.roll(logret, -1)}
        )
        df.loc[df.index[-1], "next_ret"] = np.nan  # roll wraps; kill the wrapped tail
        df = df.dropna()

        contemp = float(np.corrcoef(df["imb"], df["ret"])[0, 1])
        ic, lo, hi = boot_corr_ci(df["imb"].to_numpy(), df["next_ret"].to_numpy(), rng)
        sig = not lo <= 0 <= hi
        if sig:
            signs.append(1 if ic > 0 else -1)
        span = (
            f"{pd.to_datetime(k['open_time'].iloc[0], unit='ms').date()}.."
            f"{pd.to_datetime(k['open_time'].iloc[-1], unit='ms').date()}"
        )
        print(f"{symbol:<10}{len(df):>7}{contemp:>10.3f}{ic:>10.3f}"
              f"{f'[{lo:+.3f},{hi:+.3f}]':>20}  {'*' if sig else ''}   {span}")

    if len(signs) >= 2 and abs(sum(signs)) == len(signs):
        direction = "momentum" if sum(signs) > 0 else "contrarian"
        print(f"\nH7 VERDICT: PASS — next-bar IC significant, same sign ({direction}) "
              f"on {len(signs)}/4 majors")
    else:
        print(f"\nH7 VERDICT: FAIL — need same-sign significant next-bar IC on >=2/4 majors "
              f"(got {len(signs)} significant)")


if __name__ == "__main__":
    main()
