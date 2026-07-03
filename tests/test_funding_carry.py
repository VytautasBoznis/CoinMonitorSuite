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
    return {"window": 60, "entry_pct": 0.5, **overrides}


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
    assert set(fam.params) == {"window", "entry_pct"}
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
    assert _run(FundingCarry(window=3, entry_pct=0.0), [None] * 10) == [0] * 10


def test_holds_flat_through_warmup():
    # Until the rolling window is full there is nothing to rank the current rate against.
    targets = _run(FundingCarry(window=5, entry_pct=0.0), [0.001] * 8)
    assert targets[:4] == [0, 0, 0, 0]
    assert targets[4] == 1  # first full window, positive rate, entry_pct=0 -> hedge on


def test_flat_when_funding_non_positive():
    # Never run a fee-bleeding hedge while paying to hold it.
    targets = _run(FundingCarry(window=3, entry_pct=0.0), [0.001, 0.001, 0.001, -0.001, 0.0])
    assert targets == [0, 0, 1, 0, 0]


def test_entry_pct_gates_on_percentile_rank():
    rising = FundingCarry(window=4, entry_pct=1.0)
    # last rate is the window max -> rank 1.0 -> clears a 100th-percentile threshold
    assert _run(rising, [0.001, 0.002, 0.003, 0.004])[-1] == 1
    falling = FundingCarry(window=4, entry_pct=0.5)
    # last rate is the window min -> rank 0.25 -> below a 50th-percentile threshold
    assert _run(falling, [0.004, 0.003, 0.002, 0.001])[-1] == 0


def test_buffer_stays_bounded():
    strat = FundingCarry(window=5, entry_pct=0.5)
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
    a = _genome("BTC/USDC", window=30, entry_pct=0.2)
    b = _genome("ETH/USDC", window=150, entry_pct=0.9)
    for _ in range(200):
        child = crossover(a, b, rng)
        validate(child)
        if child.family == FAMILY:
            for name in FAMILIES[FAMILY].params:
                assert child.params[name] in {a.params[name], b.params[name]}


# --- end-to-end through the engine with a real funding series ------------------------------


def test_engine_harvests_the_carry_premium():
    # Price is flat (the hedge is market-neutral anyway); funding is richly positive while the
    # hedge is on, then drops to zero so the hedge closes and books a round-trip.
    funding = [0.01] * 25 + [0.0] * 5
    candles = _candles(len(funding))
    g = _genome(pair="BTC/USDC", **_params(window=20, entry_pct=0.0))
    result = BacktestEngine(
        decode(g)(), decode_portfolio(g)(10_000.0, 0.0), stop_pct=decode_stop(g)
    ).run(candles, funding=funding)
    assert result.metrics["total_return"] > 0  # collected the funding premium (zero fees)
    assert any(t.direction == 0 for t in result.trades)  # a market-neutral carry round-trip


def test_carry_stays_flat_without_funding():
    # funding=None -> no funding_rate feature -> the strategy can never find a premium to hedge.
    candles = _candles(30)
    g = _genome(pair="BTC/USDC", **_params(window=20, entry_pct=0.0))
    result = BacktestEngine(decode(g)(), decode_portfolio(g)(10_000.0, 0.0)).run(candles)
    assert result.metrics["trades"] == 0
    assert result.metrics["total_return"] == 0.0


def test_spot_family_still_uses_spot_book():
    # Guard the seam didn't leak: a non-carry family keeps the direction gene's book.
    g = Genome(
        "rsi_meanreversion", "BTC/USDC", {"period": 14, "oversold": 30.0, "exit_level": 70.0}
    )
    assert isinstance(decode_portfolio(g)(10_000.0, 0.001), SpotPortfolio)
