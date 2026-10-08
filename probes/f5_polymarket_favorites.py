"""F5 — POLYMARKET FAVORITE-LONGSHOT CALIBRATION: are 90-97c favorites underpriced near resolution?

Pre-registered 2026-10-08, written BEFORE any entry price was pulled. Seen before writing
(declared): Gamma market metadata (field names, counts per year: >58k closed markets with >= $50k
volume, 2025-26 dominant), one event's tags, and the NUMBER of hourly price points for 8 markets
(to learn that prices-history needs a window before closedTime). No price value was looked at.
Idea 5 of the Fable batch ([[fable-batch-10-probe-queue]]); Fable's thresholds.

THE TRADE. Buy the favorite side at 90-97c a day before scheduled resolution; collect $1 if it
wins. Pays: retail lottery preference / identity bettors overpay longshots, so favorites trade
below their true probability (the favorite-longshot bias of every betting market ever measured).

UNIVERSE + POINT-IN-TIME ENTRY (frozen):
  * Closed binary Polymarket markets (2 outcomes), volume >= $100k, feesEnabled false, scheduled
    endDate in 2022-01-01 .. 2026-09-30, final outcomePrices in [0, 1].
  * ENTRY at t_e = scheduled endDate - 24h, the only anchor known in advance (anchoring on the
    actual closedTime would be look-ahead: early resolutions are not known ahead). The market must
    be open then: startDate <= t_e < closedTime. Markets that resolved earlier are not tradable
    by this rule and drop out.
  * More markets qualify than a probe should pull, so a FIXED random subsample (seed 20261008) of
    8,000 eligible markets is priced. Price p = last CLOB price-history point (10-min fidelity) of
    outcome 0 in [t_e - 2h, t_e]; outcome 1 is priced at 1 - p. A favorite entry exists when one
    side is in [0.90, 0.97]; payout = that side's final outcomePrice.
  * CATEGORY from the market's event tags: Sports if tagged sports, else Crypto, else Politics
    (incl. elections/geopolitics tags), else Other.

THE FROZEN RULE (all five must hold; ANY miss = KILL):
  P1 SAMPLE     >= 1000 favorite entries.
  P2 SIZE       gap = mean payout - mean entry price >= +1.5 percentage points.
  P3 SIGNIFICANCE  95% bootstrap CI on the gap > 0, resampling whole EVENTS (a multi-candidate
                event's markets resolve together, so they are one observation).
  P4 BREADTH    Politics, Sports AND Crypto each have >= 100 entries and a positive gap.
  P5 REGIME     gap > 0 in >= 2 calendar years that each have >= 100 entries.

HONESTY CAVEATS (flagged before running):
  * p is the CLOB price series (a mid/last proxy), not an executable ask; buying pays roughly half
    a spread more. Fable's 1.5pp bar already budgets ~1pp for fee+spread (KILL at <= ~1pp).
  * Lockup to resolution + UMA dispute risk are real costs; the diagnostics print holding time.
  * endDate can be edited after the fact by Polymarket; an edited endDate shifts the entry.
  * Not tested here: Fable's second leg (already-decided-but-unresolved markets under 99c).
  * Venue access from the owner's jurisdiction is an execution question, not settled here.

Run:
  PYTHONPATH="src;." .venv/Scripts/python probes/f5_polymarket_favorites.py
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import requests

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
CACHE = Path("data")
MIN_VOLUME = 100_000
END_MIN, END_MAX = "2022-01-01T00:00:00Z", "2026-09-30T00:00:00Z"
ENTRY_LEAD = pd.Timedelta(hours=24)
STALE = pd.Timedelta(hours=2)
SAMPLE, SEED = 8_000, 20261008
LO, HI = 0.90, 0.97

P1_MIN_N = 1000
P2_MIN_GAP = 0.015
P4_CATS = ("Politics", "Sports", "Crypto")
P4_MIN_N = 100
P5_MIN_N = 100
BOOT = 10_000

_session = requests.Session()


def _get(url: str, params: dict | None = None) -> dict | list:
    for attempt in range(10):
        r = _session.get(url, params=params, timeout=60)
        if r.status_code == 200:
            return r.json()
        if r.status_code != 429 and r.status_code < 500:
            r.raise_for_status()
        time.sleep(min(2**attempt, 60))
    r.raise_for_status()
    raise RuntimeError("unreachable")


def _ts(s: str | float | None) -> pd.Timestamp | None:
    """Gamma timestamps, ISO or "2024-07-18 00:10:37+00"; missing ones arrive as None or NaN."""
    return pd.Timestamp(s.replace(" ", "T")).tz_convert("UTC") if isinstance(s, str) and s else None


def _markets() -> pd.DataFrame:
    path = CACHE / "f5_markets.parquet"
    if path.exists():
        return pd.read_parquet(path)
    rows, cursor = [], None
    while True:
        q = {"closed": "true", "limit": 100, "volume_num_min": MIN_VOLUME,
             "end_date_min": END_MIN, "end_date_max": END_MAX}
        if cursor:
            q["after_cursor"] = cursor
        page = _get(f"{GAMMA}/markets/keyset", q)
        for m in page["markets"]:
            outcomes = json.loads(m.get("outcomes") or "[]")
            tokens = json.loads(m.get("clobTokenIds") or "[]")
            finals = json.loads(m.get("outcomePrices") or "[]")
            if len(outcomes) != 2 or len(tokens) != 2 or len(finals) != 2 or m.get("feesEnabled"):
                continue
            rows.append({"id": m["id"], "event": str((m.get("events") or [{}])[0].get("id")),
                         "token0": tokens[0], "final0": float(finals[0]),
                         "start": m.get("startDate"), "end": m.get("endDate"),
                         "closed": m.get("closedTime"), "volume": float(m.get("volumeNum") or 0)})
        cursor = page.get("next_cursor")
        if not cursor or not page["markets"]:
            break
    df = pd.DataFrame(rows)
    CACHE.mkdir(exist_ok=True)
    df.to_parquet(path)
    return df


def _eligible(mk: pd.DataFrame) -> pd.DataFrame:
    mk = mk.copy()
    for c in ("start", "end", "closed"):
        mk[c] = mk[c].map(_ts)
    mk = mk.dropna(subset=["start", "end", "closed"])
    mk["entry"] = mk["end"] - ENTRY_LEAD
    ok = (mk["start"] <= mk["entry"]) & (mk["entry"] < mk["closed"]) & mk["final0"].between(0, 1)
    return mk[ok].reset_index(drop=True)


def _price(token: str, entry: pd.Timestamp) -> float | None:
    e = int(entry.timestamp())
    h = _get(f"{CLOB}/prices-history",
             {"market": token, "startTs": e - int(STALE.total_seconds()), "endTs": e, "fidelity": 10})
    pts = [p for p in h.get("history", []) if p["t"] <= e]
    return float(max(pts, key=lambda p: p["t"])["p"]) if pts else None


def _priced(el: pd.DataFrame) -> pd.DataFrame:
    path = CACHE / "f5_priced.parquet"
    if path.exists():
        return pd.read_parquet(path)
    sample = el.sample(n=min(SAMPLE, len(el)), random_state=SEED).reset_index(drop=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        sample["p0"] = list(pool.map(lambda r: _price(r[0], r[1]),
                                     zip(sample["token0"], sample["entry"])))
    sample.to_parquet(path)
    return sample


def _categories(events: list[str]) -> dict[str, str]:
    path = CACHE / "f5_event_cats.json"
    if path.exists():
        return json.loads(path.read_text())

    def one(eid: str) -> str:
        tags = {(t.get("label") or "").lower() for t in _get(f"{GAMMA}/events/{eid}").get("tags", [])}
        if "sports" in tags:
            return "Sports"
        if "crypto" in tags:
            return "Crypto"
        if tags & {"politics", "elections", "geopolitics", "world elections", "us election"}:
            return "Politics"
        return "Other"

    with ThreadPoolExecutor(max_workers=4) as pool:
        cats = dict(zip(events, pool.map(one, events)))
    path.write_text(json.dumps(cats))
    return cats


def _boot_ci(df: pd.DataFrame) -> tuple[float, float]:
    blocks = [(g["payout"].to_numpy(), g["price"].to_numpy()) for _, g in df.groupby("event")]
    rng = np.random.default_rng(SEED)
    gaps = np.empty(BOOT)
    for b in range(BOOT):
        pick = rng.integers(0, len(blocks), len(blocks))
        pay = np.concatenate([blocks[j][0] for j in pick])
        px = np.concatenate([blocks[j][1] for j in pick])
        gaps[b] = pay.mean() - px.mean()
    return float(np.percentile(gaps, 2.5)), float(np.percentile(gaps, 97.5))


def main() -> None:
    mk = _markets()
    el = _eligible(mk)
    pr = _priced(el)
    print(f"F5: {len(mk):,} liquid binary markets, {len(el):,} open at endDate-24h, "
          f"{len(pr):,} sampled, {pr['p0'].notna().sum():,} priced")

    pr = pr.dropna(subset=["p0"])
    fav0 = pr["p0"].between(LO, HI)
    fav1 = (1 - pr["p0"]).between(LO, HI)
    fav = pd.concat([
        pr[fav0].assign(price=pr["p0"], payout=pr["final0"]),
        pr[fav1].assign(price=1 - pr["p0"], payout=1 - pr["final0"]),
    ], ignore_index=True)
    cats = _categories(sorted(fav["event"].unique()))
    fav["cat"] = fav["event"].map(cats)
    fav["year"] = fav["entry"].map(lambda t: t.year)

    gap = fav["payout"].mean() - fav["price"].mean()
    lo, hi = _boot_ci(fav)
    print(f"\n{'=' * 74}\nFAVORITES at 90-97c, endDate-24h: N={len(fav)}, {fav['event'].nunique()} events"
          f"\n{'=' * 74}")
    print(f"  mean price {fav['price'].mean() * 100:.2f}c   win rate {fav['payout'].mean() * 100:.2f}%   "
          f"gap {gap * 100:+.2f}pp   CI [{lo * 100:+.2f}, {hi * 100:+.2f}]pp")
    by_cat = fav.groupby("cat").apply(lambda g: pd.Series(
        {"n": len(g), "gap": g["payout"].mean() - g["price"].mean()}), include_groups=False)
    by_year = fav.groupby("year").apply(lambda g: pd.Series(
        {"n": len(g), "gap": g["payout"].mean() - g["price"].mean()}), include_groups=False)
    print("  by category: " + "  ".join(f"{c} {r.gap * 100:+.2f}pp n={int(r.n)}" for c, r in by_cat.iterrows()))
    print("  by year:     " + "  ".join(f"{y} {r.gap * 100:+.2f}pp n={int(r.n)}" for y, r in by_year.iterrows()))

    p1 = len(fav) >= P1_MIN_N
    p2 = gap >= P2_MIN_GAP
    p3 = lo > 0
    p4 = all(c in by_cat.index and by_cat.loc[c, "n"] >= P4_MIN_N and by_cat.loc[c, "gap"] > 0
             for c in P4_CATS)
    p5 = int(((by_year["n"] >= P5_MIN_N) & (by_year["gap"] > 0)).sum()) >= 2
    print(f"\n  P1 N >= {P1_MIN_N}                         : {'PASS' if p1 else 'FAIL'}")
    print(f"  P2 gap >= +{P2_MIN_GAP * 100:.1f}pp                   : {'PASS' if p2 else 'FAIL'}")
    print(f"  P3 event-bootstrap CI > 0           : {'PASS' if p3 else 'FAIL'}")
    print(f"  P4 Politics/Sports/Crypto each > 0  : {'PASS' if p4 else 'FAIL'}")
    print(f"  P5 positive in >= 2 years (n>=100)  : {'PASS' if p5 else 'FAIL'}")
    print(f"\n  VERDICT: {'PASS' if all((p1, p2, p3, p4, p5)) else 'KILL'}")

    # ---- diagnostics (not the verdict)
    print("\n  diagnostics (not the verdict):")
    for a, b in ((0.90, 0.92), (0.92, 0.95), (0.95, 0.97 + 1e-9)):
        g = fav[(fav["price"] >= a) & (fav["price"] < b)]
        if len(g):
            print(f"    price [{a:.2f},{min(b, 0.97):.2f}]: n={len(g):>4}  price {g['price'].mean() * 100:.2f}c  "
                  f"win {g['payout'].mean() * 100:.2f}%  gap {(g['payout'].mean() - g['price'].mean()) * 100:+.2f}pp")
    ret = fav["payout"] / fav["price"] - 1.0
    hold = (fav["closed"] - fav["entry"]).dt.total_seconds() / 86400
    print(f"    return/trade at mid {ret.mean() * 100:+.2f}%  median hold {hold.median():.1f}d  "
          f"(mean {hold.mean():.1f}d)  losers {int((fav['payout'] < 0.5).sum())} of {len(fav)}")
    rec = fav[fav["entry"] >= fav["entry"].max() - pd.Timedelta(days=730)]
    print(f"    recent 24mo: n={len(rec)} gap {(rec['payout'].mean() - rec['price'].mean()) * 100:+.2f}pp")


if __name__ == "__main__":
    main()
