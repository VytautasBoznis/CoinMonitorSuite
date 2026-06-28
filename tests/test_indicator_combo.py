from __future__ import annotations

import math
import random

import pandas as pd
import pytest

from coinmon.backtest.engine import BacktestEngine
from coinmon.backtest.fitness import evaluate_fitness
from coinmon.backtest.portfolio import PerpPortfolio, SpotPortfolio
from coinmon.data.models import Candle
from coinmon.feed import BarView
from coinmon.search.ga import crossover, mutate, random_genome
from coinmon.search.genome import (
    COMBO_FAMILY,
    FAMILIES,
    Genome,
    decode,
    decode_portfolio,
    validate,
)
from coinmon.strategies.directional import RegimeAdaptive
from coinmon.strategies.indicator_combo import (
    INDICATOR_COUNT,
    INDICATORS,
    N_CONDITIONS,
    IndicatorCombo,
    build_combo,
    decode_conditions,
    describe_combo,
)


def _candles(n):
    # A dip-then-recover wave so oscillator conditions actually fire and produce trades.
    wave = [float(p) for p in range(40, 20, -1)] + [float(p) for p in range(21, 45)]
    closes = (wave * (n // len(wave) + 1))[:n]
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


def _combo_params(**overrides) -> dict[str, float]:
    # A valid baseline combo genome: both conditions on indicator 0 (rsi), mid period/threshold,
    # op "<", combined with AND. Override individual genes per test.
    params: dict[str, float] = {}
    for i in range(N_CONDITIONS):
        params[f"ind{i}"] = 0.0
        params[f"period{i}"] = 0.5
        params[f"op{i}"] = 0.0
        params[f"thr{i}"] = 0.5
    params["combine"] = 0.0
    return {**params, **overrides}


def _combo_genome(pair="ETH/USDC", **overrides) -> Genome:
    return Genome(COMBO_FAMILY, pair, _combo_params(**overrides))


# --- the family is registered and wired into the genome contract ---------------------------


def test_combo_family_is_registered():
    fam = FAMILIES[COMBO_FAMILY]
    assert set(fam.params) == set(_combo_params())  # schema matches the param helper
    assert fam.describe is describe_combo


def test_combo_genome_validates_and_decodes_to_a_strategy():
    g = _combo_genome()
    validate(g)  # raises if the schema/ranges are wrong
    assert isinstance(decode(g)(), IndicatorCombo)
    assert isinstance(decode_portfolio(g)(10_000.0, 0.001), SpotPortfolio)  # long default


def test_validate_rejects_out_of_range_indicator_gene():
    bad = _combo_genome(ind0=float(INDICATOR_COUNT))  # one past the last valid index
    with pytest.raises(ValueError):
        validate(bad)


def test_decode_yields_a_fresh_strategy_each_call():
    factory = decode(_combo_genome())
    assert factory() is not factory()  # each fold/stress run needs its own stateful instance


# --- the unit genotype maps onto each indicator's own ranges -------------------------------


def test_unit_genes_map_to_indicator_natural_ranges():
    rsi = INDICATORS[0]
    # period unit 0 -> min_period, unit 1 -> max_period; threshold unit 0/1 -> thr_lo/thr_hi.
    lo, _ = decode_conditions(_combo_params(period0=0.0, thr0=0.0))
    hi, _ = decode_conditions(_combo_params(period0=1.0, thr0=1.0))
    assert lo[0].period == rsi.min_period and hi[0].period == rsi.max_period
    assert lo[0].threshold == rsi.thr_lo and hi[0].threshold == rsi.thr_hi


def test_op_and_combine_genes_decode():
    conds, combine = decode_conditions(_combo_params(op0=1.0, combine=1.0))
    assert conds[0].op == ">"
    assert combine == "or"
    conds, combine = decode_conditions(_combo_params(op0=0.0, combine=0.0))
    assert conds[0].op == "<"
    assert combine == "and"


# --- the compiled strategy is correct and point-in-time ------------------------------------


def _run_combo(strategy, candles):
    # Drive the strategy bar-by-bar through plain BarViews (no engine) to read its raw signal.
    targets = []
    for row in candles.itertuples(index=False):
        view = BarView(
            Candle(row.open_time, row.open, row.high, row.low, row.close, row.volume)
        )
        targets.append(strategy.on_bar(view))
    return targets


def test_combo_and_requires_both_conditions_or_only_one():
    # AND of (rsi < 35) and (rsi < 35) is identical to a single rsi < 35 rule; OR of (rsi < 35)
    # OR (rsi > 65) fires more often. Same data, so OR must be long at least as many bars as AND.
    candles = _candles(120)
    and_rule = build_combo(_combo_params(ind0=0.0, op0=0.0, thr0=0.25, ind1=0.0, op1=0.0,
                                         thr1=0.25, combine=0.0))
    or_rule = build_combo(_combo_params(ind0=0.0, op0=0.0, thr0=0.25, ind1=0.0, op1=1.0,
                                        thr1=0.75, combine=1.0))
    and_long = sum(_run_combo(and_rule, candles))
    or_long = sum(_run_combo(or_rule, candles))
    assert or_long >= and_long
    assert or_long > 0  # the OR rule actually trades on this wave


def test_combo_holds_through_warmup():
    # With a long-period indicator the first bars are NaN; the strategy must stay flat (its initial
    # target), never emit a long off undefined indicators.
    candles = _candles(60)
    g = build_combo(_combo_params(ind0=0.0, period0=1.0, ind1=0.0, period1=1.0))  # rsi(40)
    targets = _run_combo(g, candles)
    assert targets[0] == 0  # bar 0: rsi undefined -> hold flat


def test_combo_value_normalisation_is_pair_scale_invariant():
    # The SAME relative price path scaled by 1000x must produce the SAME signal sequence, proving
    # the menu's divide-by-close / oscillator normalisation removes pair scale (the whole reason
    # cumulative-volume indicators are excluded).
    base = _candles(120)
    scaled = base.copy()
    for col in ("open", "high", "low", "close"):
        scaled[col] = base[col] * 1000.0
    g_params = _combo_params(ind0=3.0, op0=1.0, thr0=0.5, ind1=4.0, op1=1.0, thr1=0.5,
                             combine=1.0)  # macd_hist OR ema_dev (both price-normalised)
    assert _run_combo(build_combo(g_params), base) == _run_combo(build_combo(g_params), scaled)


# --- it plugs into the full GA + fitness pipeline unchanged --------------------------------


def test_ga_reaches_the_combo_family():
    rng = random.Random(0)
    genomes = [random_genome(rng) for _ in range(400)]
    assert any(g.family == COMBO_FAMILY for g in genomes)  # explored by default


def test_random_and_mutated_combo_genomes_stay_valid():
    rng = random.Random(1)
    g = _combo_genome()
    for _ in range(500):
        g = mutate(g, rng)
        validate(g)


def test_crossover_within_combo_family_inherits_each_gene():
    rng = random.Random(2)
    a = _combo_genome("ETH/USDC", ind0=0.0, combine=0.0)
    b = _combo_genome("BTC/USDC", ind0=5.0, combine=1.0)
    for _ in range(200):
        child = crossover(a, b, rng)
        validate(child)
        assert child.family == COMBO_FAMILY
        for name in FAMILIES[COMBO_FAMILY].params:
            assert child.params[name] in {a.params[name], b.params[name]}


def test_evaluate_fitness_scores_a_combo_genome():
    g = _combo_genome("ETH/USDC", op0=0.0, thr0=0.3, op1=1.0, thr1=0.7, combine=1.0)
    r = evaluate_fitness(_candles(120), decode(g), taker_fee=0.0, folds=4, min_trades=0)
    assert len(r.fold_returns) == 4
    assert all(math.isfinite(x) for x in r.fold_returns)


def test_adaptive_combo_wraps_regime_and_trades_a_perp():
    g = _combo_genome("ETH/USDC")
    g = Genome(g.family, g.pair, g.params, direction="adaptive", leverage=2.0)
    assert isinstance(decode(g)(), RegimeAdaptive)  # combo composes with the direction gene
    book = decode_portfolio(g)(10_000.0, 0.001)
    assert isinstance(book, PerpPortfolio)
    assert book.leverage == 2.0


# --- the winner's rule is watchable --------------------------------------------------------


def test_describe_combo_is_readable():
    text = describe_combo(_combo_params(ind0=0.0, op0=1.0, thr0=1.0, ind1=4.0, op1=0.0, thr1=0.0,
                                        combine=1.0))
    assert "rsi" in text and "ema_dev" in text
    assert ">" in text and "<" in text
    assert " OR " in text


def test_engine_runs_a_combo_genome_end_to_end():
    # The decoded combo strategy runs through the real engine like any other strategy.
    g = _combo_genome("ETH/USDC", op0=0.0, thr0=0.3, op1=1.0, thr1=0.7, combine=1.0)
    result = BacktestEngine(decode(g)(), SpotPortfolio(10_000.0, 0.001)).run(_candles(120))
    assert "total_return" in result.metrics
