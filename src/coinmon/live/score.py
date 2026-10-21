"""Scoring a bot's forward round trips against its own frozen backtest.

Ranking bots by live P&L and backing the leader is best-of-N luck
([[swarm-and-cross-market-ideas]]). So each bot is scored only
against its own baseline (``swarm.Baseline``), with N, a CI and a "too early" label, and a paper
bot is promoted only by the bar written before it started (``swarm.PROMOTION``), applied here as
written.

Cascade fills cluster violently (one crash day can fill every coin at once), so the CI resamples
whole UTC days, as in every F8 probe: one crash day counts as roughly one observation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from coinmon.live.control import Trade
from coinmon.live.paper import CLOSE_GRACE_MS, MIN

DAY_MS = 86_400_000
YEAR_MS = 365.25 * DAY_MS
BOOT = 10_000
SEED = 20260731  # the F8 probes' seed
MIN_N = 50  # the bar's minimum sample; below it no CI is read as a result
BAR_YIELD = 0.05  # the bar's paper yield, per year at 1x


def day_ci(nets, days, boot: int = BOOT, seed: int = SEED) -> tuple[float, float] | None:
    """95% CI on the mean net per round trip, resampling whole UTC days (``days``: any per-trade
    day key). None with fewer than two days: one day has no spread to resample."""
    nets = np.asarray(nets, float)
    keys, inv = np.unique(np.asarray(days), return_inverse=True)
    if len(keys) < 2:
        return None
    sums = np.bincount(inv, weights=nets)
    counts = np.bincount(inv).astype(float)
    pick = np.random.default_rng(seed).integers(0, len(keys), (boot, len(keys)))
    means = sums[pick].sum(axis=1) / counts[pick].sum(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(lo), float(hi)


def net(t: Trade) -> float:
    """Net per round trip as a fraction of the entry notional, fees included."""
    return ((t.exit_px - t.fill_px) * t.sz - t.entry_fee - t.exit_fee) / (t.fill_px * t.sz)


def _record(closed: list[Trade], start_ms: int, end_ms: int, coins: int) -> dict:
    nets = [net(t) for t in closed]
    years = (end_ms - start_ms) / YEAR_MS
    return {
        "n": len(nets),
        "mean": float(np.mean(nets)) if nets else None,
        "ci": day_ci(nets, [t.fill_ms // DAY_MS for t in closed]),
        "yield_yr": sum(nets) / coins / years if nets and years > 0 else None,
    }


def card(trades: list[Trade], started_ms: int | None, now_ms: int, coins: int,
         baseline) -> dict:
    """A bot's forward record next to its backtest. The record runs from its first cycle (or its
    first fill, if the ledger is older than ``started_ms``); yield as the bar defines it, the sum
    of net / coins / years at 1x. ``vs_backtest`` stays "too early" below MIN_N round trips."""
    closed = [t for t in trades if t.exit_px is not None]
    since = min([x for x in (started_ms, *(t.fill_ms for t in trades)) if x is not None],
                default=None)
    start = now_ms if since is None else since  # None: no trades, nothing ran
    rec = _record(closed, start, now_ms, coins)
    ci, base = rec["ci"], baseline.mean
    vs = ("too early" if rec["n"] < MIN_N or ci is None else
          "below" if ci[1] < base else "above" if ci[0] > base else "in line")
    return rec | {
        "since_ms": since,
        "open": sum(t.exit_ms is None for t in trades),
        "expected_n": baseline.per_year * (now_ms - start) / YEAR_MS,
        "tp_hit": sum(t.exit_reason == "tp" for t in closed) / len(closed) if closed else None,
        "net_usd": sum(net(t) * t.fill_px * t.sz for t in closed),
        "vs_backtest": vs,
    }


def _months_after(ms: int, months: int) -> int:
    return int((pd.Timestamp(ms, unit="ms", tz="UTC") + pd.DateOffset(months=months)).value
               // 1_000_000)


def judge(trades: list[Trade], started_ms: int | None, now_ms: int, coins: int) -> dict:
    """The promotion bar as written: judged once, 6 months after the first run, on the round trips
    closed by then; if N < MIN_N then, once more at 12 months, after which a fail retires it.
    ``status``: not started | too early | extended (both carry ``at_ms``, the judging date) |
    pass | fail (with the record judged)."""
    if started_ms is None:
        return {"status": "not started", "at_ms": None}
    at = _months_after(started_ms, 6)
    if now_ms < at:
        return {"status": "too early", "at_ms": at}
    if sum(t.exit_px is not None and t.exit_ms <= at for t in trades) < MIN_N:
        at = _months_after(started_ms, 12)
        if now_ms < at:
            return {"status": "extended", "at_ms": at}
    rec = _record([t for t in trades if t.exit_px is not None and t.exit_ms <= at],
                  started_ms, at, coins)
    passed = (rec["n"] >= MIN_N and rec["ci"] is not None and rec["ci"][0] > 0
              and rec["yield_yr"] >= BAR_YIELD)
    return rec | {"status": "pass" if passed else "fail", "at_ms": at}


def capture(twin: list[Trade], live: list[Trade], since_ms: int | None) -> dict:
    """The twin's measurement: which of its fills the live bot also got (same coin, a candle at
    most one minute apart; the live bot's bid can sit a re-peg band off the twin's), what the live
    bot filled that the twin did not, and live minus paper net per round trip both closed."""
    live = sorted((t for t in live if since_ms is not None and t.fill_ms >= since_ms),
                  key=lambda t: t.fill_ms)
    pairs = []
    for p in sorted(twin, key=lambda t: t.fill_ms):
        candle = (p.fill_ms - CLOSE_GRACE_MS) // MIN * MIN - MIN  # paper stamps a fill at close
        match = next((t for t in live if t.coin == p.coin
                      and abs(t.fill_ms // MIN * MIN - candle) <= MIN), None)
        if match is not None:
            live.remove(match)
            pairs.append((p, match))
    gaps = [net(t) - net(p) for p, t in pairs if p.exit_px is not None and t.exit_px is not None]
    return {"twin": len(twin), "caught": len(pairs), "live_only": len(live),
            "gap": float(np.mean(gaps)) if gaps else None, "n_gap": len(gaps)}
