"""T0 probe H6 — funding carry premium on Bybit USDC perps (pre-registered, alpha-hunt.md §1.5).

Frozen rule (2026-07-02, before first run): PASS if (a) the mean funding rate's bootstrap
95% CI excludes 0 (a structural carry exists), OR (b) the IC — corr(day's summed funding,
NEXT day's return) — has a 95% CI excluding 0 (funding predicts). Either finds W3's data
plumbing in chunk T. Read-only public data via ccxt; no keys, no orders.

Run:  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
      .venv/Scripts/python probes/h6_funding.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from coinmon.data import db

SYMBOLS = {"BTC/USDC:USDC": "BTC/USDC", "ETH/USDC:USDC": "ETH/USDC"}
N_BOOT = 10_000
SEED = 0


def fetch_funding(exchange, symbol: str) -> pd.DataFrame:
    """Page the full funding-rate history, newest-first via ``until`` (Bybit rejects a far
    ``since``; its endpoint serves the most recent window and pages backward)."""
    rows: list[dict] = []
    until: int | None = None
    while True:
        params = {"until": until} if until else {}
        page = exchange.fetch_funding_rate_history(symbol, limit=200, params=params)
        if not page:
            break
        rows = page + rows
        oldest = page[0]["timestamp"]
        if until is not None and oldest >= until:
            break
        until = oldest - 1
    frame = pd.DataFrame(
        {"ts": [r["timestamp"] for r in rows], "rate": [r["fundingRate"] for r in rows]}
    ).drop_duplicates("ts").sort_values("ts")
    frame["day"] = pd.to_datetime(frame["ts"], unit="ms", utc=True).dt.floor("D")
    return frame


def boot_mean_ci(x: np.ndarray, rng) -> tuple[float, float]:
    draws = rng.choice(x, size=(N_BOOT, len(x)), replace=True).mean(axis=1)
    return tuple(np.percentile(draws, [2.5, 97.5]))


def boot_corr_ci(x: np.ndarray, y: np.ndarray, rng) -> tuple[float, float, float]:
    idx = rng.integers(0, len(x), size=(N_BOOT, len(x)))
    xs, ys = x[idx], y[idx]
    xs = xs - xs.mean(axis=1, keepdims=True)
    ys = ys - ys.mean(axis=1, keepdims=True)
    corrs = (xs * ys).sum(axis=1) / np.sqrt((xs**2).sum(axis=1) * (ys**2).sum(axis=1))
    return float(np.corrcoef(x, y)[0, 1]), *np.percentile(corrs, [2.5, 97.5])


def main() -> None:
    import ccxt

    rng = np.random.default_rng(SEED)
    exchange = ccxt.bybit({"enableRateLimit": True})
    conn = db.connect()
    carry_pass = ic_pass = False
    for perp, spot in SYMBOLS.items():
        funding = fetch_funding(exchange, perp)
        candles = db.read_candles(conn, "bybit", spot, "1d")
        ret = np.log(candles["close"]).diff()
        ret.index = pd.to_datetime(candles["open_time"], unit="ms", utc=True)

        rates = funding["rate"].to_numpy(dtype=float)
        lo, hi = boot_mean_ci(rates, rng)
        pos = (rates > 0).mean()
        carry_sig = not lo <= 0 <= hi
        carry_pass |= carry_sig

        daily = funding.groupby("day")["rate"].sum()
        joined = pd.DataFrame({"funding": daily, "next_ret": ret.shift(-1)}).dropna()
        ic, ic_lo, ic_hi = boot_corr_ci(
            joined["funding"].to_numpy(), joined["next_ret"].to_numpy(), rng
        )
        ic_sig = not ic_lo <= 0 <= ic_hi
        ic_pass |= ic_sig

        span = f"{funding['day'].iloc[0].date()} → {funding['day'].iloc[-1].date()}"
        print(f"{perp}: {len(rates)} settlements, {span}")
        print(f"  mean rate/8h {rates.mean() * 100:+.4f}%  CI [{lo * 100:+.4f},{hi * 100:+.4f}]"
              f"  {'*' if carry_sig else ''}  ({pos:.0%} positive; "
              f"~{rates.mean() * 3 * 365 * 100:+.1f}%/yr if always long-collecting)")
        print(f"  IC(day funding, next-day ret) {ic:+.3f}  CI [{ic_lo:+.3f},{ic_hi:+.3f}]"
              f"  {'*' if ic_sig else ''}  (n={len(joined)})")
    conn.close()

    verdict = "PASS" if (carry_pass or ic_pass) else "FAIL"
    print(f"\nH6 VERDICT: {verdict} — carry bias significant: {carry_pass}, "
          f"IC significant: {ic_pass}")


if __name__ == "__main__":
    main()
