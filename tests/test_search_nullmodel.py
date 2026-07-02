import math

import pytest

from coinmon.backtest.portfolio import PerpPortfolio, SpotPortfolio
from coinmon.search.evidence import EvalSegment
from coinmon.search.genome import UNIVERSE, Genome
from coinmon.search.nullmodel import (
    NullResult,
    _synthetic_return,
    null_from_distribution,
    null_from_scores,
    random_entry_null,
    random_genome_null,
    surrogate_null,
)


def test_candidate_above_sample_max_beats_null():
    # A candidate that clears every random score clears the best-of-M null.
    result = null_from_scores(5.0, [0.1, 0.4, 0.2, -0.3, 0.9], seed=0)
    assert result.beaten
    assert result.mode == "random"
    assert result.n_samples == 5


def test_candidate_inside_the_bulk_does_not_beat_null():
    # The best-of-M null's 95% tail sits at (or just below) the sample max, so a candidate that
    # merely matches a typical random score is NOT a real edge.
    scores = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    result = null_from_scores(0.5, scores, seed=0)
    assert not result.beaten
    assert result.percentile >= 0.5  # threshold is the upper tail of the max, above the median


def test_percentile_near_sample_max_for_best_of_m():
    # Bootstrapping the max of M draws lands the 95th percentile at the top of the sample: the bar
    # is "beat the best random genome", the correct null for a SELECTED statistic.
    scores = [float(i) for i in range(20)]
    result = null_from_scores(100.0, scores, seed=1)
    assert result.percentile == 19.0  # the sample max
    assert result.beaten


def test_deterministic_given_seed():
    scores = [0.3, -0.1, 0.7, 0.2, 0.5, 0.05]
    a = null_from_scores(0.6, scores, seed=7)
    b = null_from_scores(0.6, scores, seed=7)
    assert a == b


def test_all_infinite_scores_cannot_be_beaten():
    # No finite random score means no null can be formed — the threshold is +inf, never beaten,
    # so a genome whose whole peer set failed to score can't sneak a C4 pass.
    result = null_from_scores(9.9, [float("-inf"), float("inf"), float("nan")], seed=0)
    assert not result.beaten
    assert math.isinf(result.percentile)


def test_infinite_scores_are_filtered_from_the_null():
    result = null_from_scores(2.0, [1.0, float("-inf"), 1.5, float("nan")], seed=0)
    assert result.percentile == 1.5  # only the two finite scores drive the max
    assert result.beaten


def test_to_from_dict_round_trip():
    result = null_from_scores(0.6, [0.1, 0.2, 0.9], seed=3)
    assert NullResult.from_dict(result.to_dict()) == result


def test_random_genome_null_uses_injected_scorer():
    # An injected scorer (no DB): the candidate scores far above any random genome -> beaten;
    # n_samples matches n_genomes and the draw is deterministic in sample_seed.
    def score(genome: Genome) -> float:
        return 0.1  # every random genome is mediocre

    result = random_genome_null(
        candidate_score=3.0,
        read=lambda s: None,
        taker_fee=0.001,
        eval_pairs=("BTC/USDC",),
        universe=UNIVERSE,
        n_genomes=25,
        score_genome=score,
    )
    assert result.beaten
    assert result.n_samples == 25


def test_random_genome_null_candidate_loses_to_lucky_random():
    # If a random genome can score as high as the candidate, the candidate does not clear the null.
    def score(genome: Genome) -> float:
        # one family scores high, mimicking a lucky random try matching the candidate
        return 2.0 if genome.family == "ema_crossover" else 0.1

    result = random_genome_null(
        candidate_score=1.5,
        read=lambda s: None,
        taker_fee=0.001,
        eval_pairs=("BTC/USDC",),
        n_genomes=60,
        sample_seed=0,
        score_genome=score,
    )
    # with 60 draws at least one ema_crossover (2.0) is sampled, so the best-of-M tail is 2.0 > 1.5
    assert not result.beaten


def test_random_genome_null_is_deterministic_in_seeds():
    def score(genome: Genome) -> float:
        return len(genome.family) * 0.1

    kwargs = dict(
        candidate_score=1.0,
        read=lambda s: None,
        taker_fee=0.001,
        eval_pairs=("BTC/USDC",),
        n_genomes=15,
        sample_seed=4,
        boot_seed=2,
        score_genome=score,
    )
    assert random_genome_null(**kwargs) == random_genome_null(**kwargs)


# --- V2: exposure-matched random-entry null ---


def test_null_from_distribution_uses_the_direct_percentile():
    # No best-of-M bootstrap: the threshold is the sample's own 95th percentile. 20 evenly-spaced
    # scores -> 95th pct lands on the top value; a candidate above it beats the null.
    scores = [float(i) for i in range(20)]
    result = null_from_distribution(19.5, scores, quantile=0.95)
    assert result.mode == "matched"
    assert result.percentile == 19.0
    assert result.beaten


def test_null_from_distribution_candidate_below_tail_not_beaten():
    scores = [float(i) for i in range(20)]
    result = null_from_distribution(5.0, scores, quantile=0.95)
    assert not result.beaten


