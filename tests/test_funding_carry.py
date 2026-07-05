import random

import pandas as pd

from coinmon.backtest.engine import BacktestEngine
from coinmon.backtest.portfolio import CarryPortfolio, SpotPortfolio
from coinmon.data.models import Candle
from coinmon.feed import BarView
from coinmon.search.ga import crossover, mutate, random_genome
from coinmon.search.genome import (
    FAMILIES,
    Genome,
    decode,
    decode_portfolio,
    decode_stop,
    validate,
)
from coinmon.strategies.funding_carry import FundingCarry

FAMILY = "funding_carry"


def _params(**overrides) -> dict[str, float]:
    return {"window": 60, "threshold": 0.0, **overrides}


def _genome(pair="BTC/USDC", **overrides) -> Genome:
    fields = {"direction": "long", "leverage": 1.0, "trend_period": 50.0, "stop_pct": None}
    params = _params(**{k: overrides.pop(k) for k in list(overrides) if k in _params()})
    fields.update(overrides)
    return Genome(FAMILY, pair, params, **fields)


def _view(rate):
    features = {} if rate is None else {"funding_rate": rate}
    return BarView(Candle(0, 100.0, 101.0, 99.0, 100.0, 1.0), features=features)


def _run(strat, rates):
    return [strat.on_bar(_view(r)) for r in rates]


def _candles(n):
    return pd.DataFrame(
        {
            "open_time": range(n),
            "open": [100.0] * n,
            "high": [101.0] * n,
            "low": [99.0] * n,
            "close": [100.0] * n,
            "volume": [1.0] * n,
        }
    )


# --- registration + genome/portfolio/stop seam ---------------------------------------------


def test_family_is_registered_as_market_neutral():
    fam = FAMILIES[FAMILY]
    assert set(fam.params) == {"window", "threshold"}
    assert fam.portfolio is not None  # brings its own CarryPortfolio (the seam)


def test_genome_decodes_to_carry_strategy_and_carry_book():
    g = _genome()
    validate(g)
    assert isinstance(decode(g)(), FundingCarry)
    assert isinstance(decode_portfolio(g)(10_000.0, 0.001), CarryPortfolio)


def test_direction_gene_is_inert_carry_is_never_regime_wrapped():
    # A market-neutral family has no directional side, so decode must NOT wrap it in RegimeAdaptive
    # and must keep the CarryPortfolio even when the direction gene says "adaptive".
    g = _genome(direction="adaptive", leverage=3.0)
    assert isinstance(decode(g)(), FundingCarry)
    assert isinstance(decode_portfolio(g)(10_000.0, 0.001), CarryPortfolio)


def test_stop_gene_is_disabled_for_carry():
    # A hedged carry has no price side to stop out; a price stop would tear the hedge apart.
    assert decode_stop(_genome(stop_pct=0.1)) is None


def test_decode_stop_passes_through_for_price_families():
    g = Genome(
        "rsi_meanreversion",
        "BTC/USDC",
        {"period": 14, "oversold": 30.0, "exit_level": 70.0},
        stop_pct=0.1,
    )
    assert decode_stop(g) == 0.1  # the seam only nulls the stop for market-neutral families


def test_decode_yields_a_fresh_strategy_each_call():
    factory = decode(_genome())
    assert factory() is not factory()


# --- signal semantics ----------------------------------------------------------------------


def test_no_funding_feature_stays_flat():
    # On a pair/run with no funding (a ratio, or a funding=None backtest) the feature is absent.
    assert _run(FundingCarry(window=3, threshold=0.0), [None] * 10) == [0] * 10


def test_holds_flat_through_warmup():
    # Until the rolling window is full there is no smoothed mean to gate on yet.
    targets = _run(FundingCarry(window=5, threshold=0.0), [0.001] * 8)
    assert targets[:4] == [0, 0, 0, 0]
    assert targets[4] == 1  # first full window, mean 0.001 > 0 -> hedge on


