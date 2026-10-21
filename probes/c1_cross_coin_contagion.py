"""C1 — cross-coin cascade contagion: when one coin crashes (or pumps), do the others follow?

Pre-registered 2026-10-21, BEFORE any 1m bar was read for this probe. Owner idea 2026-10-20 ("if
shit happens in one place, prep for it in another", [[swarm-and-cross-market-ideas]]). Earlier
lead-lag tests were all at slow scales and all dead: B3 Binance vs Bybit on 4h bars, H4 BTC vs alts
daily ([[plan-b-p1-results]]). This is the first test at minute scale. Cross-VENUE at second scale
needs a collector and is NOT tested here.

DATA: Binance USDT-M perp 1m for F8's 10 coins (BTC ETH SOL DOGE AVAX NEAR LINK 1000SHIB ADA XRP),
2021-01 -> 2026-09 (`probes/z1_backfill_1m.py --perp`), aligned on one minute grid.

DEFINITIONS:
  Trigger — coin X at minute i: low_i <= close_{i-1} * (1 - 2.5%) (F8's rung touch; the previous
     minute must exist). Up-trigger (mirror): high_i >= close_{i-1} * (1 + 2.5%).
  Episode — minute t where at least one coin triggers and NO coin triggered in [t-60, t-1].
     Leaders = coins triggering at t; laggards = coins with data at t that did not.

TESTS (three, so each uses a Bonferroni 98.33% interval; day-cluster bootstrap, 10,000 resamples):
  T1-DOWN (directional) — short every laggard at the open of t+1, cover at the close of t+15,
     Hyperliquid taker both legs (0.09% round trip). The signal is known by the close of t;
     entering on the next open is reachable from the EU box. Spread widening inside a cascade is
     NOT modelled, which flatters T1.
  T1-UP (mirror, "good shit happens") — on up-episodes, long every laggard, same timing and fees.
     PASS (each separately) iff N >= 300 laggard-events AND mean net >= +0.10%/event AND the
     98.33% CI lower bound > 0 AND mean net > 0 in both halves of the sample (split at the median
     episode date).
  T2 (F8 placement) — F8's frozen rule replayed exactly as `f8_cascade_ladder_proxy.py --perp`
     (self-check: N 2261, mean +0.509%). Each fill on coin B at minute i is LED if another coin
     triggered in [i-15, i-1], ISOLATED if no other coin triggered in [i-15, i] (same-minute-only
     fills are reported, not tested). PASS iff both buckets have N >= 100 AND the 98.33% CI of
     mean(LED) - mean(ISOLATED) excludes zero. Two-sided: LED worse means "pull the other coins'
     bids after a leader cascades", LED better means "add a rung on them".

WHAT A PASS LICENSES: the matching rule as a PAPER bot in the swarm (owner 2026-10-21: paper by
default). Nothing changes on the live F8 book.

DIAGNOSTIC (no gate): how much more likely a laggard is to trigger within 15 minutes after an
episode, vs any 15-minute window; T1 at 1/5/30/60 minutes; T1 by BTC-led vs alt-led.

Run:
  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
  PYTHONPATH="src;." .venv/Scripts/python probes/c1_cross_coin_contagion.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from coinmon.data import db
from probes.f8_cascade_ladder_proxy import DROP, HOLD, PERP_SYMBOLS, RT_COST, TARGET

M = 60_000
QUIET = 60  # minutes with no trigger before an episode
HORIZON = 15  # T1 exit minute after the trigger minute
LEAD_WINDOW = 15  # T2: another coin triggered within this many minutes before the fill
HL_RT_TAKER = 2 * 0.00045
T1_MIN, MIN_N_T1, MIN_N_T2 = 0.0010, 300, 100
BOOT, SEED = 10_000, 20261021
LO, HI = 100 * (0.05 / 3) / 2, 100 - 100 * (0.05 / 3) / 2  # Bonferroni over 3 tests


# --- data ---

def load() -> tuple[np.ndarray, dict[str, dict[str, np.ndarray]], dict[str, pd.DataFrame]]:
    """Minute grid + per-coin OHLC on it (NaN where missing) + the raw frames for T2."""
    conn = db.connect()
    raw: dict[str, pd.DataFrame] = {}
    for sym in PERP_SYMBOLS:
        df = db.read_candles(conn, "binance", sym, "1m")
        raw[sym] = df[["open_time", "open", "high", "low", "close"]].reset_index(drop=True)
        print(f"  loaded {sym}: {len(df):,} bars", flush=True)
    conn.close()
    t0 = min(int(d["open_time"].iloc[0]) for d in raw.values())
    t1 = max(int(d["open_time"].iloc[-1]) for d in raw.values())
    grid = np.arange(t0, t1 + M, M, dtype=np.int64)
    cols: dict[str, dict[str, np.ndarray]] = {}
    for sym, d in raw.items():
        pos = ((d["open_time"].to_numpy("int64") - t0) // M).astype(np.int64)
        cols[sym] = {}
        for k in ("open", "high", "low", "close"):
            a = np.full(len(grid), np.nan, dtype=np.float32)  # 10 coins x 3M minutes: halve memory
            a[pos] = d[k].to_numpy(np.float32)
            cols[sym][k] = a
    return grid, cols, raw


def triggers(cols: dict[str, dict[str, np.ndarray]], up: bool) -> np.ndarray:
    """(coins x minutes) bool: the coin touched its +/-2.5% rung off the previous minute's close."""
    out = []
    for c in cols.values():
        prev = np.concatenate([[np.nan], c["close"][:-1]])
        with np.errstate(invalid="ignore"):
            hit = c["high"] >= prev * (1 + DROP) if up else c["low"] <= prev * (1 - DROP)
        out.append(hit & ~np.isnan(prev))
    return np.array(out)


