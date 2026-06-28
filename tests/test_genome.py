import pandas as pd
import pytest

from coinmon.backtest.engine import BacktestEngine
from coinmon.backtest.fitness import evaluate_fitness
from coinmon.backtest.portfolio import PerpPortfolio, SpotPortfolio
from coinmon.feed import CostModel
from coinmon.search.genome import FAMILIES, Genome, decode, decode_portfolio, validate
from coinmon.strategies.directional import RegimeAdaptive
from coinmon.strategies.ema_crossover import EMACrossover
from coinmon.strategies.rsi_meanreversion import RSIMeanReversion


def _candles(n):
    # A dip-then-recover wave repeated, so RSI and EMA strategies both produce real trades.
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


def _metrics(strategy, candles):
    return BacktestEngine(strategy, SpotPortfolio(10_000.0, 0.001)).run(candles).metrics


def _rsi_genome():
    return Genome(
        "rsi_meanreversion", "XRP/ETH", {"period": 14, "oversold": 30.0, "exit_level": 50.0}
    )


def _ema_genome():
    return Genome("ema_crossover", "ETH/USDC", {"fast": 12, "slow": 26})


def test_decode_rsi_genome_matches_handbuilt_strategy():
    candles = _candles(96)
    from_genome = _metrics(decode(_rsi_genome())(), candles)
    handbuilt = _metrics(RSIMeanReversion(period=14, oversold=30.0, exit_level=50.0), candles)
    assert from_genome == handbuilt


def test_decode_ema_genome_matches_handbuilt_strategy():
    candles = _candles(96)
    from_genome = _metrics(decode(_ema_genome())(), candles)
    handbuilt = _metrics(EMACrossover(CostModel.from_settings(), fast=12, slow=26), candles)
    assert from_genome == handbuilt


def test_decode_yields_a_fresh_strategy_each_call():
    factory = decode(_rsi_genome())
    assert factory() is not factory()  # each fold/stress run needs its own stateful instance


def test_evaluate_fitness_scores_a_genome():
    # The whole point of decode: a genome plugs straight into the fitness rig unchanged.
    genome = Genome(
        "rsi_meanreversion", "XRP/ETH", {"period": 2, "oversold": 40.0, "exit_level": 60.0}
    )
    r = evaluate_fitness(_candles(96), decode(genome), taker_fee=0.0, folds=4, min_trades=0)
    assert len(r.fold_returns) == 4


def test_validate_rejects_unknown_family():
    with pytest.raises(ValueError):
        validate(Genome("nope", "ETH/BTC", {}))


def test_validate_rejects_wrong_param_set():
    with pytest.raises(ValueError):
        validate(Genome("rsi_meanreversion", "ETH/BTC", {"period": 14}))


def test_validate_rejects_out_of_range_param():
    spec = FAMILIES["rsi_meanreversion"].params["period"]
    bad = Genome(
        "rsi_meanreversion", "ETH/BTC",
        {"period": spec.high + 1, "oversold": 30.0, "exit_level": 50.0},
    )
    with pytest.raises(ValueError):
        validate(bad)


def test_validate_rejects_malformed_pair():
    with pytest.raises(ValueError):
        validate(Genome("ema_crossover", "ETHBTC", {"fast": 12, "slow": 26}))


def test_decode_validates_before_building():
    bad = Genome(
        "rsi_meanreversion", "ETH/BTC", {"period": 999, "oversold": 30.0, "exit_level": 50.0}
    )
    with pytest.raises(ValueError):
        decode(bad)


# --- direction is a regime-adaptive gene ---------------------------------------------------


def test_genome_defaults_to_long_spot():
    # A genome built the chunk-B way (no direction genes) is still long/flat spot — backward compat.
    g = _rsi_genome()
    assert g.direction == "long"
    assert g.leverage == 1.0
    assert isinstance(decode_portfolio(g)(10_000.0, 0.001), SpotPortfolio)
    assert not isinstance(decode(g)(), RegimeAdaptive)


def test_adaptive_genome_decodes_to_regime_wrapped_strategy_and_perp_book():
    g = Genome(
        "rsi_meanreversion", "XRP/ETH", {"period": 14, "oversold": 30.0, "exit_level": 50.0},
        direction="adaptive", leverage=3.0,
    )
    assert isinstance(decode(g)(), RegimeAdaptive)  # direction follows the current-bar regime
    book = decode_portfolio(g)(10_000.0, 0.001)
    assert isinstance(book, PerpPortfolio)
    assert book.leverage == 3.0


