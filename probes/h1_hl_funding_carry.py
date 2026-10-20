"""H1 - HYPERLIQUID-NATIVE FUNDING CARRY. Pre-registered 2026-10-20 BEFORE any Hyperliquid funding
or price row was pulled (only spot/perp METADATA was read, to fix the universe).

QUESTION  Can a delta-neutral book on the locked venue (long HL spot, short the same coin's HL perp)
          clear the >=5%/yr live hurdle ([[live-yield-hurdle]]) on TOTAL capital, recent regime?
          W3 ([[w3-carry-first-live-diagnosis]]) and F1 ([[f1-tail-gated-carry-result]]) died of
          funding-premium decay on Bybit/Binance; Hyperliquid's own funding was never measured.
UNIVERSE  The 11 HL perps with a same-asset HL spot pair quoted in USDC and trading >= $100k/day
          on 2026-10-20 (spotMetaAndAssetCtxs): HYPE, BTC (UBTC), ZEC (UZEC), ETH (UETH),
          XMR (XMR1), NEAR (ONEAR), SOL (USOL), PUMP (UPUMP), PURR, XPL (UXPL), ENA (UENA).
          Chosen on today's volume = survivor-flavoured (pairs that died are absent); declared.
WINDOW    2024-10-20 -> 2026-10-20 (the hurdle's recent 24 months). A coin is LIVE from the first
          daily close at which both its spot pair and its perp have a full day of candles:
          point-in-time, because the hedge leg did not exist before its spot listing.
          CORRECTED after the first run (2026-10-20): UBTC's spot closed at 6.97M and 7.98M
          against a ~96k perp in its first 10 days (troll prints on an empty book), and the
          equal-quantity book marked that as an 80x gain and a -99% day. A coin now goes live only
          once its spot market has formed: 7 consecutive daily closes within 2% of the perp
          (FORMED_DAYS, FORMED_GAP), checked point-in-time. Every coin starts 5-6 days later (the
          rule needs a week of both legs); BTC starts 16 days later, past the troll prints. The
          first run's log (KILL, account -47%/yr) is kept as runs/h1_hl_funding_carry_v1.log.
BOOK      Per coin, its own capital E: q coins long spot, q coins short perp (equal QUANTITY),
          perp at L=2 isolated, so E = q*S + q*P/L. Funding is hourly on q * perp close (start of
          day); the short receives +rate. Equity = q*S + margin + q*(entry - P): price-neutral
          except basis, which is measured from the spot and perp daily closes.
MANAGE    Daily, at the close (a bot could do better; daily is conservative). REBALANCE when
          |P/entry - 1| >= 25%: re-size both legs to q' = E/(S + P/L); fees on |q - q'| on both
          legs. LIQUIDATION when the day's perp HIGH reaches (margin + q*entry)/(q*(1 + mm)),
          mm = 1/(2*maxLeverage) from today's meta: the perp leg is lost (equity -> 0), the spot
          leg is kept, the book is re-opened at the close with fees. Funding is credited before
          the day's liquidation check.
FEES      HL tier 0, taker on every leg: perp 0.045%, spot 0.070%. Open at the first close, close
          at the last.
ACCOUNT   One account, equal-weight across LIVE coins: daily return = mean of the live coins'
          daily book returns (inter-coin rebalancing cost ignored: the books are price-neutral,
          so their equity drifts apart only by funding differences). EVALUATION SPAN = from the
          first close with >= 3 coins live, to the end.

PASS      ALL of:
  R0  the evaluation span is >= 365 days (else UNTESTABLE, which is not a pass);
  R1  account net yield over the evaluation span >= +5%/yr;
  R2  account net yield over the last 365 days >= +5%/yr;
  R3  95% CI of the mean daily account return excludes zero (circular block bootstrap,
      30-day blocks, 2,000 draws, seed 20261020);
  R4  >= 2/3 of the coins (rounded up) have positive net yield over their own live span;
  R5  no single coin contributes > 60% of the account's summed return.
KILL      any miss. A PASS licenses paper/micro-live of the carry book, never a deployment
          ([[alpha-definition-edge-certificate]]).

DIAGNOSTICS (none affect the verdict)
  D1  per coin: live from, days, mean funding %/yr, share of hours negative, share of hours
      pinned at the 0.00125%/h interest baseline, rebalances, liquidations, net yield at L=2.
  D2  capital structure: L=1 (band 50%), L=2 (band 25%, frozen), L=3 (band 15%), and NOTIONAL
      (no margin modelled = the portfolio-margin upper bound, yield on hedged notional).
      CORRECTED after the corrected run: NOTIONAL never re-sized, so a coin that rose 4x ran 4x
      notional per unit of equity (HYPE printed +36%/yr on 19%/yr funding). It now re-sizes at
      the same 25% band, so it is the yield on hedged notional it was declared to be.
  D3  account yield per calendar quarter.
  D4  HL vs Binance funding, same coins, same live days (Binance from the DB, to 2026-09-30).
  D5  W3's gate: hold only while the trailing-30d mean funding > 0, else flat (fees on switches).
  D6  POST-HOC, added after the corrected run showed the L=2 losses are liquidations: per coin,
      L=2 with liquidation on the day's CLOSE (a generous mark-price proxy, cf. F11 CLOSE-LIQ)
      and NOTIONAL. Seen in the data; it can only motivate a new pre-registered test.

LOAD      fundingHistory returns <= 500 hourly rows per call, weight ~45. The bot shares this IP's
          1,200/min REST weight (~440/min), so calls are paced at one per 6s (~450/min). About 320
          calls = ~32 minutes; candles are 22 more calls. Caches in data/ (gitignored), so reruns
          read nothing from the venue.

Run:
  PYTHONPATH="src;." .venv/Scripts/python probes/h1_hl_funding_carry.py \
    | tee runs/h1_hl_funding_carry.log
"""
from __future__ import annotations

