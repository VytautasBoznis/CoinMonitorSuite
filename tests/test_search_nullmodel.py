import math

from coinmon.search.genome import UNIVERSE, Genome
from coinmon.search.nullmodel import (
    NullResult,
    null_from_scores,
    random_genome_null,
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
