"""F4 - TOKEN-UNLOCK SHORT (idea 4 of the Fable batch). Pre-registered BEFORE any price is read.

Written 2026-10-19 while `probes/z2_backfill_um_1d.py` was still loading the 1d perp data and
before any event return existed. The event list is frozen separately and reads no price
(`probes/f4_unlock_events.py` -> runs/f4_unlock_events.json).

THE IDEA ([[fable-batch-10-probe-queue]] #4). Short the perp 7 days before a scheduled unlock of
insider / VC tokens, cover on the unlock day. Pays: holders with a near-zero cost basis selling
on a published schedule, and traders front-running them. Open question: has publication killed it?

EVENT (see f4_unlock_events.py). Insider or private-sale tranches (cliff or monthly step, not
linear) summing to >= 1% of the coin's schedule-unlocked supply on one UTC day, 2020-01 -> 2026-09,
on a coin with a Binance USDT-M perp. Delisted perps are included (Z2 loads them from the dumps).

TRADE, per event with unlock day T, on Binance USDT-M perp 1d bars:
  * Short at the open of day T-7, cover at the open of day T. The bars for days T-7 .. T must
    all exist, else the event is skipped (not listed yet, or delisted).
  * NET = (open[T-7] - open[T]) / open[T-7] - 0.20% (taker round trip, Fable's figure)
          + the sum of funding settlements in (entry, exit] (a short receives a positive rate).
  * 1x isolated: if a daily high in T-7 .. T-1 reaches 1.99 x entry, the short is liquidated and
    books -100%.
  * One position per coin: an event whose entry falls before the same coin's previous cover is
    skipped.

THE FROZEN RULE (Fable's four, plus R5; ANY miss = KILL):
  R1 mean NET >= +0.50% per event.
  R2 N >= 80 events.
  R3 95% CI on the mean excludes zero. Bootstrap (10,000) clustered by the ISO week of T, since
     events in the same week share the market's move.
  R4 mean NET > 0 in >= 2 calendar years.
  R5 PLACEBO (a tightening added here, before any data): the unlock must matter, not just "VC coins
     bleed". For each event, the same short on the same coin over the 7-day windows ending at
     T-21, T-14, T+14 and T+21, skipping windows that overlap any of that coin's event windows or
     lack data. R5 holds if the 95% CI (same clustering) on mean(event NET - mean placebo NET)
     lies above zero. Events with no valid placebo window drop out of R5 only.
  A PASS licenses a forward/paper test, never live money: [[live-yield-hurdle]] still applies.

CAVEATS, declared before running:
  * LOOK-AHEAD IN THE SCHEDULES. DefiLlama writes and edits the adapters after the fact. A delayed
    or cancelled unlock may sit in the file as it actually happened, not as it was announced at T-7.
  * EVENT-SIDE SURVIVORSHIP. The perp side includes delisted contracts; the event side is
    DefiLlama's coverage (310 protocols, mostly projects that lasted).
  * SUPPLY IS AN ESTIMATE (schedule-unlocked, not circulating), so the 1% cut is approximate.
  * Ticker collisions in the CoinGecko -> Binance match are not checked.
  * Venue: Binance prints stand in for Hyperliquid, which lists only part of these coins.

Run:
  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
  PYTHONPATH="src;." .venv/Scripts/python probes/f4_unlock_cliff_short.py
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd

from coinmon.data import db

EVENTS = "runs/f4_unlock_events.json"
EXCHANGE = "binance"
HOLD_DAYS = 7
RT_COST = 0.0020
LIQ = 1.99
PLACEBO_OFFSETS = (-21, -14, 14, 21)
R1_MIN, R2_MIN_N = 0.005, 80
BOOT, SEED = 10_000, 20261019
RECENT_FROM = date(2024, 10, 1)  # last 24 months of data, for the post-verdict diagnostic


class Coin:
    """One perp's daily bars and funding, indexed for window lookups."""

    def __init__(self, candles: pd.DataFrame, funding: pd.DataFrame) -> None:
        days = pd.to_datetime(candles["open_time"], unit="ms", utc=True).dt.date
        self.idx = {d: i for i, d in enumerate(days)}
        self.days = list(days)
        self.t = candles["open_time"].to_numpy("int64")
        self.open = candles["open"].to_numpy(float)
        self.high = candles["high"].to_numpy(float)
        self.ft = funding["funding_time"].to_numpy("int64")
        self.fr = funding["rate"].to_numpy(float)

    def short(self, entry: date, exit_: date) -> float | None:
        """NET of a short, open of `entry` -> open of `exit_`; None if a bar is missing."""
        i, j = self.idx.get(entry), self.idx.get(exit_)
        if i is None or j is None or j - i != (exit_ - entry).days:
            return None
        e = self.open[i]
        if self.high[i:j].max() >= LIQ * e:
            return -1.0
        m = (self.ft > self.t[i]) & (self.ft <= self.t[j])
        return (e - self.open[j]) / e - RT_COST + float(self.fr[m].sum())