import math
import time
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

from coinmon.data import db

INFO = "https://api.hyperliquid.xyz/info"
DATA = Path("data")
FUNDING, CANDLES = DATA / "h1_hl_funding.parquet", DATA / "h1_hl_candles.parquet"
H, D = 3_600_000, 86_400_000
START = int(pd.Timestamp("2024-10-20", tz="UTC").timestamp() * 1000)
END = int(pd.Timestamp("2026-10-20", tz="UTC").timestamp() * 1000)
PACE_S = 6.0
FORMED_DAYS, FORMED_GAP = 7, 0.02  # spot market formed: 7 closes in a row within 2% of the perp
GATE_DAYS = 30  # D5 trailing window; funding is pulled this far before each coin's live start

# perp coin -> (HL spot pair, perp maxLeverage on 2026-10-20)
UNIVERSE = {
    "HYPE": ("@107", 10), "BTC": ("@142", 40), "ZEC": ("@272", 10), "ETH": ("@151", 25),
    "XMR": ("@260", 5), "NEAR": ("@496", 10), "SOL": ("@156", 20), "PUMP": ("@188", 10),
    "PURR": ("PURR/USDC", 3), "XPL": ("@210", 10), "ENA": ("@206", 10),
}
F_PERP, F_SPOT = 0.00045, 0.00070
L, BAND = 2, 0.25
STRUCTURES = [(1, 0.50), (2, 0.25), (3, 0.15), (None, 0.25)]  # D2; None = notional
BASELINE = 0.0000125  # 0.01% per 8h interest component, paid hourly
HURDLE, MIN_COINS, MIN_SPAN = 0.05, 3, 365
BLOCK, BOOT, SEED = 30, 2_000, 20261020
TOP_SHARE = 0.60


# --- data ---

class Venue:
    def __init__(self) -> None:
        self._c = httpx.Client(timeout=30.0)
        self._last = 0.0

    def info(self, body: dict):
        for attempt in range(6):
            time.sleep(max(0.0, self._last + PACE_S - time.monotonic()))
            self._last = time.monotonic()
            r = self._c.post(INFO, json=body)
            if r.status_code == 429:
                print(f"  429, backing off 60s (attempt {attempt + 1})", flush=True)
                time.sleep(60)
                continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError("venue kept rate-limiting")


def _candles(v: Venue, coin: str) -> pd.DataFrame:
    rows = v.info({"type": "candleSnapshot",
                   "req": {"coin": coin, "interval": "1d", "startTime": 0, "endTime": END}})
    df = pd.DataFrame(rows)
    return pd.DataFrame({"t": df["t"].astype("int64"), "h": df["h"].astype(float),
                         "c": df["c"].astype(float)})


def _funding(v: Venue, coin: str, start: int) -> pd.DataFrame:
    out, t = [], start
    while t < END:
        rows = v.info({"type": "fundingHistory", "coin": coin, "startTime": t, "endTime": END})
        if not rows:
            break
        out += rows
        t = int(rows[-1]["time"]) + 1
        if len(rows) < 500:
            break
    df = pd.DataFrame(out)
    return pd.DataFrame({"coin": coin, "t": df["time"].astype("int64"),
                         "rate": df["fundingRate"].astype(float)})


