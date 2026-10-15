"""F11 - POST-LISTING DRIFT SHORT (day 8 -> day 98). Pre-registered BEFORE any price is pulled.
EVENTS  F6 caches (data/f6_listing_events_{binance,bybit}.parquet); t1 = first funding settlement.
TRADE   short perp at t1+7d, cover at t1+97d or delisting. 1x isolated: loss capped at -100%.
HEDGE   long equal-weight basket of the 41-perp universe, same notional (alt beta, not BTC: B13 lesson).
NET     -(perp return) + basket return - net funding on both legs - 0.11% taker RT.
PASS    all, on BOTH venues: N >= 150; mean net >= +5%/event; median > 0; 95% CI ex-zero
        (bootstrap clustered by listing month); recent-24mo mean > 0; top-5 events < 50% of PnL.
KILL    any miss. Unhedged result reported separately, never blended.
CAVEAT  survivor universe (delisted perps missing, sign unknown). Week 1 is excluded because F6
        showed Bybit week-1 naked long at mean +3.70%, i.e. against the short.

Spec by Fable; thresholds FROZEN as written by the owner 2026-10-15. Owner constraint: no
Hyperliquid data (its API budget belongs to the live bot; Hyperliquid is kept for a final recheck).

CONSTRUCTION, declared 2026-10-15 before any day-8..98 price was pulled (where the spec is silent):
  PRICES   1h perp klines from the listing's own venue. Entry = open of the 1h bar at t1+7d (the
           first bar within 24h if that one is missing, else the event drops). Exit = open of the
           bar at t1+97d.
  1x ISO   isolated margin also pays the funding, so equity = 2 - p/E + F (F = funding received so
           far) and the short is liquidated when a 1h high reaches p = E x (2 + F)/(1 + 0.5%
           maintenance margin), ~1.99x at F=0. The short leg, funding included, then books exactly
           -100% and both legs close at the end of that bar.
           CORRECTED 2026-10-15 after the first run printed worst events of -183%: v1 booked -100%
           on price, charged funding on top (breaking the spec's -100% cap) and ignored funding in
           the liquidation price. The fix can only help the short.
  NO-LIQ   sensitivity row: never liquidated, short leg floored at -100% at exit. Liquidation on
           last-trade highs (above) is harsher than the venues' mark price; this row bounds ANY
           liquidation treatment from the short's side. Not a reachable 1x position.
  CLOSE-LIQ  sensitivity row, added after NO-LIQ passed: liquidated only when a 1h CLOSE crosses,
           a generous proxy for mark price (which smooths wicks).
  DELIST   klines ending before t1+97d: cover at the last bar's close (labelled 'delist' when the
           last bar is more than a day short of t1+97d).
  BASKET   the 41 Bybit USDT perps of the DB universe MINUS the 4 that carry no alt beta (USDC,
           RLUSD, USD1 stablecoins; XAUT gold) and minus the event's own coin; equal-weight
           buy-and-hold from entry, over the legs that already traded at entry. 1h Bybit perp
           klines, pulled from the API (the DB's candles stop 2026-07-02). The literal 41-leg
           basket is printed as a sensitivity row, with its own verdict.
  FUNDING  every settlement in (entry, exit], on entry notional (no drift): the short receives
           +rate, the basket pays its legs' mean rate.
  FEES     0.11% taker round trip charged on EACH leg (0.22%/event hedged, 0.11% unhedged).
  RECENT   events whose t1 falls in the 730 days before the venue's last eligible t1.
  WINDOW   events whose t1+97d is complete by CUTOFF.

Run:
  PYTHONPATH="src;." .venv/Scripts/python probes/f11_post_listing_drift_short.py
"""
from __future__ import annotations

import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from probes.f6_new_listing_funding import _bybit, _get

DATA = Path("data")
H, D = 3_600_000, 86_400_000
ENTRY, EXIT = 7 * D, 97 * D
CUTOFF = int(pd.Timestamp("2026-10-15", tz="UTC").timestamp() * 1000)
BASKET_FROM = int(pd.Timestamp("2021-01-01", tz="UTC").timestamp() * 1000)
MMR = 0.005  # maintenance margin
FEE_RT = 0.0011  # taker round trip, per leg