def recent_any(trig_any: np.ndarray, lo: int, hi: int) -> np.ndarray:
    """bool per minute i: trig_any is True somewhere in [i-hi, i-lo] (negative bounds = ahead)."""
    n = len(trig_any)
    cs = np.concatenate([[0], np.cumsum(trig_any.astype(np.int64))])
    i = np.arange(n)
    a, b = np.clip(i - hi, 0, n), np.clip(i - lo + 1, 0, n)
    return (cs[b] - cs[a]) > 0


# --- stats ---

def day_boot(day: np.ndarray, r: np.ndarray, rng: np.random.Generator) -> tuple[float, float]:
    """Bonferroni CI on the mean, resampling whole UTC days."""
    _, inv = np.unique(day, return_inverse=True)
    sums, cnts = np.bincount(inv, weights=r), np.bincount(inv).astype(float)
    pick = rng.integers(0, len(sums), size=(BOOT, len(sums)))
    means = sums[pick].sum(axis=1) / cnts[pick].sum(axis=1)
    return float(np.percentile(means, LO)), float(np.percentile(means, HI))


def diff_boot(day: np.ndarray, r: np.ndarray, grp: np.ndarray, rng: np.random.Generator
              ) -> tuple[float, float]:
    """Bonferroni CI on mean(r | grp) - mean(r | ~grp), resampling whole UTC days."""
    _, inv = np.unique(day, return_inverse=True)
    n = inv.max() + 1
    s1 = np.bincount(inv, weights=r * grp, minlength=n)
    c1 = np.bincount(inv, weights=grp.astype(float), minlength=n)
    s0 = np.bincount(inv, weights=r * ~grp, minlength=n)
    c0 = np.bincount(inv, weights=(~grp).astype(float), minlength=n)
    pick = rng.integers(0, n, size=(BOOT, n))
    d = s1[pick].sum(1) / c1[pick].sum(1) - s0[pick].sum(1) / c0[pick].sum(1)
    return float(np.percentile(d, LO)), float(np.percentile(d, HI))


