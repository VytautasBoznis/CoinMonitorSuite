import math

import pandas as pd
import pytest

from coinmon.data.candles import split_holdout
from coinmon.search.genome import Genome
from coinmon.search.graduation import graduate


def _frame(closes):
    return pd.DataFrame(
        {
            "open_time": range(len(closes)),
            "open": closes,
            "high": [c + 1 for c in closes],
            "low": [c - 1 for c in closes],
            "close": closes,
            "volume": [1.0] * len(closes),
        }
    )


def _oscillation(n=300):
    # A clean, strongly mean-reverting series: RSI buys the troughs and exits the peaks, so a
    # well-formed RSI genome makes money with many trades and survives small frictions.
    return _frame([100.0 + 25.0 * math.sin(i / 5.0) for i in range(n)])


def _uptrend(n=300):
    # Monotonic ramp: RSI rarely dips oversold, so the mean-reversion genome barely trades.
    return _frame([100.0 + 0.5 * i for i in range(n)])


def _downtrend(n=300):
    # A falling mean with strong oscillation: RSI trades both legs, but holding long through the
    # drift bleeds on spot — the case the perp short exists to win (see perp-short-capability).
    return _frame([100.0 - 0.25 * i + 12.0 * math.sin(i / 5.0) for i in range(n)])


# pair is irrelevant to graduate() — it scores the holdout frame it is handed directly.
_RSI = Genome(
    family="rsi_meanreversion",
    pair="BTC/USDC",
    params={"period": 14, "oversold": 30.0, "exit_level": 55.0},
)


def test_graduate_passes_a_robust_edge():
    report = graduate(_RSI, _oscillation(), taker_fee=0.0, fragility_runs=30)
    assert report.passed
    assert report.reasons == ()
    assert report.holdout_return > 0
    assert report.holdout_trades >= 5
    assert report.fragility.runs == 30


def test_adaptive_genome_outprofits_the_long_one_and_graduates_on_a_downtrend():
    # The regime-adaptive payoff: on a falling market the SAME family/params run as a leveraged
    # regime-adaptive perp read the down-regime and short the would-be-flat legs, capturing the
    # drift the long/flat book leaves on the table — so it both out-returns the spot genome and
    # clears the absolute graduation gate. Unlike a fixed short, direction here comes from the
    # holdout's own measured trend, not an in-sample gene (see direction-gene-overfits-regime).
    holdout = _downtrend()
    long_genome = Genome(
        family="rsi_meanreversion", pair="BTC/USDC",
        params={"period": 14, "oversold": 30.0, "exit_level": 55.0},
    )
    adaptive_genome = Genome(
        family="rsi_meanreversion", pair="BTC/USDC",
        params={"period": 14, "oversold": 30.0, "exit_level": 55.0},
        direction="adaptive", leverage=2.0, trend_period=20.0,
    )
    long_report = graduate(long_genome, holdout, taker_fee=0.0, fragility_runs=30)
    adaptive_report = graduate(adaptive_genome, holdout, taker_fee=0.0, fragility_runs=30)

    # the regime-adaptive genome wins the downtrend
    assert adaptive_report.holdout_return > long_report.holdout_return
    assert adaptive_report.holdout_return > 0
    assert adaptive_report.passed  # the regime-adaptive perp graduates GO
    assert adaptive_report.reasons == ()


def test_graduate_rejects_a_genome_that_does_not_trade():
    report = graduate(_RSI, _uptrend(), taker_fee=0.0, fragility_runs=30)
    assert not report.passed
    assert report.reasons  # at least the not-positive / too-few-trades gates fired


def test_graduate_fails_min_trades_gate():
    # The edge is real, but demanding an absurd trade count rejects it for thin evidence.
    report = graduate(_RSI, _oscillation(), taker_fee=0.0, fragility_runs=30, min_trades=10_000)
    assert not report.passed
    assert any("trades" in r for r in report.reasons)


def test_graduate_fails_fragility_gate():
    # Requiring more-than-100% positive runs is impossible, so the fragility gate always bites.
    report = graduate(
        _RSI, _oscillation(), taker_fee=0.0, fragility_runs=30, min_fraction_positive=1.1
    )
    assert not report.passed
    assert any("fragility" in r for r in report.reasons)


def test_split_holdout_carves_the_tail():
    head, tail = split_holdout(_frame(list(range(100))), 0.2)
    assert len(head) == 80
    assert len(tail) == 20
    # The tail is the LAST bars, both index-reset to stand alone.
    assert tail["close"].iloc[0] == 80
    assert list(head.index) == list(range(80))
    assert list(tail.index) == list(range(20))


@pytest.mark.parametrize("bad", [0.0, 1.0, -0.1, 1.5])
def test_split_holdout_rejects_out_of_range_fraction(bad):
    with pytest.raises(ValueError):
        split_holdout(_frame(list(range(100))), bad)
