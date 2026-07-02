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
from coinmon.strategies.donchian_breakout import DonchianBreakout

FAMILY = "donchian_breakout"


def _params(**overrides) -> dict[str, float]:
    return {"channel": 20, "atr_period": 14, "exit_mult": 3.0, **overrides}


def _genome(pair="BTC/USDC", **overrides) -> Genome:
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


def _run(strategy, bars):
    # Drive the strategy bar-by-bar. ``bars`` is a list of (high, low, close); read the target.
    targets = []
    for high, low, close in bars:
        targets.append(strategy.on_bar(BarView(Candle(0, close, high, low, close, 1.0))))
    return targets


def _hlc(closes, spread=1.0):
    return [(c + spread, c - spread, c) for c in closes]


# --- registration + genome contract --------------------------------------------------------


def test_family_is_registered():
    fam = FAMILIES[FAMILY]
    assert set(fam.params) == {"channel", "atr_period", "exit_mult"}


def test_genome_validates_and_decodes_to_a_strategy():
    g = _genome()
    validate(g)
    assert isinstance(decode(g)(), DonchianBreakout)
    assert isinstance(decode_portfolio(g)(10_000.0, 0.001), SpotPortfolio)  # long default


def test_decode_matches_handbuilt_strategy():
    closes = [float(p) for p in range(20, 60)] + [float(p) for p in range(60, 20, -1)]
    candles = _candles((closes * 3)[:120])
    from_genome = BacktestEngine(decode(_genome())(), SpotPortfolio(10_000.0, 0.001)).run(candles)
    handbuilt = BacktestEngine(
        DonchianBreakout(channel=20, atr_period=14, exit_mult=3.0), SpotPortfolio(10_000.0, 0.001)
    ).run(candles)
    assert from_genome.metrics == handbuilt.metrics


def test_decode_yields_a_fresh_strategy_each_call():
    factory = decode(_genome())
    assert factory() is not factory()  # each fold/stress run needs its own stateful instance


def test_validate_rejects_out_of_range_channel():
    with pytest.raises(ValueError):
        validate(_genome(channel=FAMILIES[FAMILY].params["channel"].high + 1))


# --- signal semantics + no-lookahead -------------------------------------------------------


def test_holds_flat_through_warmup():
    # Entry needs ``channel`` prior highs, so the first ``channel`` bars can't break out -> flat.
    strat = DonchianBreakout(channel=5, atr_period=3, exit_mult=3.0)
    targets = _run(strat, _hlc([float(100 + i) for i in range(20)]))
    assert targets[:5] == [0] * 5  # no channel yet on the first `channel` bars


def test_breaks_out_long_on_new_high():
    # Flat while ranging under the prior 5-bar high, then a fresh high triggers long.
    closes = [10.0, 11.0, 12.0, 11.0, 10.0, 11.0, 20.0]
    targets = _run(DonchianBreakout(channel=5, atr_period=3, exit_mult=3.0), _hlc(closes))
    assert targets[-1] == 1  # close 20 clears the prior 5-bar high (12+spread) -> long


def test_never_enters_without_a_breakout():
    # A pure downtrend never exceeds a prior high, so the family stays flat throughout.
    targets = _run(
        DonchianBreakout(channel=5, atr_period=3, exit_mult=3.0),
        _hlc([float(100 - i) for i in range(20)]),
    )
    assert set(targets) == {0}


def test_atr_trailing_stop_exits_on_pullback():
    # Break out long on a rally, then a deep drop trips the ATR trailing stop -> flat.
    up = [10.0, 11.0, 12.0, 11.0, 10.0, 11.0, 20.0, 21.0, 22.0]
    drop = [5.0]  # far below the peak minus a small ATR band -> stop fires
    targets = _run(DonchianBreakout(channel=5, atr_period=3, exit_mult=1.0), _hlc(up + drop))
    assert targets[-3] == 1  # long after the breakout
    assert targets[-1] == 0  # trailing stop closed it out


def test_wide_exit_mult_holds_through_the_same_pullback():
    # Same path, a much wider ATR multiple keeps the trailing stop out of reach -> stays long.
    up = [10.0, 11.0, 12.0, 11.0, 10.0, 11.0, 20.0, 21.0, 22.0]
    drop = [18.0]  # a shallow dip; a wide band tolerates it
    targets = _run(DonchianBreakout(channel=5, atr_period=3, exit_mult=6.0), _hlc(up + drop))
    assert targets[-1] == 1  # still long


def test_buffer_stays_bounded():
    # O(1)/bar: the high buffer never grows past the channel it needs (N1 discipline).
    strat = DonchianBreakout(channel=7, atr_period=3, exit_mult=3.0)
    _run(strat, _hlc([float(i) for i in range(1, 501)]))
    assert len(strat._highs) == 7


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
    a = _genome("BTC/USDC", channel=10, atr_period=5, exit_mult=1.0)
    b = _genome("ETH/USDC", channel=90, atr_period=40, exit_mult=5.0)
    for _ in range(200):
        child = crossover(a, b, rng)
        validate(child)
        assert child.family == FAMILY
        for name in FAMILIES[FAMILY].params:
            assert child.params[name] in {a.params[name], b.params[name]}


def test_evaluate_fitness_scores_a_genome():
    closes = [float(p) for p in range(20, 60)] + [float(p) for p in range(60, 20, -1)]
    r = evaluate_fitness(_candles((closes * 3)[:120]), decode(_genome()), taker_fee=0.0, folds=4,
                         min_trades=0)
    assert len(r.fold_returns) == 4
    assert all(math.isfinite(x) for x in r.fold_returns)


def test_adaptive_genome_wraps_regime_and_trades_a_perp():
    g = Genome(FAMILY, "BTC/USDC", _params(), direction="adaptive", leverage=2.0)
    assert isinstance(decode(g)(), RegimeAdaptive)  # breakout composes with the direction gene
    book = decode_portfolio(g)(10_000.0, 0.001)
    assert isinstance(book, PerpPortfolio)
    assert book.leverage == 2.0
