"""F6 — NEW PERP LISTING FUNDING CAPTURE, gate probe on the funding leg (Binance + Bybit).

Pre-registered 2026-10-08, written BEFORE any listing, funding or price was pulled. Idea 6 of the
Fable batch ([[fable-batch-10-probe-queue]]). Fable's thresholds; the CI and the gross-first
structure are declared here before data.

THE CLAIM. For the first ~7 days after a perp lists, funding runs chronically NEGATIVE: shorting
the listing pump is easy on the perp and no spot borrow exists, so shorts pay longs. Be the long
collecting it, hedged where a hedge leg exists.

WHAT THIS PROBE MEASURES: the FUNDING LEG ONLY, gross of any hedge. A hedge (spot short via margin
borrow, or a short perp elsewhere) can only SUBTRACT from it, so a gross fail is a clean KILL and a
gross pass licenses one next step: measuring hedge availability and cost. Never a deployment.

EVENTS. Every USDT-margined linear perpetual listed 2021-01-01 .. 2026-09-15: Binance from
`fapi/v1/exchangeInfo` (onboardDate), Bybit from `v5/market/instruments-info` (launchTime).
  t1     = the perp's FIRST funding settlement, searched within 8 days (Bybit) / 10 days
           (Binance) of listing. A Bybit pre-market perp whose funding starts later than that
           drops out, which is Fable's rule anyway: pre-market is a separate, naked bucket.
  F_e    = funding a LONG receives over settlements in [t1, t1 + 7d) = -sum(rate).
  P_e    = naked long perp price return, open of the 1h bar at t1-1h -> open of the 1h bar at
           t1+7d-1h. Reported SEPARATELY, never blended with F_e (Fable's flag): it is the
           unhedged degradation, not the trade.

THE FROZEN RULE, per venue (all four must hold on BOTH venues; ANY miss = KILL):
  L1 SAMPLE     >= 50 events.
  L2 SIZE       mean F_e >= +0.50% per event (gross; Fable's "net of hedge" bar applied before
                the hedge, which can only lower it).
  L3 HIT        F_e > 0 in >= 60% of events.
  L4 SIGNIFICANCE  95% bootstrap CI (10,000 resamples of events, seed fixed) on mean F_e > 0.

HONESTY CAVEATS (flagged before running): survivor universe — exchange metadata lists today's
perps (plus whatever delisted ones it still returns), so fully delisted listings are missing, sign
of the bias unknown; funding is per-settlement, so 1h/4h/8h intervals sum correctly; the recent
24 months are printed because the yield hurdle weights them ([[live-yield-hurdle]]).

Run:
  PYTHONPATH="src;." .venv/Scripts/python probes/f6_new_listing_funding.py
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

CACHE = Path("data/f6_listing_events.parquet")  # one file per venue: f6_listing_events_<venue>
FIRST = int(pd.Timestamp("2021-01-01", tz="UTC").timestamp() * 1000)
LAST = int(pd.Timestamp("2026-09-15", tz="UTC").timestamp() * 1000)
H, D = 3_600_000, 86_400_000
WINDOW = 7 * D

L1_MIN_N = 50
L2_MIN = 0.005
L3_MIN_HIT = 0.60
BOOT, SEED = 10_000, 20261008


def _get(url: str, params: dict) -> object:
    full = f"{url}?{urllib.parse.urlencode(params)}"
    for attempt in range(8):
        try:
            with urllib.request.urlopen(full, timeout=60) as r:
                return json.load(r)
        except (urllib.error.URLError, TimeoutError) as exc:  # 429 rate limit, blips
            if getattr(exc, "code", 429) != 429 or attempt == 7:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("unreachable")


def _event(venue: str, symbol: str, listed: int, funding: list[tuple[int, float]],
           opens: dict[int, float], fetched_to: int) -> dict | None:
    if not funding:
        return None
    funding.sort()
    t1 = funding[0][0] // H * H  # settlements land a few ms after the hour
    if t1 + WINDOW > fetched_to:  # late first settlement: the window would be truncated
        return None
    f = -sum(r for t, r in funding if t1 <= t < t1 + WINDOW)
    p0, p1 = opens.get(t1 - H), opens.get(t1 + WINDOW - H)
    return {"venue": venue, "symbol": symbol, "listed": listed, "t1": t1, "F": f,
            "n_settle": sum(1 for t, _ in funding if t1 <= t < t1 + WINDOW),
            "P": p1 / p0 - 1.0 if p0 and p1 else np.nan}


# ---------------------------------------------------------------- Binance
def _binance_listings() -> list[tuple[str, int]]:
    info = _get("https://fapi.binance.com/fapi/v1/exchangeInfo", {})
    return [(s["symbol"], int(s["onboardDate"])) for s in info["symbols"]
            if s["contractType"] == "PERPETUAL" and s["quoteAsset"] == "USDT"
            and FIRST <= int(s["onboardDate"]) <= LAST]


def _binance_klines(symbol: str, listed: int) -> dict[int, float] | None:
    """None = Binance answered 400 (it no longer serves this symbol's history)."""
    try:
        k = _get("https://fapi.binance.com/fapi/v1/klines",
                 {"symbol": symbol, "interval": "1h", "startTime": listed, "limit": 400})
    except urllib.error.HTTPError as exc:
        if exc.code != 400:
            raise
        return None
    return {int(b[0]): float(b[1]) for b in k}


def _binance_events() -> list[dict]:
    listings = _binance_listings()
    print(f"  binance: {len(listings)} USDT perps listed in span")
    with ThreadPoolExecutor(max_workers=4) as pool:
        opens = list(pool.map(lambda x: _binance_klines(*x), listings))
    out = []
    unserved = sum(op is None for op in opens)
    print(f"  binance: {unserved} symbols answered 400 on klines (unserved, skipped)")
    for (symbol, listed), op in zip(listings, opens):
        if op is None:
            continue
        # fundingRate shares a 500 / 5 min / IP budget: pace it, sequentially.
        fr = _get("https://fapi.binance.com/fapi/v1/fundingRate",
                  {"symbol": symbol, "startTime": listed, "endTime": listed + 10 * D, "limit": 1000})
        time.sleep(0.6)
        ev = _event("binance", symbol, listed,
                    [(int(x["fundingTime"]), float(x["fundingRate"])) for x in fr], op,
                    listed + 10 * D)
        if ev:
            out.append(ev)
    return out


# ---------------------------------------------------------------- Bybit
def _bybit(url: str, params: dict) -> dict:
    """Bybit signals errors (incl. rate limit 10006) in an HTTP-200 body: retry those."""
    for attempt in range(8):
        body = _get(url, params)
        if body.get("retCode") == 0:
            return body["result"]
        if attempt == 7:
            raise RuntimeError(f"bybit {url} {params}: {body.get('retCode')} {body.get('retMsg')}")
        time.sleep(2**attempt)
    raise RuntimeError("unreachable")


def _bybit_listings() -> list[tuple[str, int]]:
    out, cursor = [], ""
    while True:
        res = _bybit("https://api.bybit.com/v5/market/instruments-info",
                   {"category": "linear", "limit": 1000, "cursor": cursor})
        out += [(i["symbol"], int(i["launchTime"])) for i in res["list"]
                if i["contractType"] == "LinearPerpetual" and i["quoteCoin"] == "USDT"
                and FIRST <= int(i["launchTime"]) <= LAST]
        cursor = res.get("nextPageCursor") or ""
        if not cursor:
            return out


def _bybit_one(symbol: str, listed: int) -> dict | None:
    # Bybit returns <= 200 settlements, NEWEST first: 8 days keeps 1h-interval perps (192) whole.
    fr = _bybit("https://api.bybit.com/v5/market/funding/history",
              {"category": "linear", "symbol": symbol, "startTime": listed,
               "endTime": listed + 8 * D, "limit": 200})["list"]
    funding = [(int(x["fundingRateTimestamp"]), float(x["fundingRate"])) for x in fr]
    if not funding:
        return None
    t1 = min(t for t, _ in funding) // H * H
    k = _bybit("https://api.bybit.com/v5/market/kline",
             {"category": "linear", "symbol": symbol, "interval": "60",
              "start": t1 - 2 * H, "end": t1 + WINDOW, "limit": 1000})["list"]
    return _event("bybit", symbol, listed, funding, {int(b[0]): float(b[1]) for b in k},
                  listed + 8 * D)


def _bybit_events() -> list[dict]:
    listings = _bybit_listings()
    print(f"  bybit: {len(listings)} USDT perps listed in span")
    with ThreadPoolExecutor(max_workers=4) as pool:
        return [e for e in pool.map(lambda x: _bybit_one(*x), listings) if e]


# ---------------------------------------------------------------- verdict
def _boot_ci(x: np.ndarray) -> tuple[float, float]:
    rng = np.random.default_rng(SEED)
    means = rng.choice(x, size=(BOOT, len(x)), replace=True).mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def main() -> None:
    frames = []
    for venue, pull in (("bybit", _bybit_events), ("binance", _binance_events)):
        path = CACHE.with_name(f"f6_listing_events_{venue}.parquet")
        if not path.exists():
            t0 = time.time()
            path.parent.mkdir(exist_ok=True)
            pd.DataFrame(pull()).to_parquet(path)
            print(f"  {venue} pulled in {time.time() - t0:.0f}s")
        frames.append(pd.read_parquet(path))
    ev = pd.concat(frames, ignore_index=True)
    ev["year"] = pd.to_datetime(ev["t1"], unit="ms", utc=True).dt.year

    verdicts = {}
    for venue in ("binance", "bybit"):
        v = ev[ev["venue"] == venue]
        f = v["F"].to_numpy()
        lo, hi = _boot_ci(f)
        print(f"\n{'=' * 74}\n{venue.upper()}: {len(v)} listings with funding, first settlement "
              f"{pd.Timestamp(v['t1'].min(), unit='ms').date()} -> "
              f"{pd.Timestamp(v['t1'].max(), unit='ms').date()}\n{'=' * 74}")
        print(f"  long funding received, first 7d: mean {f.mean() * 100:+.3f}%  median "
              f"{np.median(f) * 100:+.3f}%  CI [{lo * 100:+.3f}%, {hi * 100:+.3f}%]  "
              f"positive {np.mean(f > 0) * 100:.1f}%")
        print("  per year (mean F, n):  " + "  ".join(
            f"{y} {g['F'].mean() * 100:+.2f}% n={len(g)}" for y, g in v.groupby("year")))
        l1 = len(v) >= L1_MIN_N
        l2 = f.mean() >= L2_MIN
        l3 = np.mean(f > 0) >= L3_MIN_HIT
        l4 = lo > 0
        print(f"  L1 N >= {L1_MIN_N}            : {'PASS' if l1 else 'FAIL'}")
        print(f"  L2 mean >= +{L2_MIN * 100:.2f}%     : {'PASS' if l2 else 'FAIL'}")
        print(f"  L3 positive >= {L3_MIN_HIT * 100:.0f}%    : {'PASS' if l3 else 'FAIL'}")
        print(f"  L4 CI > 0              : {'PASS' if l4 else 'FAIL'}")
        verdicts[venue] = all((l1, l2, l3, l4))
        print(f"  {venue}: {'PASS' if verdicts[venue] else 'KILL'}")

        # diagnostics (not the verdict)
        cut = v["t1"].max() - 730 * D
        rec = v[v["t1"] >= cut]["F"]
        p = v["P"].dropna()
        print(f"  diag: recent 24mo n={len(rec)} mean {rec.mean() * 100:+.3f}% positive "
              f"{np.mean(rec > 0) * 100:.1f}%")
        print(f"  diag: NAKED long perp price, same window (never blended): n={len(p)} mean "
              f"{p.mean() * 100:+.2f}% median {p.median() * 100:+.2f}%  -> naked total "
              f"{(v['F'] + v['P']).mean() * 100:+.2f}%")
        print(f"  diag: top-10 listings = {v['F'].nlargest(10).sum() / v['F'].sum() * 100:.0f}% "
              f"of summed funding")

    idea = "PASS" if all(verdicts.values()) else "KILL"
    print(f"\n{'=' * 74}\nF6 VERDICT (funding leg, gross of hedge): {idea}  "
          f"({', '.join(f'{k} ' + ('PASS' if x else 'KILL') for k, x in verdicts.items())})")
    if idea == "PASS":
        print("  Licenses measuring hedge availability/cost ONLY — not a trade.")


if __name__ == "__main__":
    main()
