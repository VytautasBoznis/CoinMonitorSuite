"""Fresh-ideation probe B16 — the cross-sectional FUNDING-CROWDING signal (pre-registered 2026-07-06).

Chosen over the queued B15 (hour-of-day seasonality) because the weekday version of that family
already FAILED (probe H2) and B15 is fee-fragile on 1h; this probes a genuinely UNTESTED input.

Hypothesis (documented, crypto positioning literature): a perp's funding rate is a crowding gauge —
persistently HIGH positive funding means longs are crowded and paying up to stay long (over-extended),
and such coins UNDERPERFORM subsequently; LOW / negative funding marks the unloved coins that
outperform. So a cross-sectional book that LONGS the low-funding slice and SHORTS the high-funding
slice should earn the crowding-reversal premium.

Distinct from W3 carry ([[w3-carry-first-live-diagnosis]]): carry is a per-coin DELTA-NEUTRAL cashflow
harvest (short perp + long the SAME coin's spot, price-neutral, collect funding). B16 is a DIRECTIONAL
cross-sectional bet — short coin A (crowded), long coin B (unloved), DIFFERENT coins — wagering that
crowding predicts relative price underperformance. As a bonus the funding cashflow works WITH the
signal here: shorting the high-funding coins also COLLECTS their (high) funding.

Distinct from H6 ([[order-flow-probe-h7-refuted]] neighbourhood): H6 only checked funding on BTC/ETH
as a carry/plumbing test — it never ranked the universe cross-sectionally on funding.

HONEST caveats built into the probe:
  * Real per-symbol Bybit 8h funding applied per bar with correct sign (long pays / short receives) —
    the same data that CERTIFIED carry.
  * Taker fee 0.001 per side on turnover, round-trip into every position.
  * Sharpe AND max-drawdown printed for EVERY config (the lesson from B14: a frozen-rule PASS with a
    sub-1 Sharpe or a drawdown worse than BTC-hold is certificate-worthy at most, never deployable).
  * SURVIVORSHIP: the universe is today's SURVIVING liquid Bybit USDT legs; coins that delisted are
    absent. Flagged, not fixed.

FROZEN RULE (pre-registered before any run — never adjust after seeing results):
  * Universe: Bybit USDT direct legs (1d) that have BOTH candles and perp funding ("<LEG>:USDT").
  * Score: trailing MEAN daily funding over the L-bar window, point-in-time (funding up to the
    rebalance bar only). Rank DESCENDING. LONG the bottom-`q` (lowest funding) slice equal-weight
    (+1); SHORT the top-`q` (highest funding) slice equal-weight (-1); dollar-neutral; any name in
    both slices dropped from the short.
  * Grid (fixed = the M the deflation must survive): L in {7,14,30} x q in {0.1,0.2} x
    rebalance in {7,14} = 12 configs. ALL recorded ([[portfolio-search-protocol]]). Shorter horizons
    than the vol probe because positioning/crowding mean-reverts faster than a volatility regime.
  * PASS (informational — funds a full Edge-Certificate run, never "trade it") iff ALL THREE:
      (a) >= 9/12 configs have POSITIVE net absolute return (after fees AND funding), AND
      (b) the MEDIAN config's ANNUALIZED net return >= +5%/yr (deploy hurdle, applied directly —
          the book is market-neutral so there is no beta to subtract), AND
      (c) the MEDIAN config's RECENT-HALF net return is also positive.
    Even on a PASS, the printed Sharpe/maxDD decide whether it is deploy-plausible or certificate-only.

Run:
  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
  .venv/Scripts/python probes/b16_funding_signal.py
"""
from __future__ import annotations

import statistics

import numpy as np
import pandas as pd

from coinmon.backtest.xsectional import load_universe_closes
from coinmon.data import db

TIMEFRAME = "1d"
EXCHANGE = "bybit"
FEE = 0.001
DAY_MS = 86_400_000


def _direct_usdt_legs(conn) -> list[str]:
    return sorted(
        sym for exch, sym, tf in db.list_series(conn)
        if exch == EXCHANGE and tf == TIMEFRAME and sym.endswith("/USDT")
    )