def pull() -> None:
    v = Venue()
    if not CANDLES.exists():
        frames = []
        for coin, (pair, _) in UNIVERSE.items():
            for leg, name in (("perp", coin), ("spot", pair)):
                frames.append(_candles(v, name).assign(coin=coin, leg=leg))
        pd.concat(frames).to_parquet(CANDLES)
    candles = pd.read_parquet(CANDLES)
    starts = {c: live_start(candles, c) for c in UNIVERSE}
    calls = sum(math.ceil((END - max(s - GATE_DAYS * D, 0)) / H / 500) for s in starts.values())
    print(f"funding pull: ~{calls} calls at {PACE_S:.0f}s = ~{calls * PACE_S / 60:.0f} min",
          flush=True)
    done = pd.read_parquet(FUNDING) if FUNDING.exists() else pd.DataFrame()
    for coin, s in starts.items():
        if not done.empty and coin in set(done["coin"]):
            continue
        f = _funding(v, coin, s - GATE_DAYS * D)
        done = pd.concat([done, f]) if not done.empty else f
        done.to_parquet(FUNDING)
        print(f"  {coin}: {len(f)} hourly rows", flush=True)


def live_start(candles: pd.DataFrame, coin: str) -> int:
    """First daily close, inside the window, at which both legs have a full day of candles and
    the spot market has formed (the last FORMED_DAYS closes within FORMED_GAP of the perp)."""
    c = candles[candles.coin == coin]
    first = max(c[c.leg == leg]["t"].min() for leg in ("perp", "spot")) + 2 * D
    p = c[c.leg == "perp"].set_index("t")["c"]
    s = c[c.leg == "spot"].set_index("t")["c"]
    near = ((s / p - 1).abs() <= FORMED_GAP).dropna().sort_index()
    formed = near.astype(int).rolling(FORMED_DAYS).sum() == FORMED_DAYS
    ok = [t + D for t in formed[formed].index if t + D >= max(START, first)]
    return int(ok[0])  # a candle t closes at t + D


# --- the book ---