# The DB's 41-perp universe (bybit 1d */USDT legs, as of 2026-10-15).
BASKET = [
    "AAVEUSDT", "ADAUSDT", "AXSUSDT", "BATUSDT", "BCHUSDT", "BNBUSDT", "BTCUSDT", "CELOUSDT",
    "CHZUSDT", "COMPUSDT", "DOGEUSDT", "DOTUSDT", "DYDXUSDT", "ENAUSDT", "ETCUSDT", "ETHUSDT",
    "FILUSDT", "GRTUSDT", "ICPUSDT", "KSMUSDT", "LINKUSDT", "LTCUSDT", "MANAUSDT", "NEARUSDT",
    "NOMUSDT", "QNTUSDT", "RLUSDUSDT", "SOLUSDT", "SUIUSDT", "SUSHIUSDT", "TRXUSDT", "UNIUSDT",
    "USD1USDT", "USDCUSDT", "WLDUSDT", "XAUTUSDT", "XLMUSDT", "XRPUSDT", "XTZUSDT", "YFIUSDT",
    "ZRXUSDT",
]
NO_BETA = {"USDCUSDT", "RLUSDUSDT", "USD1USDT", "XAUTUSDT"}

PASS_N, PASS_MEAN, TOP5_MAX = 150, 0.05, 0.50
BOOT, SEED = 10_000, 20261015


# ---------------------------------------------------------------- fetch (Binance / Bybit only)
def _binance_bars(symbol: str, start: int, end: int) -> list[list] | None:
    """1h [t, open, high, close] in [start, end). None = Binance answered 400 (unserved)."""
    out = []
    while start < end:
        try:
            k = _get("https://fapi.binance.com/fapi/v1/klines",
                     {"symbol": symbol, "interval": "1h", "startTime": start, "endTime": end - 1,
                      "limit": 1000})
        except urllib.error.HTTPError as exc:
            if exc.code != 400:
                raise
            return None
        if not k:
            break
        out += [[int(b[0]), float(b[1]), float(b[2]), float(b[4])] for b in k]
        start = int(k[-1][0]) + H
    return out


def _binance_funding(symbol: str, start: int, end: int) -> list[tuple[int, float]]:
    out = []
    while True:
        fr = _get("https://fapi.binance.com/fapi/v1/fundingRate",
                  {"symbol": symbol, "startTime": start, "endTime": end, "limit": 1000})
        time.sleep(0.6)  # fundingRate shares a 500 / 5 min / IP budget
        out += [(int(x["fundingTime"]), float(x["fundingRate"])) for x in fr]
        if len(fr) < 1000:
            return out
        start = int(fr[-1]["fundingTime"]) + 1


def _bybit_bars(symbol: str, start: int, end: int) -> list[list]:
    out = []
    for s in range(start, end, 1000 * H):
        k = _bybit("https://api.bybit.com/v5/market/kline",
                   {"category": "linear", "symbol": symbol, "interval": "60",
                    "start": s, "end": min(s + 1000 * H, end) - 1, "limit": 1000})["list"]
        out += [[int(b[0]), float(b[1]), float(b[2]), float(b[4])] for b in k]
    return sorted(out)


def _bybit_funding(symbol: str, start: int, end: int) -> list[tuple[int, float]]:
    """Bybit returns <= 200 settlements, NEWEST first: page backwards."""
    out = []
    while True:
        fr = _bybit("https://api.bybit.com/v5/market/funding/history",
                    {"category": "linear", "symbol": symbol, "startTime": start, "endTime": end,
                     "limit": 200})["list"]
        out += [(int(x["fundingRateTimestamp"]), float(x["fundingRate"])) for x in fr]
        if len(fr) < 200:
            return out
        end = min(int(x["fundingRateTimestamp"]) for x in fr) - 1


