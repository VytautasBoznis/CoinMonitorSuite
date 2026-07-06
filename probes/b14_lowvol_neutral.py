"""Fresh-ideation probe B14 — MARKET-NEUTRAL low-vol / high-vol with an honest short-cost model
(pre-registered 2026-07-06, the direct follow-up to B13's passing long-only probe).

B13 showed the cross-sectional LOW-VOLATILITY anomaly is real on the liquid Bybit USDT universe
(12/12 positive edge vs the equal-weight universe, present in the recent regime) — but the long-only
low-vol book UNDERPERFORMS just holding BTC (+5.6 vs +15.6%/yr), so the anomaly's alpha is in the
RELATIVE ordering, not the long book. The way to actually harvest relative alpha is a dollar-neutral
book: LONG the low-vol slice, SHORT the high-vol slice ([[b13-low-vol-fresh-lead]]).

Because the book is dollar-neutral, there is NO crypto-beta to subtract — the absolute net return IS
the alpha, so it is tested DIRECTLY against the >= +5%/yr forward deploy hurdle ([[live-yield-hurdle]]),
not against an equal-weight benchmark. This is the honest bar the long-only probe could dodge.

THE HONEST SHORT-COST MODEL (this is the whole point of B14 — a paper low-vol edge usually dies on
short costs):
  * Both legs are PERPETUAL swaps on one margin account (the executable dollar-neutral book).
  * Real per-symbol Bybit funding (8h settlements — the same data that CERTIFIED the carry strategy,
    [[w3-carry-first-live-diagnosis]]) is applied per bar with the correct sign:
      LONG position pays funding  (P&L contribution = -weight * rate)
      SHORT position receives it  (weight is negative, so -weight*rate is positive when rate > 0)
    High-vol alts usually carry higher positive funding, so shorting them tends to EARN funding — but
    the low-vol longs also pay funding, and the data decides whether the net is a tail-wind or a drag.
  * Taker fee 0.001 per side on turnover, round-trip charged into every position's ledger entry.
  * A fragility sweep (fee x2 + a funding HAIRCUT that always hurts the book) reports whether the edge
    survives worse-than-modelled costs, exactly as the carry certificate's C6 does.

FROZEN RULE (pre-registered before any run — never adjust after seeing results):
  * Universe: Bybit 41 USDT direct legs, 1d bars; each leg's perp funding = "<LEG>:USDT".
  * Score: trailing realized vol = std of daily pct-change over the L-bar formation window,
    point-in-time (closes up to the rebalance bar only). LONG the bottom-`q` (lowest vol) slice
    equal-weight (weights sum +1); SHORT the top-`q` (highest vol) slice equal-weight (weights sum
    -1), any name in both slices dropped from the short. Hold until the next rebalance.
  * Grid (fixed = the M the deflation must survive): L in {30,60,90} x q in {0.1,0.2} x
    rebalance in {14,30} = 12 configs. ALL recorded ([[portfolio-search-protocol]]).
  * PASS (informational — funds a full Edge-Certificate run, never "trade it") iff ALL THREE:
      (a) >= 9/12 configs have POSITIVE net absolute return (after fees AND funding), AND
      (b) the MEDIAN config's ANNUALIZED net return >= +5%/yr (the deploy hurdle, applied directly
          because the book is market-neutral), AND
      (c) the MEDIAN config's RECENT-HALF net return is also positive (the effect must live in the
          recent regime, not be a stale full-sample artifact).

Run:
  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
  .venv/Scripts/python probes/b14_lowvol_neutral.py
"""
from __future__ import annotations

import statistics

import pandas as pd

from coinmon.backtest.xsectional import load_universe_closes
from coinmon.data import db

TIMEFRAME = "1d"
EXCHANGE = "bybit"
FEE = 0.001
DAY_MS = 86_400_000
GRID = [
    (L, q, rb)
    for L in (30, 60, 90)
    for q in (0.1, 0.2)
    for rb in (14, 30)
]


def _direct_usdt_legs(conn) -> list[str]:
    return sorted(
        sym for exch, sym, tf in db.list_series(conn)
        if exch == EXCHANGE and tf == TIMEFRAME and sym.endswith("/USDT")
    )


def load_daily_funding(conn, legs: list[str], index: pd.Index) -> pd.DataFrame:
    """Per-day summed funding rate for every leg's perp, aligned to the close-frame index.

    A daily bar with open_time T carries every 8h funding settlement whose funding_time falls in
    [T, T + 1 day). Missing legs/bars are 0.0 (no settlement = no cashflow), so a long simply pays,
    and a short receives, the summed rate for that day."""
    edges = list(index) + [int(index[-1]) + DAY_MS]
    out: dict[str, pd.Series] = {}
    for leg in legs:
        f = db.read_funding(conn, EXCHANGE, f"{leg}:USDT")
        if f.empty:
            out[leg] = pd.Series(0.0, index=index)
            continue
        # bucket each settlement into its daily bar, then sum rates per bar
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
        if r == r:  # not NaN
            total += wt * r
        fr = fund_row.get(s)
        if fr == fr:
            total -= wt * fr
    return total


