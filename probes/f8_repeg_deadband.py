"""F8 live ladder: what does a wider re-peg deadband cost? An operational diagnostic, not a test.

The F8 verdict ([[f8-cascade-ladder-result]]) is NOT reopened here. The live bot
(``src/coinmon/live/ladder.py``) re-pegs a resting bid only once its rung moved >= DEADBAND
(0.1%), which costs about 2,000 Hyperliquid actions a day on six coins. The venue gives an address
10k actions, then 1 per USDC traded, then one every 10 seconds ([[live-bot-dashboard-plan]]).
This probe replays the live peg on Binance USDT-M perp 1m bars for the six live coins and prices
each deadband variant two ways: venue actions, and the F8 per-event economics.

THE PEG, per minute i, with the bot flat on that coin:
  * rung_i = close[i-1] * (1 - 2.5%), the frozen F8 rung.
  * The resting bid is re-pegged to rung_i only if it sits ABOVE the rung by >= DOWN (price fell:
    the bid is shallower than the rule) or BELOW it by >= UP (price rose: the bid is deeper).
    DOWN = UP = 0 is the frozen rule; DOWN = UP = 0.1% is the live bot.
  * Fill if low[i] <= bid, at the bid (touch-fill, as in the F8 probe). Exit exactly as F8:
    take-profit +1.2% on a later bar within 60 minutes, else the close of minute 60; maker 2bp
    both legs. One position per coin at a time.
  * Actions: each bid placement or modify is one; each fill adds the take-profit placement, and a
    time-stop exit adds the close. Cancels are not counted (the venue budgets them separately).

A shallow bid (above the rung) is the risky deviation: it buys smaller one-minute drops than F8
validated. Those fills are reported separately as "shallow".

Run:
  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
  PYTHONPATH="src;." .venv/Scripts/python probes/f8_repeg_deadband.py
"""
from __future__ import annotations

from collections import Counter

import numpy as np
import pandas as pd

from coinmon.data import db
from probes.f8_cascade_ladder_proxy import DROP, HOLD, RT_COST, SEED, TARGET

EXCHANGE = "binance"
SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT",
           "DOGE/USDT:USDT", "XRP/USDT:USDT", "ADA/USDT:USDT"]  # the live COINS
VARIANTS = [  # (DOWN, UP)
    (0.0, 0.0), (0.001, 0.001), (0.0025, 0.0025), (0.005, 0.005),
    (0.001, 0.005), (0.001, 0.01), (0.0025, 0.01),
]
RECENT_ACTIONS_DAYS = 90
BOOT = 2_000


def simulate(t, low, high, close, down, up):
    """Walk one coin's bars; returns (events, action minute timestamps)."""
    t, low, high, close = t.tolist(), low.tolist(), high.tolist(), close.tolist()
    n = len(t)
    events, actions = [], []
    bid = None
    i = 1
    while i < n:
        rung = close[i - 1] * (1.0 - DROP)
        if bid is None or (bid > rung and bid / rung - 1 >= down) or (
                bid < rung and 1 - bid / rung >= up):
            bid = rung
            actions.append(t[i])
        if low[i] > bid:
            i += 1
            continue
        end = min(i + HOLD, n - 1)
        tp = bid * (1.0 + TARGET)
        hit = max(high[i + 1:end + 1], default=-1.0) >= tp
        exit_px = tp if hit else close[end]
        events.append((t[i], exit_px / bid - 1.0 - RT_COST, bid > rung))
        actions.append(t[i])  # take-profit placement
        if not hit:
            actions.append(t[end])  # time-stop close
        bid = None
        i = end + 1
    return events, actions


def _ci(ev: pd.DataFrame) -> tuple[float, float]:
    blocks = [g.to_numpy() for _, g in ev.groupby("day")["net"]]
    rng = np.random.default_rng(SEED)
    means = [np.concatenate([blocks[j] for j in rng.integers(0, len(blocks), len(blocks))]).mean()
             for _ in range(BOOT)]
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def main() -> None:
    conn = db.connect()
    data = {}
    for s in SYMBOLS:
        df = db.read_candles(conn, EXCHANGE, s, "1m")
        data[s] = (df["open_time"].to_numpy("int64"), df["low"].to_numpy(float),
                   df["high"].to_numpy(float), df["close"].to_numpy(float))
        print(f"  {s}: {len(df):,} bars, {pd.Timestamp(df['open_time'].iloc[0], unit='ms').date()}"
              f" -> {pd.Timestamp(df['open_time'].iloc[-1], unit='ms').date()}")
    last = max(int(v[0][-1]) for v in data.values())
    act_from = last - RECENT_ACTIONS_DAYS * 86_400_000
    recent_from = pd.Timestamp(last, unit="ms", tz="UTC") - pd.Timedelta(days=730)

    print(f"\nactions/day over the last {RECENT_ACTIONS_DAYS} days of data; bursts = minutes"
          " needing >= 2 writes across the six coins (each extra write waits 10s once throttled)")
    print(f"{'DOWN':>6} {'UP':>6} | {'act/day':>7} {'per coin':>34} | {'burst>=2':>8} {'>=4':>5}"
          f" | {'N':>5} {'mean':>7} {'CI':>17} {'shallow':>15} | {'N24':>4} {'mean24':>7}"
          f" {'acct24/yr':>9}")
    for down, up in VARIANTS:
        rows, per_coin, minutes = [], [], Counter()
        for s, (t, lo, hi, cl) in data.items():
            ev, acts = simulate(t, lo, hi, cl, down, up)
            rows += [(s, *e) for e in ev]
            recent_acts = [a for a in acts if a >= act_from]
            per_coin.append(len(recent_acts) / RECENT_ACTIONS_DAYS)
            minutes.update(recent_acts)
        ev = pd.DataFrame(rows, columns=["sym", "t", "net", "shallow"])
        ev["day"] = pd.to_datetime(ev["t"], unit="ms", utc=True).dt.normalize()
        lo, hi = _ci(ev)
        sh = ev[ev["shallow"]]
        rec = ev[ev["day"] >= recent_from.normalize()]
        acct24 = rec["net"].sum() / len(SYMBOLS) / 2.0
        n_min = RECENT_ACTIONS_DAYS * 1440
        burst2 = sum(1 for c in minutes.values() if c >= 2) / n_min
        burst4 = sum(1 for c in minutes.values() if c >= 4) / n_min
        coins = " ".join(f"{c:>5.0f}" for c in per_coin)
        sh_txt = f"{len(sh):>4} {sh['net'].mean() * 100:+.2f}%" if len(sh) else f"{0:>4}      -"
        print(f"{down * 100:>5.2f}% {up * 100:>5.2f}% | {sum(per_coin):>7.0f} {coins} |"
              f" {burst2 * 100:>7.2f}% {burst4 * 100:>4.2f}% | {len(ev):>5}"
              f" {ev['net'].mean() * 100:+.3f}% [{lo * 100:+.3f},{hi * 100:+.3f}] {sh_txt:>15} |"
              f" {len(rec):>4}"
              f" {rec['net'].mean() * 100:+.3f}% {acct24 * 100:>+8.2f}%")


if __name__ == "__main__":
    main()
