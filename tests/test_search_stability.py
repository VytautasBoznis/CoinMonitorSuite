import math

import pandas as pd
import pytest

from coinmon.search.ga import GAConfig
from coinmon.search.genome import Genome
from coinmon.search.graduation import GraduationReport
from coinmon.search.runner import FitnessParams
from coinmon.search.stability import (
    StabilityReport,
    param_drift,
    run_stability,
    window_bounds,
)


def _read(symbol):
    # Same per-symbol oscillation over a mild uptrend as the runner tests, but longer so each
    # rolling window still spans the folds + holdout after being sliced.
    phase = sum(ord(c) for c in symbol) % 7
    n = 400
    closes = [100.0 + 20.0 * math.sin(i / 6.0 + phase) + 0.05 * i for i in range(n)]
    return pd.DataFrame(
        {
            "open_time": range(n),
            "open": closes,
            "high": [c + 1 for c in closes],
            "low": [c - 1 for c in closes],
            "close": closes,
            "volume": [1.0] * n,
        }
    )


_FP = FitnessParams(folds=3, embargo_bars=2, min_trades=0)
_CFG = GAConfig(population=6, generations=3, seed=0)


def test_window_bounds_rolls_overlapping_windows():
    # 60% windows advancing 20% tile [0, 1] into three overlapping panes.
    assert window_bounds(0.6, 0.2) == [(0.0, 0.6), (0.2, 0.8), (0.4, 1.0)]


def test_window_bounds_caps_at_n_windows():
    assert window_bounds(0.5, 0.1, n_windows=2) == [(0.0, 0.5), (0.1, 0.6)]


def test_window_bounds_rejects_bad_geometry():
    with pytest.raises(ValueError):
        window_bounds(1.5, 0.2)  # window wider than the series
    with pytest.raises(ValueError):
        window_bounds(0.5, 0.6)  # step wider than the window -> a gap, not a roll


def test_param_drift_is_zero_for_identical_and_none_across_families():
    a = Genome("rsi_meanreversion", "BTC/USDC", {"period": 14, "oversold": 30, "exit_level": 60})
    same = Genome("rsi_meanreversion", "BTC/USDC", dict(a.params))
    assert param_drift(a, same) == 0.0
    other_family = Genome("ema_crossover", "BTC/USDC", {"fast": 10, "slow": 30})
    assert param_drift(a, other_family) is None


def test_param_drift_normalizes_by_range():
    # period spans [2, 40] (range 38); a 19-step move is exactly half its range, the others equal.
    a = Genome("rsi_meanreversion", "BTC/USDC", {"period": 2, "oversold": 30, "exit_level": 60})
    b = Genome("rsi_meanreversion", "BTC/USDC", {"period": 21, "oversold": 30, "exit_level": 60})
    assert param_drift(a, b) == pytest.approx(0.5 / 3)  # one of three params moved half its range


def _run():
    return run_stability(
        _read,
        taker_fee=0.0,
        config=_CFG,
        holdout_fraction=0.2,
        window_size=0.6,
        step=0.2,
        fitness_params=_FP,
        fragility_runs=10,
    )


def test_run_stability_searches_each_window_and_links_them_forward():
    report = _run()
    assert isinstance(report, StabilityReport)
    # Three rolling windows over the series, each a full graduated search.
    assert [(w.lo, w.hi) for w in report.windows] == [(0.0, 0.6), (0.2, 0.8), (0.4, 1.0)]
    assert all(w.report.graduation is not None for w in report.windows)
    # Forward persistence links consecutive windows: N windows -> N-1 carry-forward steps.
    assert len(report.forward) == len(report.windows) - 1
    for step in report.forward:
        assert step.to_index == step.from_index + 1
        assert isinstance(step.graduation, GraduationReport)
        # The carried-forward genome is the previous window's winner, judged on the next window.
        assert step.graduation.genome == report.windows[step.from_index].winner


def test_run_stability_is_deterministic_for_a_seed():
    a, b = _run(), _run()
    assert [w.winner for w in a.windows] == [w.winner for w in b.windows]
    assert [s.persisted for s in a.forward] == [s.persisted for s in b.forward]


def test_run_stability_summary_reports_both_metrics():
    out = _run().summary()
    assert "selection agreement across windows:" in out
    assert "forward persistence" in out


def test_run_stability_rejects_bad_holdout():
    with pytest.raises(ValueError):
        run_stability(_read, taker_fee=0.0, config=_CFG, holdout_fraction=0.0)