def run_config(closes: pd.DataFrame, funding: pd.DataFrame, L: int, q: float, rb: int,
               fee: float = FEE, funding_haircut: float = 0.0):
    """Dollar-neutral long-low-vol / short-high-vol book, rebalanced every `rb` bars.

    `funding_haircut` is a fragility knob: it always hurts the book (subtracts a fraction of the
    per-position funding cashflow's favourable part) so the sweep tests worse-than-modelled carry.
    Returns (net_abs, net_recent, n_positions, win_rate, short_fund_mean) or None if too short."""
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
    positions: list[float] = []
    short_funds: list[float] = []
    prev_w: dict[str, float] = {}

    for start, end in zip(rebalance_bars, seg_ends, strict=True):
        window = ret.iloc[start - L + 1 : start + 1]
        vol = window.std()
        price_now = closes.iloc[start]
        elig = vol[vol.notna() & price_now.notna() & (vol > 0)]
        if len(elig) < 4:
            continue
        ranked = list(elig.sort_values(ascending=True).index)  # lowest vol first
        k = max(1, round(len(ranked) * q))
        longs = ranked[:k]
        long_set = set(longs)
        shorts = [s for s in reversed(ranked) if s not in long_set][:k]
        if not shorts:
            continue
        w = {s: 1.0 / len(longs) for s in longs}
        for s in shorts:
            w[s] = -1.0 / len(shorts)

        eq *= 1.0 - fee * _turnover(prev_w, w)
        for d in range(start + 1, end + 1):
            eq *= 1.0 + _bar_pnl(ret.iloc[d], funding.iloc[d], w)
            curve.append(eq)

        entry, exit_ = closes.iloc[start], closes.iloc[end]
        seg_fund = funding.iloc[start + 1 : end + 1].sum()  # cumulative funding per symbol over hold
        for s in longs + shorts:
            hp = exit_[s] / entry[s] - 1.0
            if hp != hp:
                continue
            sign = 1.0 if s in long_set else -1.0
            cum_f = float(seg_fund.get(s, 0.0))
            fund_pnl = -sign * cum_f
            # haircut always removes a slice of any FAVOURABLE funding, never adds
            fund_pnl -= funding_haircut * abs(cum_f)
            net = sign * hp + fund_pnl - 2.0 * fee
            positions.append(net)
            if sign < 0:
                short_funds.append(-cum_f)  # what the short actually received (rate>0 => positive)
        prev_w = w

    if len(curve) < 4:
        return None
    m = len(curve) // 2
    net_abs = curve[-1] - 1.0
    net_recent = curve[-1] / curve[m] - 1.0
    win = sum(p > 0 for p in positions) / len(positions) if positions else float("nan")
    sf = statistics.mean(short_funds) if short_funds else float("nan")
    return net_abs, net_recent, len(positions), win, sf


def main() -> None:
    conn = db.connect()
    legs = _direct_usdt_legs(conn)
    print(f"B14 market-neutral low/high-vol — {EXCHANGE} {len(legs)} USDT perps, {TIMEFRAME}")

    def read(sym: str) -> pd.DataFrame:
        return db.read_candles(conn, EXCHANGE, sym, TIMEFRAME)

    closes = load_universe_closes(read, legs)
    have = [c for c in legs if c in closes.columns]
    funding = load_daily_funding(conn, have, closes.index)
    conn.close()
    span = len(closes)
    years = span / 365.0
    print(f"close frame: {span} bars x {closes.shape[1]} coins "
          f"({pd.to_datetime(closes.index[0], unit='ms').date()} -> "
          f"{pd.to_datetime(closes.index[-1], unit='ms').date()})")
    print(f"funding: real Bybit 8h settlements, summed to daily, applied per bar "
          f"(long pays / short receives)\n")

    header = (f"{'L':>4}{'q':>6}{'reb':>5}{'net_abs':>11}{'net/yr':>9}"
              f"{'net_rec':>10}{'win%':>7}{'sh_fund':>9}")
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
        net_abs, net_recent, npos, win, sf = r
        n_pos += net_abs > 0
        ann.append(net_abs / years)
        recents.append(net_recent)
        print(f"{L:>4}{q:>6.1f}{rb:>5}{net_abs:>+10.1%}{net_abs / years:>+8.1%}"
              f"{net_recent:>+9.1%}{win:>6.1%}{sf:>+8.2%}")

    ran = len(ann)
    med_ann = statistics.median(ann) if ann else float("nan")
    med_recent = statistics.median(recents) if recents else float("nan")
    btc = closes.get("BTC/USDT")
    btc_hold = float(btc.dropna().iloc[-1] / btc.dropna().iloc[0] - 1.0) if btc is not None else float("nan")
    print(f"\nBTC buy-and-hold over the span: {btc_hold:+.1%} ({btc_hold / years:+.1%}/yr) — the passive alternative")
    print(f"configs with positive net absolute return: {n_pos}/{ran}")
    print(f"median annualized net return: {med_ann:+.2%}/yr (deploy hurdle >= +5%/yr)")
    print(f"median recent-half net return: {med_recent:+.2%}")

    # Fragility: does the median config survive fee x2 + a 25% funding haircut?
    print("\nfragility (median config, fee x2 + 25% funding haircut):")
    Lm, qm, rbm = GRID[len(GRID) // 2]
    base = run_config(closes, funding, Lm, qm, rbm)
    frag = run_config(closes, funding, Lm, qm, rbm, fee=2 * FEE, funding_haircut=0.25)
    if base and frag:
        print(f"  L={Lm} q={qm} reb={rbm}: base {base[0] / years:+.2%}/yr -> stressed {frag[0] / years:+.2%}/yr")

    pass_a = n_pos >= 9
    pass_b = med_ann >= 0.05
    pass_c = med_recent > 0
    verdict = "PASS" if (pass_a and pass_b and pass_c) else "FAIL"
    print(f"\nB14 VERDICT: {verdict} — frozen rule: >= 9/12 net-positive [{ '#OK' if pass_a else 'no'}] "
          f"AND median >= +5%/yr [{'#OK' if pass_b else 'no'}] "
          f"AND median recent-half > 0 [{'#OK' if pass_c else 'no'}] "
          f"(informational; a PASS funds a full Edge-Certificate run).")


if __name__ == "__main__":
    main()