def test_null_from_distribution_all_infinite_cannot_be_beaten():
    result = null_from_distribution(9.9, [float("inf"), float("nan")])
    assert not result.beaten
    assert math.isinf(result.percentile)


def test_synthetic_return_spot_long_is_price_move_minus_fees():
    # Spot long, zero fee, +10% price move over one bar -> +10% return.
    ret = _synthetic_return(
        lambda cash, fee: SpotPortfolio(cash, fee), 0.0,
        opens=[100.0, 110.0], closes=[105.0], entry_idx=0, duration=1, direction=1,
    )
    assert ret == 0.10


def test_synthetic_return_perp_short_profits_when_price_falls():
    # Perp short at 2x, zero fee, -10% price move -> +20% return on collateral.
    ret = _synthetic_return(
        lambda cash, fee: PerpPortfolio(cash, fee, 2.0), 0.0,
        opens=[100.0, 95.0, 90.0], closes=[95.0, 90.0], entry_idx=0, duration=2, direction=-1,
    )
    assert ret == pytest.approx(0.20)


def test_synthetic_return_liquidation_marks_on_a_held_close():
    # Perp long at 5x: a 25% drop marked mid-hold wipes the collateral -> -100%, latched even though
    # the exit-bar open recovers (the engine's isolated-margin liquidation, matched here).
    ret = _synthetic_return(
        lambda cash, fee: PerpPortfolio(cash, fee, 5.0), 0.0,
        opens=[100.0, 75.0, 100.0], closes=[100.0, 75.0], entry_idx=0, duration=2, direction=1,
    )
    assert ret == -1.0


def test_random_entry_null_is_deterministic_in_seed():
    seg = EvalSegment(
        opens=(100.0, 101.0, 102.0, 103.0, 104.0),
        closes=(100.0, 101.0, 102.0, 103.0, 104.0),
        trades=((1, 1), (1, 2)),
    )
    a = random_entry_null(0.05, [seg], SpotPortfolio, 0.0, resamples=200, seed=3)
    b = random_entry_null(0.05, [seg], SpotPortfolio, 0.0, resamples=200, seed=3)
    assert a == b
    assert a.n_samples == 200


def test_random_entry_null_flat_series_beaten_only_by_positive_expectancy():
    # A flat series (every entry returns 0 at zero fee) -> the whole matched distribution is 0. Any
    # genuinely positive expectancy clears it; a negative one does not. This is the exposure floor.
    seg = EvalSegment(
        opens=(100.0, 100.0, 100.0),
        closes=(100.0, 100.0, 100.0),
        trades=((1, 1), (1, 2)),
    )
    assert random_entry_null(0.01, [seg], SpotPortfolio, 0.0, resamples=100, seed=0).beaten
    assert not random_entry_null(-0.01, [seg], SpotPortfolio, 0.0, resamples=100, seed=0).beaten


def test_random_entry_null_uptrend_beta_does_not_beat_the_null():
    # Riding a monotone uptrend, random long entries are almost all positive: a candidate whose
    # expectancy merely equals that beta (long the trend) must NOT clear the 95th percentile.
    opens = tuple(100.0 + i for i in range(40))
    seg = EvalSegment(opens=opens, closes=opens, trades=tuple((1, 3) for _ in range(6)))
    result = random_entry_null(0.0, [seg], SpotPortfolio, 0.0, resamples=500, seed=1)
    # the random-entry expectancy is positive (pure beta), so its 95th pct is well above 0
    assert result.percentile > 0
    assert not result.beaten


# --- V3: surrogate-data null ---


def test_surrogate_null_uses_injected_per_surrogate_scorer():
    # An injected scorer (no DB / no search): every surrogate scores mediocre, the candidate towers
    # over them -> beaten; n_samples matches n_surrogates and the mode is tagged surrogate.
    result = surrogate_null(3.0, lambda s: 0.1, n_surrogates=20, seed=0)
    assert result.beaten
    assert result.mode == "surrogate"
    assert result.n_samples == 20


def test_surrogate_null_candidate_inside_the_noise_not_beaten():
    # If the search mines scores as high as the candidate out of pure noise, the candidate is not a
    # real edge — a surrogate reaching the candidate's score puts it below the 95th percentile.
    result = surrogate_null(9.0, lambda s: float(s), n_surrogates=20, seed=0)
    assert not result.beaten  # surrogate scores 0..19; 95th pct (19) is well above 9


def test_surrogate_null_seeds_each_surrogate_distinctly():
    seen: list[int] = []

    def score(s: int) -> float:
        seen.append(s)
        return 0.0

    surrogate_null(1.0, score, n_surrogates=5, seed=100)
    assert seen == [100, 101, 102, 103, 104]


def test_surrogate_null_is_deterministic():
    a = surrogate_null(2.0, lambda s: (s % 3) * 0.5, n_surrogates=12, seed=1)
    b = surrogate_null(2.0, lambda s: (s % 3) * 0.5, n_surrogates=12, seed=1)
    assert a == b
