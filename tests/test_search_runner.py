import math

import pandas as pd
import pytest

from coinmon.backtest.stress import MonteCarloResult
from coinmon.search.ga import GAConfig
from coinmon.search.genome import validate
from coinmon.search.runner import FitnessParams, fragility_verdict, run_search


def _read(symbol):
    # A per-symbol oscillation (different phase) over a mild uptrend, so both direct USDC pairs
    # and synthetic ratios mean-revert enough to trade. Long enough for the folds + embargo.
    phase = sum(ord(c) for c in symbol) % 7
    n = 220
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


def _empty(symbol):
    return pd.DataFrame(
        {c: [] for c in ("open_time", "open", "high", "low", "close", "volume")}
    )


_FP = FitnessParams(folds=3, embargo_bars=2, min_trades=0)
_CFG = GAConfig(population=6, generations=3, seed=0)


def test_run_search_returns_a_valid_scored_winner():
    report = run_search(_read, taker_fee=0.0, config=_CFG, fitness_params=_FP)
    validate(report.best)
    assert report.fitness.fitness != float("-inf")
    # The reported full FitnessResult must match the GA's recorded best score for that genome.
    assert report.fitness.fitness == pytest.approx(report.ga.best_fitness)
    assert len(report.ga.history) == _CFG.generations


def test_run_search_is_deterministic_for_a_seed():
    a = run_search(_read, taker_fee=0.0, config=_CFG, fitness_params=_FP)
    b = run_search(_read, taker_fee=0.0, config=_CFG, fitness_params=_FP)
    assert a.best == b.best
    assert a.fitness.fitness == b.fitness.fitness


def test_run_search_runs_fragility_gate_when_requested():
    report = run_search(
        _read, taker_fee=0.0, config=_CFG, fitness_params=_FP, fragility_runs=10
    )
    assert report.fragility is not None
    assert report.fragility.runs == 10
    assert isinstance(report.passed_fragility, bool)


def test_run_search_skips_fragility_gate_by_default():
    report = run_search(_read, taker_fee=0.0, config=_CFG, fitness_params=_FP)
    assert report.fragility is None
    assert report.passed_fragility is None
    assert report.graduation is None


def test_run_search_graduates_the_winner_on_a_holdout():
    # With a holdout the chunk-D gate runs instead of the chunk-C fragility post-filter: the GA
    # scores only the search head and the winner is graduated on the never-seen tail.
    report = run_search(
        _read,
        taker_fee=0.0,
        config=_CFG,
        fitness_params=_FP,
        fragility_runs=10,
        holdout_fraction=0.2,
    )
    assert report.fragility is None
    assert report.passed_fragility is None
    assert report.graduation is not None
    assert report.graduation.fragility.runs == 10
    assert isinstance(report.graduation.passed, bool)
    # The holdout is ~20% of the 220-bar series; the search never saw those bars.
    assert report.graduation.holdout_bars == 44


def test_run_search_raises_when_no_genome_can_be_scored():
    # Every pair resolves to an empty frame => every genome scores -inf and is discarded.
    with pytest.raises(SystemExit):
        run_search(_empty, taker_fee=0.0, config=_CFG, fitness_params=_FP)


def test_fragility_verdict_thresholds_on_fraction_positive():
    nine_up_one_down = MonteCarloResult(
        returns=[0.05] * 9 + [-0.02], benchmark_return=None
    )
    assert nine_up_one_down.fraction_positive == pytest.approx(0.9)
    assert fragility_verdict(nine_up_one_down, min_fraction_positive=0.9) is True
    assert fragility_verdict(nine_up_one_down, min_fraction_positive=0.95) is False