def load_daily_funding(conn, legs: list[str], index: pd.Index) -> pd.DataFrame:
    """Per-day summed funding rate for every leg's perp ("<LEG>:USDT"), aligned to the close
    frame. A daily bar with open_time T carries every 8h settlement in [T, T+1 day); missing = 0."""
    edges = list(index) + [int(index[-1]) + DAY_MS]
    out: dict[str, pd.Series] = {}
    for leg in legs:
        f = db.read_funding(conn, EXCHANGE, f"{leg}:USDT")
        if f.empty:
            out[leg] = pd.Series(0.0, index=index)
            continue
        bucket = pd.cut(f["funding_time"], bins=edges, right=False, labels=index)
        daily = f.groupby(bucket, observed=True)["rate"].sum()
        out[leg] = daily.reindex(index).fillna(0.0)
    return pd.DataFrame(out).reindex(columns=legs)


def _turnover(prev: dict[str, float], new: dict[str, float]) -> float:
    return sum(abs(new.get(s, 0.0) - prev.get(s, 0.0)) for s in prev.keys() | new.keys())


def _bar_pnl(ret_row: pd.Series, fund_row: pd.Series, w: dict[str, float]) -> float:
    """One bar's book P&L: price return on signed weights, minus funding on signed weights
    (long weight>0 pays, short weight<0 receives)."""
    total = 0.0
    for s, wt in w.items():
        r = ret_row.get(s)
        if r == r:
            total += wt * r
        fr = fund_row.get(s)
        if fr == fr:
            total -= wt * fr
    return total
GRID = [
    (L, q, rb)
    for L in (7, 14, 30)
    for q in (0.1, 0.2)
    for rb in (7, 14)
]