def days_of(ms: np.ndarray) -> np.ndarray:
    return (ms // 86_400_000).astype(np.int64)


# --- T1 ---

def t1(grid, cols, trig, up: bool, rng, horizon: int = HORIZON, verbose: bool = True):
    syms = list(cols)
    any_t = trig.any(axis=0)
    quiet = ~recent_any(any_t, 1, QUIET)
    eps = np.flatnonzero(any_t & quiet)
    eps = eps[eps + horizon < len(grid)]
    rows = []
    for t in eps:
        btc_led = bool(trig[0, t])
        for k, s in enumerate(syms):
            if trig[k, t]:
                continue
            o, c = cols[s]["open"][t + 1], cols[s]["close"][t + horizon]
            if np.isnan(o) or np.isnan(c) or np.isnan(cols[s]["close"][t]):
                continue
            g = (c / o - 1.0) * (1 if up else -1)
            rows.append((grid[t], g - HL_RT_TAKER, btc_led))
    if not rows:
        return None
    ms = np.array([r[0] for r in rows], dtype=np.int64)
    net = np.array([r[1] for r in rows])
    btc = np.array([r[2] for r in rows])
    out = {"n_eps": len(eps), "n": len(net), "mean": float(net.mean()),
           "ms": ms, "net": net, "btc": btc}
    if verbose:
        out["ci"] = day_boot(days_of(ms), net, rng)
        mid = np.median(grid[eps])
        out["h1"], out["h2"] = float(net[ms < mid].mean()), float(net[ms >= mid].mean())
    return out


# --- T2 (F8 replay) ---

def f8_fills(raw: pd.DataFrame) -> list[tuple[int, float]]:
    """F8's frozen rule on one coin's raw rows, as in f8_cascade_ladder_proxy._events.

    Returns (fill ms, net) per event."""
    ot = raw["open_time"].to_numpy("int64")
    low, high, close = (raw[k].to_numpy(float) for k in ("low", "high", "close"))
    prior = np.roll(close, 1)
    cand = np.flatnonzero(low <= prior * (1.0 - DROP))
    out, n, nxt = [], len(raw), 1
    for i in cand:
        if i < nxt or i == 0:
            continue
        rung = prior[i] * (1.0 - DROP)
        end = min(i + HOLD, n - 1)
        w = high[i + 1: end + 1]
        target = rung * (1.0 + TARGET)
        exit_px = target if (w >= target).any() else close[end]
        out.append((int(ot[i]), exit_px / rung - 1.0 - RT_COST))
        nxt = end + 1
    return out


def main() -> None:
    rng = np.random.default_rng(SEED)
    print("C1 cross-coin cascade contagion — Binance USDT-M perp 1m, F8's 10 coins\n")
    grid, cols, raw = load()
    t0 = grid[0]
    print(f"  grid {pd.Timestamp(grid[0], unit='ms')} -> {pd.Timestamp(grid[-1], unit='ms')} "
          f"({len(grid):,} minutes)\n")
    syms = list(cols)
    trig_dn, trig_up = triggers(cols, up=False), triggers(cols, up=True)

    # --- diagnostic: does a cascade raise the odds of another coin cascading? ---
    print("DIAGNOSTIC — P(laggard triggers within 15m after an episode) vs P(any 15m window)")
    for name, trig in (("down", trig_dn), ("up", trig_up)):
        any_t = trig.any(axis=0)
        eps = np.flatnonzero(any_t & ~recent_any(any_t, 1, QUIET))
        eps = eps[eps + HORIZON < len(grid)]
        hits = tot = 0
        base = []
        for k in range(len(syms)):
            fut = recent_any(trig[k], -HORIZON, -1)  # trig in [i+1, i+15]
            lag = ~trig[k, eps]
            hits += int(fut[eps][lag].sum())
            tot += int(lag.sum())
            base.append(fut[~np.isnan(cols[syms[k]]["close"])].mean())
        print(f"  {name:>4}: episodes {len(eps):,} | after-episode {hits / tot:.1%} "
              f"({hits}/{tot}) | any window {np.mean(base):.3%} "
              f"-> lift x{hits / tot / np.mean(base):.0f}")

    # --- T1 ---
    verdicts = {}
    for name, trig, up in (("T1-DOWN", trig_dn, False), ("T1-UP", trig_up, True)):
        r = t1(grid, cols, trig, up, rng)
        print(f"\n{name} — {'long' if up else 'short'} laggards, open t+1 -> close t+{HORIZON}, "
              f"HL taker RT {HL_RT_TAKER:.2%}")
        print(f"  episodes {r['n_eps']:,}, laggard-events {r['n']:,}")
        print(f"  mean net {r['mean']:+.3%}/event (gross {r['mean'] + HL_RT_TAKER:+.3%}), "
              f"98.33% CI [{r['ci'][0]:+.3%}, {r['ci'][1]:+.3%}]")
        print(f"  halves: {r['h1']:+.3%} / {r['h2']:+.3%}")
        b = r["btc"]
        print(f"  BTC-led {r['net'][b].mean():+.3%} (N {b.sum():,}) | "
              f"alt-led {r['net'][~b].mean():+.3%} (N {(~b).sum():,})")
        hz = []
        for h in (1, 5, 30, 60):
            q = t1(grid, cols, trig, up, rng, horizon=h, verbose=False)
            hz.append(f"{h}m {q['mean']:+.3%}")
        print("  horizons (net): " + ", ".join(hz))
        passed = (r["n"] >= MIN_N_T1 and r["mean"] >= T1_MIN and r["ci"][0] > 0
                  and r["h1"] > 0 and r["h2"] > 0)
        verdicts[name] = passed
        print(f"  -> {name} {'PASS' if passed else 'FAIL'}")

    # --- T2 ---
    print("\nT2 — F8 fills after another coin's cascade vs isolated fills (F8 frozen economics)")
    any_other_prior = {}
    for k, s in enumerate(syms):
        others = np.delete(trig_dn, k, axis=0).any(axis=0)
        any_other_prior[s] = (recent_any(others, 1, LEAD_WINDOW), others)
    fills = []
    for s in syms:
        prior, same = any_other_prior[s]
        for ms, net in f8_fills(raw[s]):
            i = int((ms - t0) // M)
            led = bool(prior[i])
            iso = not led and not bool(same[i])
            fills.append((ms, net, led, iso))
    ms = np.array([f[0] for f in fills], dtype=np.int64)
    net = np.array([f[1] for f in fills])
    led = np.array([f[2] for f in fills])
    iso = np.array([f[3] for f in fills])
    sim = ~led & ~iso
    print(f"  self-check: N {len(net):,}, mean {net.mean():+.3%} (F8 perp log: N 2261, +0.509%)")
    for lbl, m in (("LED", led), ("ISOLATED", iso), ("same-minute only", sim)):
        print(f"  {lbl:>16}: N {m.sum():>5,}  mean {net[m].mean():+.3%}  "
              f"TP-ish share {(net[m] > 0).mean():.1%}")
    keep = led | iso
    lo, hi = diff_boot(days_of(ms[keep]), net[keep], led[keep], rng)
    diff = net[led].mean() - net[iso].mean()
    passed = led.sum() >= MIN_N_T2 and iso.sum() >= MIN_N_T2 and (lo > 0 or hi < 0)
    verdicts["T2"] = passed
    print(f"  LED - ISOLATED {diff:+.3%}, 98.33% CI [{lo:+.3%}, {hi:+.3%}]  "
          f"-> T2 {'PASS' if passed else 'FAIL'}")

    print("\nC1 VERDICT: " + " | ".join(f"{k} {'PASS' if v else 'FAIL'}"
                                       for k, v in verdicts.items()))


if __name__ == "__main__":
    main()
