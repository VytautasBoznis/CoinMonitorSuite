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
from coinmon.search.genome import FAMILIES, Genome, decode, decode_portfolio, validate
from coinmon.strategies.directional import RegimeAdaptive
from coinmon.strategies.ratio_momentum import RatioMomentum

FAMILY = "ratio_momentum"


def _params(**overrides) -> dict[str, float]:
    return {"lookback": 30, "skip": 1, "band": 0.0, **overrides}


def _genome(pair="XRP/ETH", **overrides) -> Genome:
    return Genome(FAMILY, pair, _params(**overrides))


def _candles(closes):
    n = len(closes)
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


def _run(strategy, closes):
    # Drive the strategy bar-by-bar through plain BarViews to read its raw target signal.
    targets = []
    for c in closes:
        targets.append(strategy.on_bar(BarView(Candle(0, c, c + 1, c - 1, c, 1.0))))
    return targets


# --- registration + genome contract --------------------------------------------------------


def test_family_is_registered():
    fam = FAMILIES[FAMILY]
    assert set(fam.params) == {"lookback", "skip", "band"}


def test_genome_validates_and_decodes_to_a_strategy():
    g = _genome()
    validate(g)
    assert isinstance(decode(g)(), RatioMomentum)
    assert isinstance(decode_portfolio(g)(10_000.0, 0.001), SpotPortfolio)  # long default


def test_decode_matches_handbuilt_strategy():
    closes = [float(p) for p in range(40, 20, -1)] + [float(p) for p in range(21, 45)]
    closes = (closes * 3)[:120]
    candles = _candles(closes)
    from_genome = BacktestEngine(decode(_genome())(), SpotPortfolio(10_000.0, 0.001)).run(candles)
    handbuilt = BacktestEngine(
        RatioMomentum(lookback=30, skip=1, band=0.0), SpotPortfolio(10_000.0, 0.001)
    ).run(candles)
    assert from_genome.metrics == handbuilt.metrics


def test_decode_yields_a_fresh_strategy_each_call():
    factory = decode(_genome())
    assert factory() is not factory()  # each fold/stress run needs its own stateful instance


def test_validate_rejects_out_of_range_lookback():
    with pytest.raises(ValueError):
        validate(_genome(lookback=FAMILIES[FAMILY].params["lookback"].high + 1))


# --- signal semantics + no-lookahead -------------------------------------------------------


def test_holds_flat_through_warmup():
    # The first lookback+skip+1 bars can't form the rate-of-change window -> must stay flat.
    strat = RatioMomentum(lookback=5, skip=1, band=0.0)
    targets = _run(strat, [float(100 + i) for i in range(20)])
    assert targets[: 5 + 1] == [0] * (5 + 1)  # bars before the window is full are flat


def test_long_on_rising_momentum_flat_on_falling():
    up = _run(RatioMomentum(lookback=5, skip=0, band=0.0), [float(100 + i) for i in range(20)])
    down = _run(RatioMomentum(lookback=5, skip=0, band=0.0), [float(100 - i) for i in range(20)])
    assert up[-1] == 1  # positive rate of change -> long
    assert down[-1] == 0  # negative rate of change -> flat


def test_band_gates_entry():
    # A gentle uptrend (~0.5%/bar over 5 bars ~ 2.5%) clears band=0 but not a 20% band.
    closes = [100.0 * (1.005**i) for i in range(20)]
    assert _run(RatioMomentum(lookback=5, skip=0, band=0.0), closes)[-1] == 1
    assert _run(RatioMomentum(lookback=5, skip=0, band=0.20), closes)[-1] == 0


def test_skip_drops_the_most_recent_bars():
    # Rise for a long run, then a sharp drop at the very end. skip=0 measures across the drop and
    # flips flat; skip=3 skips the drop and measures from before it, so momentum stays positive.
    closes = [float(100 + i) for i in range(15)] + [113.0, 105.0]
    skip0 = _run(RatioMomentum(lookback=5, skip=0, band=0.0), closes)
    skip3 = _run(RatioMomentum(lookback=5, skip=3, band=0.0), closes)
    assert skip0[-1] == 0  # the recent drop drags the rate of change negative
    assert skip3[-1] == 1  # the recent drop is skipped -> momentum still positive


def test_buffer_stays_bounded():
    # O(1)/bar: the close buffer never grows past the window it needs (N1 discipline).
    strat = RatioMomentum(lookback=5, skip=1, band=0.0)
    _run(strat, [float(i) for i in range(1, 501)])
    assert len(strat._closes) == 5 + 1 + 1


# --- plugs into the full GA + fitness pipeline unchanged -----------------------------------


def test_ga_reaches_the_family():
    rng = random.Random(0)
    genomes = [random_genome(rng) for _ in range(400)]
    assert any(g.family == FAMILY for g in genomes)  # explored by default


def test_random_and_mutated_genomes_stay_valid():
    rng = random.Random(1)
    g = _genome()
    for _ in range(500):
        g = mutate(g, rng)
        validate(g)


def test_crossover_within_family_inherits_each_gene():
    rng = random.Random(2)
    a = _genome("XRP/ETH", lookback=10, skip=0, band=0.0)
    b = _genome("BTC/USDC", lookback=90, skip=8, band=0.05)
    for _ in range(200):
        child = crossover(a, b, rng)
        validate(child)
        assert child.family == FAMILY
        for name in FAMILIES[FAMILY].params:
            assert child.params[name] in {a.params[name], b.params[name]}


def test_evaluate_fitness_scores_a_genome():
    closes = [float(p) for p in range(40, 20, -1)] + [float(p) for p in range(21, 45)]
    r = evaluate_fitness(_candles((closes * 3)[:120]), decode(_genome()), taker_fee=0.0, folds=4,
                         min_trades=0)
    assert len(r.fold_returns) == 4
    assert all(math.isfinite(x) for x in r.fold_returns)


def test_adaptive_genome_wraps_regime_and_trades_a_perp():
    g = Genome(FAMILY, "XRP/ETH", _params(), direction="adaptive", leverage=2.0)
    assert isinstance(decode(g)(), RegimeAdaptive)  # momentum composes with the direction gene
    book = decode_portfolio(g)(10_000.0, 0.001)
    assert isinstance(book, PerpPortfolio)
    assert book.leverage == 2.0
