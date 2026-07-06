"""Fresh-ideation probe B13 — the cross-sectional LOW-VOLATILITY anomaly (pre-registered 2026-07-06).

Hypothesis (documented, 2024-2026 crypto asset-pricing literature): coins with LOWER trailing
realized volatility earn HIGHER future returns than high-vol coins — the low-volatility anomaly,
reported as EMERGING and STRENGTHENING as crypto markets mature (i.e. present in the recent
regime, which is exactly what the deploy hurdle [[live-yield-hurdle]] cares about). This is a
DIFFERENT input from W5 cross-sectional momentum (rank by return, REFUTED): we rank by risk, and
the long leg is the STABLE coins, so it churns less than momentum's fee-heavy short leg.

Why it might be retail-reachable: the effect is attributed to retail lottery-preference (chasing
high-vol names bids them up → they underperform). It needs only daily candles we already have.
Honest caveat (from the same literature): crypto anomalies concentrate in micro-caps; we restrict
to the LIQUID Bybit USDT direct legs, where the effect is weaker but actually tradable — so this is
a conservative test, and a FAIL here does not rule out the effect on an illiquid universe we won't
trade anyway.

FROZEN RULE (pre-registered before any run — never adjust after seeing results):
  * Universe: Bybit USDT DIRECT legs (the coins, not synthetic ratios), 1d bars.
  * Score: trailing realized vol = std of daily pct-change over the L-bar formation window,
    point-in-time (closes up to the rebalance bar only). Rank ASCENDING; long the bottom `q`
    fraction equal-weight; hold until the next rebalance. Long-only (no short leg).
  * Benchmark: equal-weight the WHOLE eligible universe on the same cadence + same fee.
  * Fee: 0.001 taker per side on turnover (honest round-trip).
  * Grid (fixed, = the M the deflation must survive): L in {30,60,90} x q in {0.2,0.3} x
    rebalance in {14,30} = 12 configs. ALL recorded ([[portfolio-search-protocol]]).
  * PASS (informational — funds a full Edge-Certificate run, never "trade it") iff BOTH:
      (a) >= 9/12 configs have POSITIVE full-sample net edge vs the EW benchmark (cross-config
          consistency is the multiple-testing guard, as in B4), AND
      (b) the MEDIAN config's RECENT-HALF net edge is also positive (the effect must live in the
          recent regime, not be a stale full-sample artifact).
    Report the annualized edge so it can be checked against the >= 5%/yr deploy hurdle.

Run:
  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
  .venv/Scripts/python probes/b13_low_vol_xsection.py
"""
from __future__ import annotations

import statistics

import pandas as pd

from coinmon.backtest.xsectional import load_universe_closes
from coinmon.data import db

TIMEFRAME = "1d"
EXCHANGE = "bybit"
FEE = 0.001
GRID = [
    (L, q, rb)
    for L in (30, 60, 90)
    for q in (0.2, 0.3)
    for rb in (14, 30)
]


def _direct_usdt_legs(conn) -> list[str]:
    """The liquid Bybit USDT direct legs at this timeframe — the coins themselves, not ratios."""
    return sorted(
        sym for exch, sym, tf in db.list_series(conn)
        if exch == EXCHANGE and tf == TIMEFRAME and sym.endswith("/USDT")
    )


def _turnover(prev: dict[str, float], new: dict[str, float]) -> float:
    return sum(abs(new.get(s, 0.0) - prev.get(s, 0.0)) for s in prev.keys() | new.keys())


def _port_return(ret_row: pd.Series, weights: dict[str, float]) -> float:
    return sum(w * r for s, w in weights.items() if (r := ret_row.get(s)) == r)