def test_holds_through_a_single_dip_exits_when_regime_turns():
    # The fee-efficiency fix (2026-07-05): smoothing the funding rides out a single negative bar
    # instead of un-hedging (and paying to re-hedge), and exits only when the smoothed mean turns
    # non-positive. window=3, threshold=0:
    #   bar2 full window [.001,.001,.001] mean +0.001 -> 1
    #   bar3 window [.001,.001,-.001] mean +0.00033 (still positive) -> HOLD (1), not a toggle
    #   bar4 window [.001,-.001,0.0]   mean  0.0 (not > 0)            -> flat (0)
    targets = _run(FundingCarry(window=3, threshold=0.0), [0.001, 0.001, 0.001, -0.001, 0.0])
    assert targets == [0, 0, 1, 1, 0]


def test_threshold_gates_on_smoothed_mean():
    # A positive threshold only harvests when the smoothed premium is meaningfully rich.
    rich = FundingCarry(window=4, threshold=0.0015)
    assert _run(rich, [0.001, 0.002, 0.003, 0.004])[-1] == 1  # mean 0.0025 > 0.0015
    thin = FundingCarry(window=4, threshold=0.0015)
    assert _run(thin, [0.0005, 0.001, 0.0005, 0.001])[-1] == 0  # mean 0.00075 < 0.0015


def test_buffer_stays_bounded():
    strat = FundingCarry(window=5, threshold=0.0)
    _run(strat, [0.001] * 500)
    assert len(strat._rates) == 5


# --- plugs into the GA unchanged -----------------------------------------------------------


def test_ga_reaches_the_family():
    rng = random.Random(0)
    genomes = [random_genome(rng) for _ in range(400)]
    assert any(g.family == FAMILY for g in genomes)


def test_random_and_mutated_genomes_stay_valid():
    rng = random.Random(1)
    g = _genome()
    for _ in range(500):
        g = mutate(g, rng)
        validate(g)


def test_crossover_within_family_inherits_each_gene():
    rng = random.Random(2)
    a = _genome("BTC/USDC", window=30, threshold=0.0001)
    b = _genome("ETH/USDC", window=150, threshold=0.0004)
    for _ in range(200):
        child = crossover(a, b, rng)
        validate(child)
        if child.family == FAMILY:
            for name in FAMILIES[FAMILY].params:
                assert child.params[name] in {a.params[name], b.params[name]}


# --- end-to-end through the engine with a real funding series ------------------------------


def test_engine_harvests_the_carry_premium():
    # Price is flat (the hedge is market-neutral anyway); funding is richly positive well past the
    # warmup so the held hedge collects it, then turns negative long enough for the smoothed mean to
    # drop non-positive, so the hedge closes and books a round-trip.
    funding = [0.02] * 40 + [-0.02] * 20
    candles = _candles(len(funding))
    g = _genome(pair="BTC/USDC", **_params(window=20))
    result = BacktestEngine(
        decode(g)(), decode_portfolio(g)(10_000.0, 0.0), stop_pct=decode_stop(g)
    ).run(candles, funding=funding)
    assert result.metrics["total_return"] > 0  # collected the funding premium (zero fees)
    assert any(t.direction == 0 for t in result.trades)  # a market-neutral carry round-trip


def test_carry_stays_flat_without_funding():
    # funding=None -> no funding_rate feature -> the strategy can never find a premium to hedge.
    candles = _candles(30)
    g = _genome(pair="BTC/USDC", **_params(window=20))
    result = BacktestEngine(decode(g)(), decode_portfolio(g)(10_000.0, 0.0)).run(candles)
    assert result.metrics["trades"] == 0
    assert result.metrics["total_return"] == 0.0


def test_spot_family_still_uses_spot_book():
    # Guard the seam didn't leak: a non-carry family keeps the direction gene's book.
    g = Genome(
        "rsi_meanreversion", "BTC/USDC", {"period": 14, "oversold": 30.0, "exit_level": 70.0}
    )
    assert isinstance(decode_portfolio(g)(10_000.0, 0.001), SpotPortfolio)