def _frames(symbols: list[str], bars: list, funding: list) -> tuple[pd.DataFrame, pd.DataFrame]:
    b = pd.DataFrame([[s, *x] for s, bs in zip(symbols, bars, strict=True) if bs for x in bs],
                     columns=["symbol", "t", "o", "h", "c"])
    f = pd.DataFrame([[s, t // H * H, r]
                      for s, fs in zip(symbols, funding, strict=True) for t, r in fs],
                     columns=["symbol", "t", "rate"])  # settlements land a few ms after the hour
    return b, f


def _events(venue: str) -> pd.DataFrame:
    ev = pd.read_parquet(DATA / f"f6_listing_events_{venue}.parquet")
    assert ev["symbol"].is_unique
    return ev[ev["t1"] + EXIT + H <= CUTOFF].reset_index(drop=True)


def _pull_venue(venue: str) -> None:
    ev = _events(venue)
    spans = [(s, t1 + ENTRY, t1 + EXIT + H)
             for s, t1 in zip(ev["symbol"], ev["t1"], strict=True)]
    print(f"  {venue}: pulling {len(spans)} events")
    if venue == "binance":
        with ThreadPoolExecutor(max_workers=2) as pool:
            bars = list(pool.map(lambda x: _binance_bars(*x), spans))
        funding = [_binance_funding(*x) if b is not None else []
                   for x, b in zip(spans, bars, strict=True)]
    else:
        with ThreadPoolExecutor(max_workers=4) as pool:
            bars = list(pool.map(lambda x: _bybit_bars(*x), spans))
            funding = list(pool.map(lambda x: _bybit_funding(*x), spans))
    b, f = _frames([s for s, _, _ in spans], bars, funding)
    b.to_parquet(DATA / f"f11_bars_{venue}.parquet")
    f.to_parquet(DATA / f"f11_funding_{venue}.parquet")


def _pull_basket() -> None:
    spans = [(s, BASKET_FROM, CUTOFF) for s in BASKET]
    with ThreadPoolExecutor(max_workers=4) as pool:
        bars = list(pool.map(lambda x: _bybit_bars(*x), spans))
        funding = list(pool.map(lambda x: _bybit_funding(*x), spans))
    b, f = _frames(BASKET, bars, funding)
    b.to_parquet(DATA / "f11_bars_basket.parquet")
    f.to_parquet(DATA / "f11_funding_basket.parquet")


# ---------------------------------------------------------------- legs
class Basket:
    """Equal-weight buy-and-hold basket: price at any hour = last 1h open at or before it."""

    def __init__(self) -> None:
        b = pd.read_parquet(DATA / "f11_bars_basket.parquet")
        grid = np.arange(b["t"].min(), b["t"].max() + H, H)
        self.t0 = int(grid[0])
        self.px = b.pivot(index="t", columns="symbol", values="o").reindex(grid).ffill()
        f = pd.read_parquet(DATA / "f11_funding_basket.parquet").sort_values("t")
        self.fund = {s: (g["t"].to_numpy(), np.cumsum(g["rate"].to_numpy()))
                     for s, g in f.groupby("symbol")}

    def _cum_fund(self, s: str, t: int) -> float:
        ts, cum = self.fund.get(s, (np.array([]), np.array([])))
        i = np.searchsorted(ts, t, side="right")
        return float(cum[i - 1]) if i else 0.0

    def legs(self, ta: int, tb: int, exclude: set[str]) -> tuple[float, float, int]:
        """(mean return, mean funding paid by a long, n legs) over (ta, tb]."""
        pa = self.px.iloc[(ta - self.t0) // H]
        pb = self.px.iloc[min((tb - self.t0) // H, len(self.px) - 1)]
        legs = [s for s in self.px.columns
                if s not in exclude and pa[s] == pa[s] and pb[s] == pb[s]]
        ret = float(np.mean([pb[s] / pa[s] - 1.0 for s in legs]))
        fund = float(np.mean([self._cum_fund(s, tb) - self._cum_fund(s, ta) for s in legs]))
        return ret, fund, len(legs)


def _trade(row, bars: pd.DataFrame, rates: pd.DataFrame, basket: Basket) -> dict | None:
    te, tx = row.t1 + ENTRY, row.t1 + EXIT
    b = bars[(bars["t"] >= te) & (bars["t"] <= tx)]
    if b.empty or b["t"].iloc[0] > te + D:
        return None
    t_in, entry = int(b["t"].iloc[0]), float(b["o"].iloc[0])
    after = rates["t"].to_numpy() > t_in
    rts = rates["t"].to_numpy()[after]
    cum = np.concatenate([[0.0], np.cumsum(rates["rate"].to_numpy()[after])])

    def f_to(t) -> np.ndarray:  # funding a short receives over (t_in, t]
        return cum[np.searchsorted(rts, t, side="right")]

    if int(b["t"].iloc[-1]) == tx:
        kind, t_end, p_end = "full", tx, float(b["o"].iloc[-1])
    else:
        kind = "delist" if int(b["t"].iloc[-1]) < tx - D else "gap"
        t_end, p_end = int(b["t"].iloc[-1]) + H, float(b["c"].iloc[-1])
    hold = b[b["t"] < t_end]
    ht = hold["t"].to_numpy()
    liq_px = entry * (2 + f_to(ht)) / (1 + MMR)

    def short_leg(hit: np.ndarray) -> tuple[str, int, float, float]:
        if len(hit):
            t_liq = int(hit[0]) + H
            return "liq", t_liq, -1.0 - float(f_to(t_liq)), float(f_to(t_liq))  # margin gone
        return kind, t_end, -(p_end / entry - 1.0), float(f_to(t_end))

    kind_v, t_out, perp, f_perp = short_leg(ht[hold["h"].to_numpy() >= liq_px])
    out = {"venue": row.venue, "symbol": row.symbol, "listed": row.listed, "t1": row.t1,
           "kind": kind_v, "perp": perp, "f_perp": f_perp,
           "unhedged": perp + f_perp - FEE_RT}
    for tag, excl in (("", NO_BETA | {row.symbol}), ("_41", {row.symbol})):
        r_b, f_b, n = basket.legs(t_in, t_out, excl)
        out |= {f"basket{tag}": r_b, f"f_basket{tag}": f_b, f"n_legs{tag}": n,
                f"net{tag}": perp + f_perp + r_b - f_b - 2 * FEE_RT}
    _, t_c, perp_c, f_c = short_leg(ht[hold["c"].to_numpy() >= liq_px])
    r_b, f_b, _ = basket.legs(t_in, t_c, NO_BETA | {row.symbol})
    out["net_closeliq"] = perp_c + f_c + r_b - f_b - 2 * FEE_RT
    r_b, f_b, _ = basket.legs(t_in, t_end, NO_BETA | {row.symbol})
    short = max(-1.0, -(p_end / entry - 1.0) + float(f_to(t_end)))
    out["net_noliq"] = short + r_b - f_b - 2 * FEE_RT
    return out


# ---------------------------------------------------------------- verdict
def _cluster_ci(x: np.ndarray, months: pd.Series) -> tuple[float, float]:
    codes, uniq = pd.factorize(months)
    sums, cnts = np.bincount(codes, weights=x), np.bincount(codes)
    idx = np.random.default_rng(SEED).integers(0, len(uniq), size=(BOOT, len(uniq)))
    means = sums[idx].sum(axis=1) / cnts[idx].sum(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def _verdict(v: pd.DataFrame, col: str) -> tuple[bool, list[str]]:
    x = v[col].to_numpy()
    months = pd.to_datetime(v["listed"], unit="ms").dt.to_period("M")
    lo, hi = _cluster_ci(x, months)
    rec = v.loc[v["t1"] >= v["t1"].max() - 730 * D, col]
    top5 = v[col].nlargest(5).sum() / x.sum() if x.sum() > 0 else float("inf")
    checks = [
        (f"N >= {PASS_N}", len(x) >= PASS_N, f"{len(x)}"),
        (f"mean >= +{PASS_MEAN:.0%}", x.mean() >= PASS_MEAN, f"{x.mean():+.2%}"),
        ("median > 0", np.median(x) > 0, f"{np.median(x):+.2%}"),
        ("95% CI ex-zero", lo > 0,
         f"[{lo:+.2%}, {hi:+.2%}] ({len(months.unique())} month clusters)"),
        ("recent-24mo mean > 0", rec.mean() > 0, f"{rec.mean():+.2%} (n={len(rec)})"),
        (f"top-5 < {TOP5_MAX:.0%} of PnL", top5 < TOP5_MAX,
         f"{top5:.0%}" if np.isfinite(top5) else "total PnL <= 0"),
    ]
    lines = [f"    {name:<22}: {'PASS' if ok else 'FAIL'}   {val}" for name, ok, val in checks]
    return all(ok for _, ok, _ in checks), lines


def main() -> None:
    for venue in ("bybit", "binance"):
        if not (DATA / f"f11_bars_{venue}.parquet").exists():
            t0 = time.time()
            _pull_venue(venue)
            print(f"  {venue} pulled in {time.time() - t0:.0f}s")
    if not (DATA / "f11_bars_basket.parquet").exists():
        t0 = time.time()
        _pull_basket()
        print(f"  basket pulled in {time.time() - t0:.0f}s")

    basket = Basket()
    verdicts = {}
    for venue in ("binance", "bybit"):
        ev = _events(venue)
        bars = {s: g for s, g in pd.read_parquet(DATA / f"f11_bars_{venue}.parquet")
                .sort_values("t").groupby("symbol")}
        rates = {s: g for s, g in pd.read_parquet(DATA / f"f11_funding_{venue}.parquet")
                 .sort_values("t").groupby("symbol")}
        empty = pd.DataFrame({"t": pd.Series(dtype="int64"), "rate": pd.Series(dtype=float)})
        rows = [_trade(r, bars[r.symbol], rates.get(r.symbol, empty), basket)
                for r in ev.itertuples() if r.symbol in bars]
        v = pd.DataFrame([r for r in rows if r])
        v["year"] = pd.to_datetime(v["t1"], unit="ms").dt.year

        print(f"\n{'=' * 78}\n{venue.upper()}: {len(ev)} F6 events with a complete window, "
              f"{len(ev) - len(bars)} unserved, {len(rows) - len(v)} without an entry bar -> "
              f"N={len(v)}\n  t1 {pd.Timestamp(v['t1'].min(), unit='ms').date()} -> "
              f"{pd.Timestamp(v['t1'].max(), unit='ms').date()}   exits: "
              + ", ".join(f"{k} {n}" for k, n in v["kind"].value_counts().items())
              + f"   basket legs {v['n_legs'].min()}-{v['n_legs'].max()}\n{'=' * 78}")
        ok, lines = _verdict(v, "net")
        verdicts[venue] = ok
        print("  HEDGED (37-leg alt basket) -- the verdict:")
        print("\n".join(lines))
        print(f"  {venue}: {'PASS' if ok else 'KILL'}")

        print("  components (mean / median): short perp leg "
              f"{v['perp'].mean():+.2%} / {v['perp'].median():+.2%}, perp funding received "
              f"{v['f_perp'].mean():+.2%}, basket {v['basket'].mean():+.2%} / "
              f"{v['basket'].median():+.2%}, basket funding paid {v['f_basket'].mean():+.2%}")
        print("  per year (mean net, n): " + "  ".join(
            f"{y} {g['net'].mean():+.1%} n={len(g)}" for y, g in v.groupby("year")))
        ok41, lines41 = _verdict(v, "net_41")
        print(f"  sensitivity, literal 41-leg basket: {'PASS' if ok41 else 'KILL'}"
              + ("  <-- DIFFERS from the verdict" if ok41 != ok else ""))
        print("\n".join(lines41))
        ok_cl, lines_cl = _verdict(v, "net_closeliq")
        print(f"  sensitivity, CLOSE-LIQ (liquidated only on a 1h close, a generous mark-price "
              f"proxy): {'PASS' if ok_cl else 'KILL'}"
              + ("  <-- DIFFERS from the verdict" if ok_cl != ok else ""))
        print("\n".join(lines_cl))
        ok_nl, lines_nl = _verdict(v, "net_noliq")
        print(f"  sensitivity, NO-LIQ (never liquidated, floored at -100%): "
              f"{'PASS' if ok_nl else 'KILL'}"
              + ("  <-- DIFFERS from the verdict" if ok_nl != ok else ""))
        print("\n".join(lines_nl))
        _, lines_u = _verdict(v, "unhedged")
        print("  UNHEDGED short (never blended; thresholds shown for scale only):")
        print("\n".join(lines_u))
        worst = v.nsmallest(5, "net")
        print("  worst 5 hedged: " + ", ".join(
            f"{r.symbol} {r.net:+.0%} ({r.kind})" for r in worst.itertuples()))
        best = v.nlargest(5, "net")
        print("  best 5 hedged:  " + ", ".join(
            f"{r.symbol} {r.net:+.0%} ({r.kind})" for r in best.itertuples()))

    idea = "PASS" if all(verdicts.values()) else "KILL"
    print(f"\n{'=' * 78}\nF11 VERDICT: {idea}  ("
          + ", ".join(f"{k} {'PASS' if x else 'KILL'}" for k, x in verdicts.items()) + ")")
    if idea == "PASS":
        print("  Licenses a Hyperliquid recheck + bot design for a slow hedged short basket. "
              "Not a deployment.")


if __name__ == "__main__":
    main()