def test_validate_rejects_out_of_range_leverage():
    bad = Genome(
        "rsi_meanreversion", "ETH/BTC", {"period": 14, "oversold": 30.0, "exit_level": 50.0},
        direction="adaptive", leverage=99.0,
    )
    with pytest.raises(ValueError):
        validate(bad)


def test_validate_rejects_unknown_direction():
    bad = Genome(
        "rsi_meanreversion", "ETH/BTC", {"period": 14, "oversold": 30.0, "exit_level": 50.0},
        direction="sideways",
    )
    with pytest.raises(ValueError):
        validate(bad)


def test_validate_rejects_out_of_range_trend_period():
    bad = Genome(
        "rsi_meanreversion", "ETH/BTC", {"period": 14, "oversold": 30.0, "exit_level": 50.0},
        direction="adaptive", trend_period=5.0,
    )
    with pytest.raises(ValueError):
        validate(bad)


# --- chunk L Part A: the intrabar stop is a gene -------------------------------------------


def test_genome_defaults_to_no_stop():
    # A genome built without the stop gene runs unbraked (chunk-B/K2 behavior unchanged).
    g = _rsi_genome()
    assert g.stop_pct is None
    validate(g)  # None is a valid, first-class "no stop"


def test_validate_accepts_an_in_range_stop():
    g = Genome(
        "rsi_meanreversion", "XRP/ETH", {"period": 14, "oversold": 30.0, "exit_level": 50.0},
        stop_pct=0.10,
    )
    validate(g)


def test_validate_rejects_out_of_range_stop():
    bad = Genome(
        "rsi_meanreversion", "ETH/BTC", {"period": 14, "oversold": 30.0, "exit_level": 50.0},
        stop_pct=0.99,
    )
    with pytest.raises(ValueError):
        validate(bad)


def test_evaluate_fitness_threads_the_stop_through_the_fold_loop():
    # A leveraged adaptive genome buys the dip into a steady decline and liquidates unbraked; a 10%
    # stop must change the fold outcome — proof stop_pct reaches the engine inside the OOS rig, not
    # just the bare engine.
    closes = [float(100 - i) for i in range(80)]
    candles = pd.DataFrame(
        {
            "open_time": range(80),
            "open": closes,
            "high": [c + 1 for c in closes],
            "low": [c - 1 for c in closes],
            "close": closes,
            "volume": [1.0] * 80,
        }
    )
    g = Genome(
        "rsi_meanreversion", "XRP/ETH", {"period": 5, "oversold": 30.0, "exit_level": 55.0},
        direction="adaptive", leverage=3.0,
    )
    unbraked = evaluate_fitness(
        candles, decode(g), taker_fee=0.0, make_portfolio=decode_portfolio(g),
        folds=2, min_trades=0,
    )
    braked = evaluate_fitness(
        candles, decode(g), taker_fee=0.0, make_portfolio=decode_portfolio(g),
        stop_pct=0.10, folds=2, min_trades=0,
    )
    assert braked.fold_returns != unbraked.fold_returns


def test_evaluate_fitness_uses_the_genome_portfolio_factory():
    # A leveraged adaptive genome on a falling series must score differently from the same genome
    # left on the default spot book: proof the portfolio factory actually reaches the fold loop.
    closes = [float(100 - i) for i in range(80)]
    candles = pd.DataFrame(
        {
            "open_time": range(80),
            "open": closes,
            "high": [c + 1 for c in closes],
            "low": [c - 1 for c in closes],
            "close": closes,
            "volume": [1.0] * 80,
        }
    )
    g = Genome(
        "rsi_meanreversion", "XRP/ETH", {"period": 5, "oversold": 30.0, "exit_level": 55.0},
        direction="adaptive", leverage=2.0,
    )
    spot = evaluate_fitness(candles, decode(g), taker_fee=0.0, folds=2, min_trades=0)
    perp = evaluate_fitness(
        candles, decode(g), taker_fee=0.0, make_portfolio=decode_portfolio(g),
        folds=2, min_trades=0,
    )
    assert perp.fold_returns != spot.fold_returns