def run_config(closes: pd.DataFrame, funding: pd.DataFrame, L: int, q: float, rb: int):
    """Dollar-neutral long-low-funding / short-high-funding book, rebalanced every `rb` bars.
    Returns a metrics dict or None if history is too short."""
    ret = closes.pct_change()
    times = closes.index
    n = len(times)
    warmup = L + 1
    if n <= warmup + rb:
        return None
    rebalance_bars = list(range(warmup, n - 1, rb))
    seg_ends = rebalance_bars[1:] + [n - 1]

    eq = 1.0
    curve: list[float] = []
    ctimes: list[int] = []
    positions: list[float] = []
    prev_w: dict[str, float] = {}

    for start, end in zip(rebalance_bars, seg_ends, strict=True):
        window = funding.iloc[start - L + 1 : start + 1]
        score = window.mean()  # trailing mean daily funding, point-in-time
        price_now = closes.iloc[start]
        past_price = closes.iloc[start - L]
        # eligible = tradeable now, has L bars of price history, and has real funding history
        # (an all-zero trailing window means the coin's funding is unrecorded for this span, which
        # would masquerade as "low funding" and pollute the long leg — exclude it)
        has_fund = (window != 0).any()
        elig = score[price_now.notna() & past_price.notna() & has_fund]
        if len(elig) < 4:
            continue
        ranked = list(elig.sort_values(ascending=False).index)  # highest funding first
        k = max(1, round(len(ranked) * q))
        shorts = ranked[:k]  # crowded / high funding -> short
        short_set = set(shorts)
        longs = [s for s in reversed(ranked) if s not in short_set][:k]  # unloved / low funding
        if not longs:
            continue
        w = {s: 1.0 / len(longs) for s in longs}
        for s in shorts:
            w[s] = -1.0 / len(shorts)

        eq *= 1.0 - FEE * _turnover(prev_w, w)
        for d in range(start + 1, end + 1):
            eq *= 1.0 + _bar_pnl(ret.iloc[d], funding.iloc[d], w)
            curve.append(eq)
            ctimes.append(int(times[d]))

        entry, exit_ = closes.iloc[start], closes.iloc[end]
        seg_fund = funding.iloc[start + 1 : end + 1].sum()
        for s in longs + shorts:
            hp = exit_[s] / entry[s] - 1.0
            if hp != hp:
                continue
            sign = 1.0 if s not in short_set else -1.0
            cum_f = float(seg_fund.get(s, 0.0))
            net = sign * hp - sign * cum_f - 2.0 * FEE
            positions.append(net)
        prev_w = w

    if len(curve) < 8:
        return None
    s = pd.Series(curve, index=pd.to_datetime(pd.Index(ctimes), unit="ms"))
    r = s.pct_change().dropna()
    m = len(curve) // 2
    net_abs = curve[-1] - 1.0
    net_recent = curve[-1] / curve[m] - 1.0
    win = sum(p > 0 for p in positions) / len(positions) if positions else float("nan")
    sharpe = float(r.mean() / r.std() * np.sqrt(365)) if r.std() > 0 else float("nan")
    maxdd = float((s / s.cummax() - 1.0).min())
    return {
        "net_abs": net_abs, "net_recent": net_recent, "win": win,
        "sharpe": sharpe, "maxdd": maxdd, "curve": s,
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
    span = len(closes)
    years = span / 365.0
    print(f"B16 funding-crowding signal — {EXCHANGE} {closes.shape[1]} USDT perps, {TIMEFRAME}")
    print(f"close frame: {span} bars ({pd.to_datetime(closes.index[0], unit='ms').date()} -> "
          f"{pd.to_datetime(closes.index[-1], unit='ms').date()})")
    print("book: LONG lowest-funding slice / SHORT highest-funding slice, dollar-neutral, "
          "real funding applied\n")

    header = (f"{'L':>4}{'q':>6}{'reb':>5}{'net_abs':>11}{'net/yr':>9}"
              f"{'net_rec':>10}{'win%':>7}{'Sharpe':>8}{'maxDD':>8}")
    print(header)
    print("-" * len(header))
    n_pos = 0
    ann: list[float] = []
    recents: list[float] = []
    for L, q, rb in GRID:
        r = run_config(closes, funding, L, q, rb)
        if r is None:
            print(f"{L:>4}{q:>6.1f}{rb:>5}   (insufficient history)")
            continue
        n_pos += r["net_abs"] > 0
        ann.append(r["net_abs"] / years)
        recents.append(r["net_recent"])
        print(f"{L:>4}{q:>6.1f}{rb:>5}{r['net_abs']:>+10.1%}{r['net_abs'] / years:>+8.1%}"
              f"{r['net_recent']:>+9.1%}{r['win']:>6.1%}{r['sharpe']:>8.2f}{r['maxdd']:>7.0%}")

    ran = len(ann)
    med_ann = statistics.median(ann) if ann else float("nan")
    med_recent = statistics.median(recents) if recents else float("nan")
    btc = closes.get("BTC/USDT")
    btc_hold = float(btc.dropna().iloc[-1] / btc.dropna().iloc[0] - 1.0) if btc is not None else float("nan")
    print(f"\nBTC buy-and-hold over the span: {btc_hold:+.1%} ({btc_hold / years:+.1%}/yr) — the passive alternative")
    print(f"configs with positive net absolute return: {n_pos}/{ran}")
    print(f"median annualized net return: {med_ann:+.2%}/yr (deploy hurdle >= +5%/yr)")
    print(f"median recent-half net return: {med_recent:+.2%}")

    pass_a = n_pos >= 9
    pass_b = med_ann >= 0.05
    pass_c = med_recent > 0
    verdict = "PASS" if (pass_a and pass_b and pass_c) else "FAIL"
    print(f"\nB16 VERDICT: {verdict} — frozen rule: >= 9/12 net-positive [{'#OK' if pass_a else 'no'}] "
          f"AND median >= +5%/yr [{'#OK' if pass_b else 'no'}] "
          f"AND median recent-half > 0 [{'#OK' if pass_c else 'no'}]. "
          f"Even on PASS, Sharpe/maxDD above decide deploy-plausibility (B14 lesson).")


if __name__ == "__main__":
    main()