def _boot_ci(values: np.ndarray, weeks: list) -> tuple[float, float]:
    groups = defaultdict(list)
    for v, w in zip(values, weeks, strict=True):
        groups[w].append(v)
    blocks = [np.array(g) for g in groups.values()]
    rng = np.random.default_rng(SEED)
    means = np.empty(BOOT)
    for b in range(BOOT):
        pick = rng.integers(0, len(blocks), len(blocks))
        means[b] = np.concatenate([blocks[k] for k in pick]).mean()
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def _week(d: date) -> tuple[int, int]:
    return d.isocalendar()[:2]


def main() -> None:
    events = json.load(open(EVENTS, encoding="utf-8"))
    conn = db.connect()
    coins = {}
    for perp in sorted({e["perp"] for e in events}):
        coins[perp] = Coin(db.read_candles(conn, EXCHANGE, perp, "1d"),
                           db.read_funding(conn, EXCHANGE, perp))

    by_coin = defaultdict(list)
    for e in events:
        e["T"] = date.fromisoformat(e["day"])
        by_coin[e["perp"]].append(e)

    taken, skipped = [], Counter()
    for perp, evs in by_coin.items():
        evs.sort(key=lambda e: e["T"])
        windows = [(e["T"] - timedelta(days=HOLD_DAYS), e["T"]) for e in evs]
        last_cover = None
        for e in evs:
            entry = e["T"] - timedelta(days=HOLD_DAYS)
            if last_cover is not None and entry < last_cover:
                skipped["overlaps the coin's previous event"] += 1
                continue
            net = coins[perp].short(entry, e["T"])
            if net is None:
                skipped["perp not trading through the window"] += 1
                continue
            last_cover = e["T"]
            placebo = []
            for k in PLACEBO_OFFSETS:
                end = e["T"] + timedelta(days=k)
                start = end - timedelta(days=HOLD_DAYS)
                if any(start < w1 and w0 < end for w0, w1 in windows):
                    continue
                p = coins[perp].short(start, end)
                if p is not None:
                    placebo.append(p)
            taken.append({**e, "net": net, "placebo": placebo})

    for k, v in skipped.items():
        print(f"  skipped: {k:<40} {v}")
    if not taken:
        print("No tradable events.")
        return
    net = np.array([e["net"] for e in taken])
    weeks = [_week(e["T"]) for e in taken]
    lo, hi = _boot_ci(net, weeks)
    by_year = pd.Series(net, index=[e["T"].year for e in taken]).groupby(level=0)
    pos_years = int((by_year.mean() > 0).sum())
    with_p = [e for e in taken if e["placebo"]]
    diff = np.array([e["net"] - np.mean(e["placebo"]) for e in with_p])
    d_lo, d_hi = _boot_ci(diff, [_week(e["T"]) for e in with_p]) if len(with_p) else (0.0, 0.0)

    print(f"\n{'=' * 72}\nF4 TOKEN-UNLOCK SHORT - {len(taken)} events, {len(by_coin)} coins listed,"
          f" {len({e['perp'] for e in taken})} traded\n{'=' * 72}")
    print(f"  mean NET / event        : {net.mean() * 100:+.3f}%"
          f"   median {np.median(net) * 100:+.3f}%   win {np.mean(net > 0) * 100:.1f}%")
    print(f"  95% CI (week clusters)  : [{lo * 100:+.3f}%, {hi * 100:+.3f}%]")
    print(f"  liquidated (-100%)      : {int((net <= -1.0).sum())}")
    print("  per year:")
    for y, g in by_year:
        print(f"    {y}  {g.mean() * 100:+.3f}%   n={len(g)}")
    print(f"  placebo: {len(with_p)} events with >= 1 window; mean placebo NET"
          f" {np.mean([np.mean(e['placebo']) for e in with_p]) * 100:+.3f}%;"
          f" event - placebo {diff.mean() * 100:+.3f}%"
          f"  CI [{d_lo * 100:+.3f}%, {d_hi * 100:+.3f}%]")

    rules = [
        (f"R1 mean >= {R1_MIN * 100:.2f}%", net.mean() >= R1_MIN),
        (f"R2 N >= {R2_MIN_N}", len(taken) >= R2_MIN_N),
        ("R3 95% CI excludes zero", lo > 0 or hi < 0),
        ("R4 positive in >= 2 years", pos_years >= 2),
        ("R5 beats same-coin placebo", d_lo > 0),
    ]
    print()
    for name, ok in rules:
        print(f"  {name:<32}: {'PASS' if ok else 'FAIL'}")
    print(f"\n  VERDICT: {'PASS' if all(ok for _, ok in rules) else 'KILL'}")
    _diagnostics(taken, coins)


