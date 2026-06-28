import math

import pandas as pd

from coinmon.search.genome import Genome
from coinmon.search.robustness import (
    PairVerdict,
    build_robustness_report,
    classify_robustness,
    pick_decorrelated_pairs,
)


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


def _verdict(pair, passed):
    return PairVerdict(
        pair=pair, passed=passed, holdout_return=0.05 if passed else -0.05,
        holdout_trades=20, fragility_positive=1.0,
    )


_GENOME = Genome(
    family="rsi_meanreversion", pair="BTC/USDC",
    params={"period": 14, "oversold": 30.0, "exit_level": 60.0},
)


def test_golden_when_enough_pairs_pass():
    verdicts = [_verdict("ETH/USDC", True), _verdict("SOL/BTC", True), _verdict("XRP/ETH", True)]
    report = build_robustness_report(_GENOME, verdicts, min_pass=3)
    assert report.pass_count == 3
    assert report.tier == "golden"


def test_specialist_when_too_few_pairs_pass():
    verdicts = [_verdict("ETH/USDC", True), _verdict("SOL/BTC", False), _verdict("XRP/ETH", False)]
    report = build_robustness_report(_GENOME, verdicts, min_pass=3)
    assert report.pass_count == 1
    assert report.tier == "specialist"


def test_summary_names_the_tier_and_each_pair():
    report = build_robustness_report(_GENOME, [_verdict("ETH/USDC", True)], min_pass=1)
    out = report.summary()
    assert "GOLDEN" in out
    assert "ETH/USDC" in out
    assert "PASS" in out


def test_pick_decorrelated_avoids_correlated_pairs():
    # A and A_TWIN share the SAME return series (|corr| 1.0); B is flat (corr undefined => treated
    # as decorrelated, always selectable). With n=2 the twin is rejected and NOT topped up, so
    # exactly one of {A, A_TWIN} is chosen alongside B.
    base = pd.Series([0.01, -0.02, 0.03, -0.01, 0.02])
    series = {
        "A/USDC": base, "A_TWIN/USDC": base.copy(), "B/USDC": pd.Series([0.0] * 5),
    }

    def returns_of(pair):
        return series.get(pair)

    picks = pick_decorrelated_pairs(list(series), returns_of, n=2, seed=0, max_corr=0.7)
    assert len(picks) == 2
    assert "B/USDC" in picks
    assert len({"A/USDC", "A_TWIN/USDC"} & set(picks)) == 1


def test_pick_skips_unloadable_pairs():
    def returns_of(pair):
        return None if pair == "BAD/USDC" else pd.Series([0.01, -0.02, 0.03])

    picks = pick_decorrelated_pairs(
        ["BAD/USDC", "OK/USDC"], returns_of, n=5, seed=1, max_corr=0.7
    )
    assert picks == ("OK/USDC",)


def test_pick_tops_up_when_decorrelation_is_short():
    # Everything is the same series (all correlated), but n=2 is still satisfied by topping up.
    s = pd.Series([0.01, -0.02, 0.03, -0.01])
    picks = pick_decorrelated_pairs(
        ["A/USDC", "B/USDC", "C/USDC"], lambda p: s.copy(), n=2, seed=0, max_corr=0.7
    )
    assert len(picks) == 2


_EMA_GENOME = Genome(
    family="ema_crossover", pair="BTC/USDC", params={"fast": 4.0, "slow": 20.0},
)


def test_classify_robustness_grades_each_pair_through_the_gate():
    n = 120
    # An uptrend with an oscillation: the EMA-crossover genome goes long and ends positive => PASS.
    up = _frame([100.0 + 10.0 * math.sin(i / 6.0) + 0.6 * i for i in range(n)])
    # A pure downtrend: the long/flat genome never crosses up, never trades => NO-GO.
    down = _frame([200.0 - 0.8 * i for i in range(n)])
    holdouts = {"UP/USDC": up, "DOWN/USDC": down}

    report = classify_robustness(
        _EMA_GENOME,
        ["UP/USDC", "DOWN/USDC"],
        lambda pair: holdouts[pair],
        taker_fee=0.0,
        fragility_runs=8,
        min_fraction_positive=0.5,
        min_trades=1,
        min_pass=1,
    )
    by_pair = {v.pair: v for v in report.verdicts}
    assert by_pair["UP/USDC"].passed is True
    assert by_pair["DOWN/USDC"].passed is False
    assert report.pass_count == 1
    assert report.tier == "golden"  # 1 pass >= min_pass 1
    # The overridden genome keeps the original's family/params — only the pair changes per test.
    assert report.genome.family == _EMA_GENOME.family
