import math

import pandas as pd
import pytest

from coinmon.backtest.stress import MonteCarloResult
from coinmon.search.ga import GAConfig
from coinmon.search.genome import validate
from coinmon.search.runner import (
    CandleCache,
    FitnessParams,
    SweepRow,
    discover_universe,
    fragility_verdict,
    run_search,
    summarize_sweep,
    sweep_row,
)


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


def test_run_search_parallel_matches_serial():
    # Chunk N2: fanning the per-genome fitness map across processes must yield the IDENTICAL run as
    # serial — only the pure genome->float is parallelized, never the seeded RNG stream.
    serial = run_search(_read, taker_fee=0.0, config=_CFG, fitness_params=_FP)
    parallel = run_search(_read, taker_fee=0.0, config=_CFG, fitness_params=_FP, workers=2)
    assert parallel.best == serial.best
    assert parallel.fitness.fitness == serial.fitness.fitness
    assert [h.best_fitness for h in parallel.ga.history] == [
        h.best_fitness for h in serial.ga.history
    ]


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


def test_run_search_skips_cross_pair_by_default():
    report = run_search(
        _read, taker_fee=0.0, config=_CFG, fitness_params=_FP, fragility_runs=10,
        holdout_fraction=0.2,
    )
    assert report.robustness is None


def test_run_search_classifies_cross_pair_when_winner_graduates():
    # Chunk O: with --cross-pair set, a GO winner is re-graduated on decorrelated peers and tagged;
    # a NO-GO winner has nothing to classify (robustness stays None). The classifier never changes
    # the go/no-go itself.
    report = run_search(
        _read, taker_fee=0.0, config=_CFG, fitness_params=_FP, fragility_runs=10,
        holdout_fraction=0.2, cross_pair_n=2, cross_pair_min=1,
    )
    if report.graduation.passed:
        assert report.robustness is not None
        assert len(report.robustness.verdicts) <= 2
        assert report.robustness.tier in {"golden", "specialist"}
        # The classifier overrides only the pair gene — never the winner's own pair.
        assert all(v.pair != report.best.pair for v in report.robustness.verdicts)
    else:
        assert report.robustness is None


def test_run_search_raises_when_no_genome_can_be_scored():
    # Every pair resolves to an empty frame => every genome scores -inf and is discarded.
    with pytest.raises(SystemExit):
        run_search(_empty, taker_fee=0.0, config=_CFG, fitness_params=_FP)


def test_discover_universe_expands_stored_usdc_bases():
    # Chunk N4: the universe is auto-built from the USDC legs the scraper stored for this
    # exchange/timeframe — every direct pair plus every coin/coin ratio.
    series = [
        ("bybit", "BTC/USDC", "1d"),
        ("bybit", "ETH/USDC", "1d"),
        ("bybit", "SOL/USDC", "1d"),
        ("bybit", "BTC/USDC", "1h"),  # wrong timeframe -> ignored
        ("binance", "DOGE/USDC", "1d"),  # wrong exchange -> ignored
        ("bybit", "ETH/BTC", "1d"),  # already a ratio, not a USDC leg -> ignored
    ]
    universe = discover_universe(series, exchange="bybit", quote="USDC", timeframe="1d")
    assert universe == (
        "BTC/USDC", "ETH/USDC", "SOL/USDC", "BTC/ETH", "BTC/SOL", "ETH/SOL"
    )


def test_discover_universe_raises_when_nothing_matches():
    with pytest.raises(SystemExit):
        discover_universe(
            [("bybit", "BTC/USDC", "1h")], exchange="bybit", quote="USDC", timeframe="1d"
        )


def _counting_read(symbol):
    _counting_read.calls += 1  # type: ignore[attr-defined]
    return _read(symbol)


def test_run_search_shared_cache_reads_each_pair_once_across_seeds():
    # Chunk N6: a sweep shares one CandleCache across seeds so the DB is read once per pair, not
    # once per seed. Two runs over the same 4-pair universe must reuse the cached frames.
    _counting_read.calls = 0  # type: ignore[attr-defined]
    cache = CandleCache(_counting_read)
    universe = ("BTC/USDC", "ETH/USDC", "SOL/USDC", "BNB/USDC")
    for seed in (0, 1, 2):
        run_search(
            _counting_read,
            taker_fee=0.0,
            config=GAConfig(population=6, generations=3, seed=seed, universe=universe),
            fitness_params=_FP,
            cache=cache,
        )
    # No pair is ever read twice across the three seeds: total reads <= universe size, where an
    # unshared cache would re-read pairs every seed (up to 3x).
    assert _counting_read.calls <= len(universe)  # type: ignore[attr-defined]


def test_sweep_row_flattens_a_graduated_report():
    report = run_search(
        _read, taker_fee=0.0, config=_CFG, fitness_params=_FP, fragility_runs=10,
        holdout_fraction=0.2,
    )
    row = sweep_row(7, report)
    g = report.graduation
    assert row.seed == 7
    assert row.passed == g.passed
    assert row.pair == g.genome.pair
    assert row.holdout_return == g.holdout_return


def test_sweep_row_rejects_ungraduated_report():
    report = run_search(_read, taker_fee=0.0, config=_CFG, fitness_params=_FP)
    with pytest.raises(ValueError):
        sweep_row(0, report)


def _row(seed, passed, pair, ret, tier=None):
    return SweepRow(
        seed=seed, passed=passed, family="rsi_meanreversion", pair=pair, direction="long",
        holdout_return=ret, holdout_trades=20, fragility_positive=1.0, benchmark_return=0.0,
        tier=tier,
    )


def test_summarize_sweep_counts_gos_and_distinct_pairs():
    rows = [
        _row(0, True, "BNB/ETH", 0.05),
        _row(1, False, "XRP/BTC", -0.1),
        _row(2, True, "SOL/ETH", 0.03),
    ]
    out = summarize_sweep(rows)
    assert "GO: 2/3 seeds" in out
    # Two GOs on two different pairs = the lottery signature, surfaced as distinct pairs.
    assert "2 distinct pair(s): BNB/ETH, SOL/ETH" in out
    # No --cross-pair tags => no tier line.
    assert "tiers:" not in out


def test_summarize_sweep_aggregates_cross_pair_tiers():
    # Chunk O: with --cross-pair, each GO carries a tier; the sweep counts golden vs specialist
    # across seeds (the untagged NO-GO and the GO without a tier don't pollute the count).
    rows = [
        _row(0, True, "BTC/USDC", 0.20, tier="golden"),
        _row(1, True, "BTC/USDC", 0.15, tier="specialist"),
        _row(2, True, "ETH/USDC", 0.10, tier="golden"),
        _row(3, False, "SOL/ETH", -0.05),  # NO-GO -> never tagged
    ]
    out = summarize_sweep(rows)
    assert "tiers: 2 golden, 1 specialist" in out
    assert "[GOLDEN]" in out
    assert "[SPECIALIST]" in out


def test_fragility_verdict_thresholds_on_fraction_positive():
    nine_up_one_down = MonteCarloResult(
        returns=[0.05] * 9 + [-0.02], benchmark_return=None
    )
    assert nine_up_one_down.fraction_positive == pytest.approx(0.9)
    assert fragility_verdict(nine_up_one_down, min_fraction_positive=0.9) is True
    assert fragility_verdict(nine_up_one_down, min_fraction_positive=0.95) is False
