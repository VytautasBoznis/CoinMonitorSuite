"""Plan-B P2 probe B18 — OPEN-INTEREST crowding (the FIRST test on genuinely new, non-candle data).

Pre-registered 2026-07-18, immediately after the Z0 OI backfill (probes/z0_backfill_oi.py) captured
5+ years of daily Bybit open-interest for the 41 USDT perps into the open_interest table. This is the
Plan-B P2 frontier the mission reserved for NEW INPUTS once the candle+funding well ran dry
([[plan-b-fallback-probes]], [[mission-find-edge-ship-ui]]) — every candle/funding-derived family
(price-shape, X-sectional & time-series momentum, carry, low-vol) is now exhausted/negative.

ECONOMIC HYPOTHESIS (documented positioning/crowding effect): coins whose OPEN INTEREST has surged the
most over a trailing window carry CROWDED leveraged positioning, which subsequently mean-reverts /
gets liquidated → they UNDERPERFORM coins whose OI grew least (de-crowding). The honest way to harvest
a cross-sectional positioning factor is a dollar-neutral perp book: LONG the least-crowded (bottom-q
OI growth), SHORT the most-crowded (top-q OI growth). Dollar-neutral ⇒ no crypto beta to subtract, so
net return is tested DIRECTLY against the +5%/yr deploy hurdle ([[live-yield-hurdle]]).

Reuses B14's exact honest neutral-book mechanics (real per-symbol Bybit funding: long pays / short
receives; taker fee 0.001/side on turnover) — only the RANKING SIGNAL changes (OI growth, not vol).
SURVIVORSHIP CAVEAT stands (41 survivors, no delistings) — same as B14; noted, not fixable here.

DIAGNOSTIC (informational, printed but NOT part of the pass rule): pooled next-bar information
coefficient — Spearman corr of OI-growth_t vs cross-sectional-demeaned return_{t+1} — the H7-style
"is there ANY predictive signal" check before trusting a portfolio construction ([[order-flow-probe-h7-refuted]]).

FROZEN RULE (pre-registered before any run — never adjusted after seeing results):
  * Universe: 41 Bybit USDT perps, 1d; OI aligned to the candle close frame (ffill <= 2 bars).
  * Signal: oi_growth = OI_now / OI_{L bars ago} - 1, point-in-time. LONG bottom-q (least growth)
    equal-weight (+1), SHORT top-q (most growth) equal-weight (-1); any name in both dropped from short.
  * Grid (M=12): L in {14,30,60} x q in {0.2,0.3} x rebalance in {14,30}. ALL recorded.
  * PASS (informational — a PASS funds a full Edge-Certificate run, never "trade it") iff ALL THREE:
      (a) >= 9/12 configs net-positive (after fees AND funding), AND
      (b) median config annualized net return >= +5%/yr, AND
      (c) median config recent-half net return > 0.
  A post-hoc SIGN FLIP (if the crowded leg outperforms) is a NEW hypothesis needing its own probe, not a pass.

Run:
  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
  PYTHONPATH="src;." .venv/Scripts/python probes/b18_oi_crowding.py
"""
from __future__ import annotations

import statistics

import pandas as pd

from coinmon.backtest.xsectional import load_universe_closes
from coinmon.data import db
from probes.b14_lowvol_neutral import (
    EXCHANGE, TIMEFRAME, FEE, _direct_usdt_legs, load_daily_funding, _turnover, _bar_pnl,
)

GRID = [(L, q, rb) for L in (14, 30, 60) for q in (0.2, 0.3) for rb in (14, 30)]


def load_oi(conn, legs: list[str], index: pd.Index) -> pd.DataFrame:
    """Per-leg OI aligned to the close-frame index (ffill <= 2 bars for the odd missing point)."""
    out: dict[str, pd.Series] = {}
    for leg in legs:
        df = db.read_open_interest(conn, EXCHANGE, f"{leg}:USDT", TIMEFRAME)
        if df.empty:
            out[leg] = pd.Series(float("nan"), index=index)
            continue
        s = pd.Series(df["oi_amount"].values, index=df["ts"].values)
        s = s[~s.index.duplicated(keep="last")]
        out[leg] = s.reindex(index).ffill(limit=2)
    return pd.DataFrame(out).reindex(columns=legs)


def diagnostic_ic(closes: pd.DataFrame, oi: pd.DataFrame, L: int) -> tuple[float, int]:
    """Pooled Spearman IC: OI-growth_t vs cross-sectionally-demeaned next-bar return."""
    ret = closes.pct_change()
    oi_growth = oi / oi.shift(L) - 1.0
    fwd = ret.shift(-1)  # next-bar return
    fwd_demean = fwd.sub(fwd.mean(axis=1), axis=0)  # remove market move -> relative
    sig, ret_rel = [], []
    for t in range(L + 1, len(closes) - 1):
        g = oi_growth.iloc[t]
        r = fwd_demean.iloc[t]
        mask = g.notna() & r.notna()
        if mask.sum() >= 5:
            sig.extend(g[mask].tolist())
            ret_rel.extend(r[mask].tolist())
    if len(sig) < 30:
        return float("nan"), len(sig)
    # Spearman = Pearson on ranks (avoids the scipy dependency pandas' method="spearman" needs)
    ic = pd.Series(sig).rank().corr(pd.Series(ret_rel).rank())
    return float(ic), len(sig)


