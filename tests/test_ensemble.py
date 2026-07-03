import pandas as pd

from coinmon.backtest.result import TradeRecord
from coinmon.search.ensemble import (
    certify_ensemble,
    daily_pnl,
    pick_decorrelated_members,
)
from coinmon.search.genome import Genome

_MS_PER_DAY = 86_400_000


def _oscillating_frame(n=160):
    """A zig-zag series an rsi(2) mean-reversion genome actually trades on, timestamped one bar per
    day so the pooled ledger spans real calendar days (daily_pnl + regime buckets need that)."""
    closes = [100 + (8 if i % 2 else -8) for i in range(n)]
    return pd.DataFrame(
        {
            "open_time": [i * _MS_PER_DAY for i in range(n)],
            "open": closes,
            "high": [c + 1 for c in closes],
            "low": [c - 1 for c in closes],
            "close": closes,
            "volume": [1.0] * n,
        }
    )


# --- daily_pnl ---

def test_daily_pnl_buckets_by_exit_day_and_sums():
    day0 = 5 * _MS_PER_DAY
    trades = [
        TradeRecord(entry_time=0, exit_time=day0, direction=1, net_return_pct=0.01),
        TradeRecord(entry_time=0, exit_time=day0 + 100, direction=1, net_return_pct=0.02),  # day 5
        TradeRecord(entry_time=0, exit_time=6 * _MS_PER_DAY, direction=1, net_return_pct=-0.01),
    ]
    series = daily_pnl(trades)
    assert list(series.index) == [5, 6]
    assert series.loc[5] == 0.03
    assert series.loc[6] == -0.01


def test_daily_pnl_empty_is_empty():
    assert daily_pnl([]).empty


# --- decorrelated pick ---

def test_pick_keeps_best_first_and_drops_correlated():
    # members 0 and 1 have identical daily streams (|corr| = 1); 2 is anti-correlated with them.
    streams = {
        0: pd.Series({1: 1.0, 2: -1.0, 3: 1.0, 4: -1.0}),
        1: pd.Series({1: 2.0, 2: -2.0, 3: 2.0, 4: -2.0}),  # perfectly correlated with 0
        2: pd.Series({1: -1.0, 2: 1.0, 3: -1.0, 4: 1.0}),  # anti-correlated -> abs corr 1 too
    }
    # order best-first = [0, 1, 2]; 1 drops (corr with 0), 2 drops (abs corr with 0) -> just {0}
    kept = pick_decorrelated_members([0, 1, 2], lambda i: streams[i], 5, max_corr=0.7)
    assert kept == (0,)


def test_pick_keeps_decorrelated_up_to_k():
    streams = {
        0: pd.Series({1: 1.0, 2: -1.0, 3: 0.5, 4: 0.2}),
        1: pd.Series({5: 0.1, 6: 0.9, 7: -0.7, 8: 0.3}),  # different days -> no overlap
    }
    kept = pick_decorrelated_members([0, 1], lambda i: streams[i], 5, max_corr=0.7)
    assert set(kept) == {0, 1}


def test_pick_respects_k():
    streams = {i: pd.Series({1: float(i), 2: float(-i), 3: float(i * 2)}) for i in range(4)}
    kept = pick_decorrelated_members([0, 1, 2, 3], lambda i: streams[i], 2, max_corr=1.01)
    assert len(kept) == 2
    assert kept == (0, 1)  # best-first order preserved


# --- end-to-end certification ---

def _genome(pair):
    return Genome(
        family="rsi_meanreversion",
        pair=pair,
        params={"period": 2, "oversold": 40.0, "exit_level": 60.0},
    )


def test_certify_ensemble_pools_members_and_reports():
    frame = _oscillating_frame()
    universe = ["AAA/USDC", "BBB/USDC"]
    candidates = [_genome("AAA/USDC"), _genome("BBB/USDC")]
    report = certify_ensemble(
        candidates, lambda s: frame, 0.0, universe,
        k=2, eval_pairs=1, seed=0, window_size=1.0, step=1.0, holdout_fraction=0.5,
        resamples=200,
    )
    assert len(report.members) == 2
    # the pooled ensemble ledger is the union of the selected members' ledgers.
    kept_trades = sum(m.n_trades for m in report.members if m.selected)
    assert report.evidence.n_trades == kept_trades
    assert kept_trades > 0
    # nothing can CERTIFY on this tiny synthetic pool (N < 300, C4/C6 PENDING) — honest UNPROVEN.
    assert report.certificate.verdict in ("UNPROVEN", "REFUTED")


def test_certify_ensemble_drops_a_redundant_member():
    # two genomes on the SAME pair produce identical ledgers -> identical daily P&L -> one drops.
    frame = _oscillating_frame()
    universe = ["AAA/USDC"]
    candidates = [_genome("AAA/USDC"), _genome("AAA/USDC")]
    report = certify_ensemble(
        candidates, lambda s: frame, 0.0, universe,
        k=5, eval_pairs=1, seed=0, window_size=1.0, step=1.0, holdout_fraction=0.5,
        resamples=200,
    )
    assert sum(1 for m in report.members if m.selected) == 1
