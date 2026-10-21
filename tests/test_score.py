"""Scoring forward round trips against a bot's frozen backtest, and the promotion bar as written."""

from __future__ import annotations

import pandas as pd
import pytest

from coinmon.live import score, swarm
from coinmon.live.control import Trade
from coinmon.live.paper import CLOSE_GRACE_MS, MIN, PAPER
from coinmon.live.score import DAY_MS, MIN_N, YEAR_MS

T0 = int(pd.Timestamp("2026-11-01", tz="UTC").value // 1_000_000)
SIX = int(pd.Timestamp("2027-05-01", tz="UTC").value // 1_000_000)
TWELVE = int(pd.Timestamp("2027-11-01", tz="UTC").value // 1_000_000)
BASE = swarm.F8_BASELINE  # mean +0.500%/trip


def trip(at_ms: int, net: float, coin: str = "BTC", reason: str = "tp", oid: int = 0) -> Trade:
    """A closed $12 round trip filled at ``at_ms`` netting ``net`` (no fees: the price says it)."""
    return Trade(bot="test", venue=PAPER, coin=coin, entry_oid=oid or at_ms, anchor_close=None,
                 sz=0.12, fill_px=100.0, fill_ms=at_ms, entry_fee=0.0, leverage="paper",
                 liq_px=None, exit_px=100.0 * (1 + net), exit_ms=at_ms + 30 * MIN,
                 exit_fee=0.0, exit_reason=reason)


def daily(n: int, nets: tuple[float, ...], start: int = T0) -> list[Trade]:
    """One round trip a day from ``start``, cycling through ``nets``."""
    return [trip(start + d * DAY_MS, nets[d % len(nets)]) for d in range(n)]


def test_day_ci_resamples_whole_days():
    assert score.day_ci([0.01, 0.02], [1, 1]) is None  # one day: no spread to resample
    # Day 1 has three +1% trips, day 2 one -1% trip. Resampling days, a quarter of the draws are
    # day 2 twice (-1%); resampling trips, all-losers is 1 in 256 and the 2.5th pct is -0.5%.
    lo, hi = score.day_ci([0.01, 0.01, 0.01, -0.01], [1, 1, 1, 2])
    assert (lo, hi) == (pytest.approx(-0.01), pytest.approx(0.01))
    assert score.day_ci([0.01, 0.01, 0.01, -0.01], [1, 1, 1, 2]) == (lo, hi)  # seeded


def test_card_is_too_early_below_the_bar_sample_then_reads_the_ci_against_the_backtest():
    now = T0 + 70 * DAY_MS
    few = score.card(daily(MIN_N - 1, (0.004, 0.006)), T0, now, 6, BASE)
    assert few["vs_backtest"] == "too early" and few["ci"] is not None

    like = score.card(daily(60, (0.004, 0.006)), T0, now, 6, BASE)
    assert like["vs_backtest"] == "in line"
    assert like["mean"] == pytest.approx(0.005)
    assert like["yield_yr"] == pytest.approx(60 * 0.005 / 6 / (70 * DAY_MS / YEAR_MS))
    assert like["expected_n"] == pytest.approx(BASE.per_year * 70 * DAY_MS / YEAR_MS)
    assert like["net_usd"] == pytest.approx(60 * 0.005 * 12)
    assert like["tp_hit"] == 1.0

    assert score.card(daily(60, (-0.011, -0.009)), T0, now, 6, BASE)["vs_backtest"] == "below"
    assert score.card(daily(60, (0.019, 0.021)), T0, now, 6, BASE)["vs_backtest"] == "above"


def test_card_runs_from_the_first_fill_when_the_ledger_is_older_than_the_first_cycle():
    # The live bot's ledger predates started_ms (the column came later).
    trades = daily(3, (0.005,), start=T0 - 10 * DAY_MS)
    c = score.card(trades, T0, T0 + 10 * DAY_MS, 6, BASE)
    assert c["since_ms"] == T0 - 10 * DAY_MS
    nothing = score.card([], None, T0, 6, BASE)
    assert (nothing["n"], nothing["since_ms"], nothing["yield_yr"]) == (0, None, None)


def test_the_bar_is_judged_once_six_calendar_months_after_the_first_run():
    assert score.judge([], None, T0, 6) == {"status": "not started", "at_ms": None}
    good = daily(60, (0.004, 0.006))
    assert score.judge(good, T0, SIX - 1, 6) == {"status": "too early", "at_ms": SIX}

    v = score.judge(good, T0, SIX, 6)
    assert (v["status"], v["at_ms"], v["n"]) == ("pass", SIX, 60)
    assert v["yield_yr"] == pytest.approx(60 * 0.005 / 6 / ((SIX - T0) / YEAR_MS))
    # Judged once: round trips closed after the judging date never change the verdict.
    late = daily(100, (-0.02,), start=SIX + DAY_MS)
    assert score.judge(good + late, T0, SIX + 200 * DAY_MS, 6)["status"] == "pass"


def test_the_bar_fails_on_yield_or_a_ci_touching_zero():
    thin = daily(60, (0.0009, 0.0011))  # CI clear of zero, but ~2%/yr
    assert score.judge(thin, T0, SIX, 6)["status"] == "fail"
    noisy = daily(60, (0.03, -0.028))  # +0.1% mean, CI spans zero
    assert score.judge(noisy, T0, SIX, 6)["status"] == "fail"


def test_under_the_sample_at_six_months_it_gets_one_more_look_at_twelve_then_retires():
    sparse = daily(30, (0.004, 0.006), start=T0 + 10 * DAY_MS)
    assert score.judge(sparse, T0, SIX, 6) == {"status": "extended", "at_ms": TWELVE}
    v = score.judge(sparse, T0, TWELVE, 6)
    assert (v["status"], v["at_ms"], v["n"]) == ("fail", TWELVE, 30)
    later = sparse + daily(30, (0.009, 0.011), start=SIX + DAY_MS)
    assert score.judge(later, T0, TWELVE, 6)["status"] == "pass"


def test_capture_matches_the_twins_fills_to_the_live_bots_by_coin_and_candle():
    candle = T0 + 100 * MIN
    paper_stamp = candle + MIN + CLOSE_GRACE_MS  # paper fills are stamped at candle close
    twin = [trip(paper_stamp, 0.012), trip(paper_stamp, 0.012, coin="ETH", oid=2)]
    live = [
        trip(candle + 20_000, 0.008),  # the same BTC candle: caught
        trip(candle - 5 * DAY_MS, 0.012, oid=3),  # before the twin ran: not counted
        trip(candle + 20_000, 0.01, coin="SOL", oid=4),  # the twin had no SOL fill
    ]
    c = score.capture(twin, live, since_ms=T0)
    assert (c["twin"], c["caught"], c["live_only"], c["n_gap"]) == (2, 1, 1, 1)
    assert c["gap"] == pytest.approx(0.008 - 0.012)
    assert score.capture(twin, live, since_ms=None)["caught"] == 0