def run_config(closes: pd.DataFrame, oi: pd.DataFrame, funding: pd.DataFrame,
               L: int, q: float, rb: int, fee: float = FEE):
    ret = closes.pct_change()
    oi_growth = oi / oi.shift(L) - 1.0
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
    prev_w: dict[str, float] = {}
    for start, end in zip(rebalance_bars, seg_ends, strict=True):
        sig = oi_growth.iloc[start]
        price_now = closes.iloc[start]
        elig = sig[sig.notna() & price_now.notna()]
        if len(elig) < 6:
            continue
        ranked = list(elig.sort_values(ascending=True).index)  # least OI growth first
        k = max(1, round(len(ranked) * q))
        longs = ranked[:k]  # de-crowded
        long_set = set(longs)
        shorts = [s for s in reversed(ranked) if s not in long_set][:k]  # crowded
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
        seg_fund = funding.iloc[start + 1 : end + 1].sum()
        for s in longs + shorts:
            hp = exit_[s] / entry[s] - 1.0
            if hp != hp:
                continue
            sign = 1.0 if s in long_set else -1.0
            net = sign * hp + (-sign * float(seg_fund.get(s, 0.0))) - 2.0 * fee
            positions.append(net)
        prev_w = w

    if len(curve) < 4:
        return None
    m = len(curve) // 2
    net_abs = curve[-1] - 1.0
    net_recent = curve[-1] / curve[m] - 1.0
    win = sum(p > 0 for p in positions) / len(positions) if positions else float("nan")
    return net_abs, net_recent, len(positions), win


def main() -> None:
    conn = db.connect()
    legs = _direct_usdt_legs(conn)

    def read(sym: str) -> pd.DataFrame:
        return db.read_candles(conn, EXCHANGE, sym, TIMEFRAME)

    closes = load_universe_closes(read, legs)
    have = [c for c in legs if c in closes.columns]
    funding = load_daily_funding(conn, have, closes.index)
    oi = load_oi(conn, have, closes.index)
    conn.close()

    years = len(closes) / 365.0
    cov = oi.notna().mean().mean()
    print(f"B18 OI-crowding neutral book — {EXCHANGE} {len(have)} USDT perps, {TIMEFRAME}, "
          f"{pd.to_datetime(closes.index[0], unit='ms').date()} -> "
          f"{pd.to_datetime(closes.index[-1], unit='ms').date()}")
    print(f"OI coverage over the close frame: {cov:.1%}\n")

    print("diagnostic — pooled next-bar IC of OI-growth vs relative return (informational):")
    for L in (14, 30, 60):
        ic, npair = diagnostic_ic(closes, oi, L)
        print(f"  L={L:>3}: IC={ic:+.4f}  (N={npair})")
    print("  (|IC| < ~0.03 => no usable cross-sectional signal, as H7 flow found for CVD)\n")

    hdr = f"{'L':>4}{'q':>6}{'reb':>5}{'net_abs':>11}{'net/yr':>9}{'net_rec':>10}{'win%':>7}"
    print(hdr)
    print("-" * len(hdr))
    n_pos = 0
    ann: list[float] = []
    recents: list[float] = []
    for L, q, rb in GRID:
        r = run_config(closes, oi, funding, L, q, rb)
        if r is None:
            print(f"{L:>4}{q:>6.1f}{rb:>5}   (insufficient history)")
            continue
        net_abs, net_recent, npos, win = r
        n_pos += net_abs > 0
        ann.append(net_abs / years)
        recents.append(net_recent)
        print(f"{L:>4}{q:>6.1f}{rb:>5}{net_abs:>+10.1%}{net_abs / years:>+8.1%}"
              f"{net_recent:>+9.1%}{win:>6.1%}")

    ran = len(ann)
    med_ann = statistics.median(ann) if ann else float("nan")
    med_recent = statistics.median(recents) if recents else float("nan")
    print(f"\nconfigs net-positive: {n_pos}/{ran}")
    print(f"median annualized net: {med_ann:+.2%}/yr (deploy hurdle >= +5%/yr)")
    print(f"median recent-half net: {med_recent:+.2%}")

    pass_a = n_pos >= 9
    pass_b = med_ann >= 0.05
    pass_c = med_recent > 0
    ok = lambda b: "#OK" if b else "no"
    verdict = "PASS" if (pass_a and pass_b and pass_c) else "FAIL"
    print(f"\nB18 VERDICT: {verdict} — >= 9/12 net-positive [{ok(pass_a)}] AND median >= +5%/yr "
          f"[{ok(pass_b)}] AND median recent-half > 0 [{ok(pass_c)}] "
          f"(informational; a PASS funds a full Edge-Certificate run; a sign-flip is a NEW probe).")


if __name__ == "__main__":
    main()