# ====================================================== POST-VERDICT DIAGNOSTICS (not frozen)


def _summ(label: str, evs: list) -> None:
    if not evs:
        print(f"    {label:<30} N=   0")
        return
    v = np.array([e["net"] for e in evs])
    lo, hi = _boot_ci(v, [_week(e["T"]) for e in evs])
    print(f"    {label:<30} N={len(v):>4}  mean {v.mean() * 100:+.3f}%  CI [{lo * 100:+.3f}%,"
          f" {hi * 100:+.3f}%]")


def _diagnostics(taken: list, coins: dict) -> None:
    print(f"\n{'=' * 72}\nPOST-VERDICT DIAGNOSTICS - do not change the verdict\n{'=' * 72}")
    print("\nD-A  by unlock size (share of schedule-unlocked supply)")
    for a, b in ((0.01, 0.02), (0.02, 0.05), (0.05, 0.10), (0.10, np.inf)):
        _summ(f"[{a * 100:.0f}%, {b * 100:.0f}%)", [e for e in taken if a <= e["share"] < b])
    print("\nD-B  tranche kind")
    _summ("includes a cliff", [e for e in taken if "cliff" in e["kind"]])
    _summ("monthly step only", [e for e in taken if e["kind"] == "step"])
    print(f"\nD-C  recent: unlock day >= {RECENT_FROM}")
    _summ("recent", [e for e in taken if e["T"] >= RECENT_FROM])

    btc = coins.get("BTC/USDT:USDT")
    if btc is None:
        conn = db.connect()
        btc = Coin(db.read_candles(conn, EXCHANGE, "BTC/USDT:USDT", "1d"),
                   db.read_funding(conn, EXCHANGE, "BTC/USDT:USDT"))
    hedged = []
    for e in taken:
        s = btc.short(e["T"] - timedelta(days=HOLD_DAYS), e["T"])
        if s is not None and e["net"] > -1.0:
            # A long BTC leg is minus the BTC short, plus its own round trip: -(s + RT) - RT.
            hedged.append({**e, "net": e["net"] - s - 2 * RT_COST})
    print("\nD-D  BTC-hedged (long BTC perp, same notional, both legs costed)")
    _summ("hedged", hedged)

    v = pd.Series([e["net"] for e in taken])
    pos = v[v > 0].sort_values()
    print(f"\nD-E  concentration: top-5 events = {pos.tail(5).sum() / v.sum() * 100:.0f}% of summed"
          " NET" if v.sum() > 0 else "\nD-E  summed NET <= 0")
    print("     worst 5:")
    for e in sorted(taken, key=lambda e: e["net"])[:5]:
        print(f"       {e['perp']:<20} {e['day']}  share {e['share'] * 100:5.1f}%"
              f"  NET {e['net'] * 100:+.1f}%")
    print("     best 5:")
    for e in sorted(taken, key=lambda e: -e["net"])[:5]:
        print(f"       {e['perp']:<20} {e['day']}  share {e['share'] * 100:5.1f}%"
              f"  NET {e['net'] * 100:+.1f}%")

    # D-F: what one account earns, capital split into K equal slices, K = the most positions
    # ever open at once (so every event gets a full slice).
    open_on = Counter()
    for e in taken:
        for k in range(HOLD_DAYS):
            open_on[e["T"] - timedelta(days=HOLD_DAYS - k)] += 1
    k_max = max(open_on.values())
    first = min(e["T"] for e in taken) - timedelta(days=HOLD_DAYS)
    last = max(e["T"] for e in taken)
    years = (last - first).days / 365.25
    rec = [e["net"] for e in taken if e["T"] >= RECENT_FROM]
    rec_years = (last - RECENT_FROM).days / 365.25
    print(f"\nD-F  ONE ACCOUNT, {k_max} equal slices (max concurrent), 1x:"
          f" {sum(v) / k_max / years * 100:+.2f}%/yr over {years:.1f}y;"
          f" recent {sum(rec) / k_max / rec_years * 100:+.2f}%/yr")
    print(f"     run at {datetime.now(UTC):%Y-%m-%d %H:%M} UTC")


if __name__ == "__main__":
    main()