def run_config(closes: pd.DataFrame, L: int, q: float, rb: int):
    """Long the bottom-`q` trailing-vol slice, rebalanced every `rb` bars, vs EW-universe benchmark.
    Returns (edge_full, edge_recent, n_positions, win_rate) or None if history is too short."""
    ret = closes.pct_change()
    times = closes.index
    n = len(times)
    warmup = L + 1
    if n <= warmup + rb:
        return None
    rebalance_bars = list(range(warmup, n - 1, rb))
    seg_ends = rebalance_bars[1:] + [n - 1]

    strat_eq = bench_eq = 1.0
    strat_curve, bench_curve = [], []
    positions: list[float] = []
    prev_w: dict[str, float] = {}
    prev_bw: dict[str, float] = {}

    for start, end in zip(rebalance_bars, seg_ends, strict=True):
        # Point-in-time trailing vol over the L bars ending at the rebalance bar.
        window = ret.iloc[start - L + 1 : start + 1]
        vol = window.std()
        price_now = closes.iloc[start]
        eligible = vol[vol.notna() & price_now.notna() & (vol > 0)]
        if len(eligible) < 3:
            continue
        ranked = list(eligible.sort_values(ascending=True).index)  # lowest vol first
        k = max(1, round(len(ranked) * q))
        longs = ranked[:k]
        w = {s: 1.0 / len(longs) for s in longs}
        bw = {s: 1.0 / len(ranked) for s in ranked}

        strat_eq *= 1.0 - FEE * _turnover(prev_w, w)
        bench_eq *= 1.0 - FEE * _turnover(prev_bw, bw)
        for d in range(start + 1, end + 1):
            row = ret.iloc[d]
            strat_eq *= 1.0 + _port_return(row, w)
            bench_eq *= 1.0 + _port_return(row, bw)
            strat_curve.append(strat_eq)
            bench_curve.append(bench_eq)

        entry, exit_ = closes.iloc[start], closes.iloc[end]
        for s in longs:
            hp = exit_[s] / entry[s] - 1.0
            if hp == hp:
                positions.append(hp - 2.0 * FEE)
        prev_w, prev_bw = w, bw

    if len(strat_curve) < 4:
        return None
    m = len(strat_curve) // 2
    strat_abs = strat_curve[-1] - 1.0            # absolute total return of the low-vol book
    bench_abs = bench_curve[-1] - 1.0            # absolute total return of the EW-universe benchmark
    edge_full = strat_abs - bench_abs
    edge_recent = (strat_curve[-1] / strat_curve[m] - 1.0) - (bench_curve[-1] / bench_curve[m] - 1.0)
    win_rate = sum(p > 0 for p in positions) / len(positions) if positions else float("nan")
    return edge_full, edge_recent, len(positions), win_rate, strat_abs, bench_abs


def main() -> None:
    conn = db.connect()
    legs = _direct_usdt_legs(conn)
    print(f"B13 low-vol cross-section — {EXCHANGE} USDT direct legs, {TIMEFRAME}, {len(legs)} coins")

    def read(sym: str) -> pd.DataFrame:
        return db.read_candles(conn, EXCHANGE, sym, TIMEFRAME)

    closes = load_universe_closes(read, legs)
    conn.close()
    span = len(closes)
    print(f"close frame: {span} bars x {closes.shape[1]} coins "
          f"({pd.to_datetime(closes.index[0], unit='ms').date()} -> "
          f"{pd.to_datetime(closes.index[-1], unit='ms').date()})\n")

    # Absolute reference the deploy hurdle actually cares about: just holding BTC over the same span.
    btc = closes.get("BTC/USDT")
    btc_hold = float(btc.dropna().iloc[-1] / btc.dropna().iloc[0] - 1.0) if btc is not None else float("nan")

    header = (f"{'L':>4}{'q':>6}{'reb':>5}{'strat_abs':>12}{'bench_abs':>12}"
              f"{'edge_full':>12}{'edge_rec':>11}{'win%':>7}")
    print(header)
    print("-" * len(header))
    full_pos = 0
    recents: list[float] = []
    ann_full: list[float] = []
    strat_abs_list: list[float] = []
    years = span / 365.0
    for L, q, rb in GRID:
        r = run_config(closes, L, q, rb)
        if r is None:
            print(f"{L:>4}{q:>6.1f}{rb:>5}   (insufficient history)")
            continue
        edge_full, edge_recent, npos, win, strat_abs, bench_abs = r
        full_pos += edge_full > 0
        recents.append(edge_recent)
        strat_abs_list.append(strat_abs)
        # crude annualization of the full-sample edge for the deploy-hurdle readout
        ann_full.append(edge_full / years)
        print(f"{L:>4}{q:>6.1f}{rb:>5}{strat_abs:>+11.1%}{bench_abs:>+11.1%}"
              f"{edge_full:>+11.1%}{edge_recent:>+10.1%}{win:>6.1%}")

    median_recent = statistics.median(recents) if recents else float("nan")
    ran = len(recents)
    print(f"\nBTC buy-and-hold over the same span: {btc_hold:+.1%} "
          f"({btc_hold / years:+.1%}/yr) — the real deploy alternative")
    print(f"median ABSOLUTE low-vol book return: {statistics.median(strat_abs_list):+.1%} "
          f"({statistics.median(strat_abs_list) / years:+.1%}/yr)")
    print(f"configs with positive full-sample edge vs EW-universe: {full_pos}/{ran}")
    print(f"median recent-half edge: {median_recent:+.2%}")
    if ann_full:
        print(f"median annualized full-sample edge (vs EW-universe): "
              f"{statistics.median(ann_full):+.2%}/yr (deploy hurdle is >= +5%/yr)")
    verdict = "PASS" if (full_pos >= 9 and median_recent > 0) else "FAIL"
    print(f"\nB13 VERDICT: {verdict} — frozen rule: >= 9/12 positive full-sample edge "
          f"AND median recent-half edge > 0 (informational; a PASS funds a full certificate).")


if __name__ == "__main__":
    main()
