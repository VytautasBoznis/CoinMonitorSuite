import pandas as pd
import pytest

from coinmon.backtest.engine import BacktestEngine
from coinmon.backtest.fitness import evaluate_fitness
from coinmon.backtest.portfolio import SpotPortfolio
from coinmon.feed import CostModel
from coinmon.search.genome import FAMILIES, Genome, decode, validate
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