def book(coin: str, candles: pd.DataFrame, fund: pd.DataFrame, lev: int | None, band: float | None,
         gate: bool = False, liq_on: str = "h") -> tuple[pd.Series, dict]:
    """Daily returns of one coin's carry book, indexed by close time (ms), plus counters."""
    perp = candles[(candles.coin == coin) & (candles.leg == "perp")].set_index("t")
    spot = candles[(candles.coin == coin) & (candles.leg == "spot")].set_index("t")
    t0 = live_start(candles, coin)
    # candle t = open of the day; its close is t + D
    closes = sorted(t + D for t in perp.index.intersection(spot.index) if t0 <= t + D <= END)
    f = fund[fund.coin == coin]
    by_close = f.groupby((f["t"] - 1) // D * D + D)["rate"]  # hour h counts in the day (h-D, h]
    day_sum, day_n = by_close.sum(), by_close.count()
    mm = 1 / (2 * UNIVERSE[coin][1])
    E, q, entry, margin = 1.0, 0.0, 0.0, 0.0
    rets, n_reb, n_liq, n_sw = {}, 0, 0, 0
    E_prev = E  # so the opening fee lands in the first day's return

    def px(t):
        return perp.at[t - D, "c"], spot.at[t - D, "c"]

    def size(eq, P, S):
        return eq / (S + (P / lev if lev else 0.0))

    def open_(eq, t):
        P, S = px(t)
        qq = size(eq, P, S)
        eq -= qq * (S * F_SPOT + P * F_PERP)
        return eq, size(eq, P, S), P, (size(eq, P, S) * P / lev if lev else 0.0)

    def gate_on(t) -> bool:
        w = slice(t - (GATE_DAYS - 1) * D, t)
        n = day_n.loc[w].sum()
        return n > 0 and day_sum.loc[w].sum() / n > 0

    holding = not gate or gate_on(closes[0])
    if holding:
        E, q, entry, margin = open_(E, closes[0])
    for prev, t in zip(closes, closes[1:], strict=False):
        P0, _ = px(prev)
        P, S = px(t)
        if holding:
            margin += day_sum.loc[prev + D:t].sum() * q * P0
            liq = (margin + q * entry) / (q * (1 + mm)) if lev else math.inf
            if perp.at[t - D, liq_on] >= liq:
                n_liq += 1
                E = q * S  # perp leg lost; spot kept
                E, q, entry, margin = open_(E, t)
            else:
                E = q * S + margin + q * (entry - P)
                if band and abs(P / entry - 1) >= band:
                    n_reb += 1
                    q2 = size(E, P, S)
                    E -= abs(q - q2) * (S * F_SPOT + P * F_PERP)
                    q, entry = size(E, P, S), P
                    margin = q * P / lev if lev else 0.0
        if gate and gate_on(t) != holding:
            n_sw += 1
            if holding:
                E -= q * (S * F_SPOT + P * F_PERP)
                holding = False
            else:
                E, q, entry, margin = open_(E, t)
                holding = True
        if t == closes[-1] and holding:
            E -= q * (S * F_SPOT + P * F_PERP)
        rets[t] = E / E_prev - 1
        E_prev = E
    return pd.Series(rets, dtype=float), {"rebalances": n_reb, "liquidations": n_liq,
                                          "switches": n_sw}


def ann(r: pd.Series) -> float:
    return math.exp(np.log1p(r).sum() * 365 / len(r)) - 1 if len(r) else float("nan")


def account(books: dict[str, pd.Series]) -> tuple[pd.Series, pd.DataFrame]:
    panel = pd.DataFrame(books).sort_index()
    live = panel.notna().sum(axis=1)
    first = live[live >= MIN_COINS].index.min()
    span = panel.loc[first:]
    return span.mean(axis=1), span


def block_ci(x: np.ndarray) -> tuple[float, float]:
    rng = np.random.default_rng(SEED)
    n = len(x)
    k = math.ceil(n / BLOCK)
    means = np.empty(BOOT)
    for i in range(BOOT):
        idx = (rng.integers(0, n, k)[:, None] + np.arange(BLOCK)).ravel()[:n] % n
        means[i] = x[idx].mean()
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def day(t: int) -> str:
    return pd.Timestamp(t, unit="ms", tz="UTC").strftime("%Y-%m-%d")


def main() -> None:
    pull()
    candles, fund = pd.read_parquet(CANDLES), pd.read_parquet(FUNDING)
    print(f"\nH1 Hyperliquid funding carry, window {day(START)} -> {day(END)}, "
          f"L={L} band {BAND:.0%}, taker perp {F_PERP:.3%} / spot {F_SPOT:.3%}\n")

    books, stats = {}, {}
    for coin in UNIVERSE:
        books[coin], stats[coin] = book(coin, candles, fund, L, BAND)

    # D1
    print("D1 per coin (L=2 book; funding stats over the coin's live span)")
    print(f"  {'coin':<5} {'live from':<11} {'days':>5} {'fund %/yr':>9} {'neg h':>6} "
          f"{'pinned':>7} {'cover':>6} {'reb':>4} {'liq':>4} {'net %/yr':>9}")
    for coin, r in books.items():
        s = live_start(candles, coin)
        f = fund[(fund.coin == coin) & (fund.t > s) & (fund.t <= END)]["rate"]
        hours = (END - s) / H
        print(f"  {coin:<5} {day(s):<11} {len(r):>5} {f.mean() * 8760:>9.2%} "
              f"{(f < 0).mean():>6.1%} {(abs(f - BASELINE) < 1e-10).mean():>7.1%} "
              f"{len(f) / hours:>6.1%} {stats[coin]['rebalances']:>4} "
              f"{stats[coin]['liquidations']:>4} {ann(r):>9.2%}")

    acct, span = account(books)
    print(f"\nACCOUNT  evaluation span {day(acct.index[0])} -> {day(acct.index[-1])} "
          f"({len(acct)} days, {MIN_COINS}+ coins live; {span.notna().sum(axis=1).iloc[-1]} at "
          f"the end)")
    y_all, y_last = ann(acct), ann(acct.iloc[-365:])
    lo, hi = block_ci(acct.to_numpy())
    per_coin = {c: ann(r.dropna()) for c, r in books.items()}
    n_pos = sum(v > 0 for v in per_coin.values())
    need = math.ceil(len(UNIVERSE) * 2 / 3)
    contrib = span.div(span.notna().sum(axis=1), axis=0).sum()
    share = contrib / contrib.sum() if contrib.sum() > 0 else contrib * np.nan
    top = share.idxmax() if share.notna().any() else "-"

    rules = [
        ("R0 span >= 365 days", len(acct) >= MIN_SPAN, f"{len(acct)} days"),
        ("R1 account yield >= 5%/yr", y_all >= HURDLE, f"{y_all:+.2%}/yr"),
        ("R2 last 365 days >= 5%/yr", y_last >= HURDLE, f"{y_last:+.2%}/yr"),
        ("R3 95% CI of mean daily return ex-zero", lo > 0,
         f"[{lo * 365:+.2%}, {hi * 365:+.2%}]/yr (simple)"),
        (f"R4 >= {need}/{len(UNIVERSE)} coins positive", n_pos >= need, f"{n_pos}/{len(UNIVERSE)}"),
        ("R5 top coin <= 60% of return", bool(share.max() <= TOP_SHARE) if share.notna().any()
         else False, f"{top} {share.max():.0%}" if share.notna().any() else "n/a"),
    ]
    for name, ok, val in rules:
        print(f"  {'PASS' if ok else 'FAIL'}  {name:<40} {val}")
    if len(acct) < MIN_SPAN:
        verdict = "UNTESTABLE"
    else:
        verdict = "PASS" if all(ok for _, ok, _ in rules) else "KILL"
    print(f"\nH1 VERDICT: {verdict}")

    print("\nD2 capital structure (account yield, same span; band = rebalance trigger)")
    for lev, band in STRUCTURES:
        b = {c: book(c, candles, fund, lev, band) for c in UNIVERSE}
        a = pd.DataFrame({c: r for c, (r, _) in b.items()}).loc[acct.index].mean(axis=1)
        liqs = sum(s["liquidations"] for _, s in b.values())
        label = f"L={lev} band {band:.0%}" if lev else "NOTIONAL (portfolio-margin bound)"
        print(f"  {label:<34} {ann(a):+8.2%}/yr  last 365d {ann(a.iloc[-365:]):+8.2%}/yr  "
              f"liquidations {liqs}")

    print("\nD3 account yield by quarter (annualized)")
    q = acct.groupby(pd.to_datetime(acct.index, unit="ms").to_period("Q"))
    for per, r in q:
        print(f"  {per}  {ann(r):+8.2%}/yr  ({len(r)} days)")

    print("\nD4 HL vs Binance funding, same coin, same live days to 2026-09-30 (%/yr)")
    cut = int(pd.Timestamp("2026-10-01", tz="UTC").timestamp() * 1000)
    with db.connect() as conn:
        for coin in UNIVERSE:
            bn = db.read_funding(conn, "binance", f"{coin}/USDT:USDT")
            if bn.empty:
                print(f"  {coin:<5} no Binance funding in the DB")
                continue
            s = max(live_start(candles, coin), int(bn["funding_time"].min()))
            hl = fund[(fund.coin == coin) & (fund.t > s) & (fund.t < cut)]
            b = bn[(bn.funding_time > s) & (bn.funding_time < cut)]
            days = (cut - s) / D
            print(f"  {coin:<5} HL {hl.rate.sum() * 365 / days:+8.2%}   "
                  f"Binance {b.rate.sum() * 365 / days:+8.2%}   ({days:.0f} days)")

    print("\nD5 W3 gate (hold while trailing-30d mean funding > 0), L=2 band 25%")
    gated = {c: book(c, candles, fund, L, BAND, gate=True) for c in UNIVERSE}
    g = pd.DataFrame({c: r for c, (r, _) in gated.items()}).loc[acct.index].mean(axis=1)
    print(f"  gated {ann(g):+.2%}/yr vs always-on {y_all:+.2%}/yr; last 365d "
          f"{ann(g.iloc[-365:]):+.2%} vs {y_last:+.2%}; switches "
          f"{sum(s['switches'] for _, s in gated.values())}")

    print("\nD6 POST-HOC: per coin %/yr over its live span (not a verdict)")
    print(f"  {'coin':<5} {'L=2 high-liq':>13} {'L=2 close-liq':>14} {'liq':>4} {'NOTIONAL':>9}")
    rows = {}
    for coin in UNIVERSE:
        cl, cs = book(coin, candles, fund, L, BAND, liq_on="c")
        nt, _ = book(coin, candles, fund, None, BAND)
        rows[coin] = cl
        print(f"  {coin:<5} {ann(books[coin]):>13.2%} {ann(cl):>14.2%} {cs['liquidations']:>4} "
              f"{ann(nt):>9.2%}")
    a = pd.DataFrame(rows).loc[acct.index].mean(axis=1)
    print(f"  account, L=2 close-liq: {ann(a):+.2%}/yr, last 365d {ann(a.iloc[-365:]):+.2%}/yr")


if __name__ == "__main__":
    main()
