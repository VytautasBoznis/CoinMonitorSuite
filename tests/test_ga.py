import random

from coinmon.search.ga import (
    GAConfig,
    crossover,
    evolve,
    mutate,
    random_genome,
    tournament_select,
)
from coinmon.search.genome import FAMILIES, Genome, validate


def test_random_genome_is_always_valid():
    rng = random.Random(1)
    for _ in range(500):
        validate(random_genome(rng))  # raises if ill-formed


def test_mutate_keeps_genome_valid():
    rng = random.Random(2)
    g = random_genome(rng)
    for _ in range(500):
        g = mutate(g, rng)
        validate(g)


def test_crossover_within_family_is_valid_and_inherits_from_parents():
    rng = random.Random(3)
    a = Genome("rsi_meanreversion", "XRP/ETH", {"period": 5, "oversold": 20.0, "exit_level": 60.0})
    b = Genome("rsi_meanreversion", "ETH/BTC", {"period": 30, "oversold": 40.0, "exit_level": 80.0})
    for _ in range(200):
        child = crossover(a, b, rng)
        validate(child)
        assert child.family == "rsi_meanreversion"
        assert child.pair in {a.pair, b.pair}
        for name in FAMILIES["rsi_meanreversion"].params:
            assert child.params[name] in {a.params[name], b.params[name]}


def test_crossover_across_families_inherits_one_parent_wholesale():
    rng = random.Random(4)
    a = Genome("rsi_meanreversion", "XRP/ETH", {"period": 5, "oversold": 20.0, "exit_level": 60.0})
    b = Genome("ema_crossover", "ETH/BTC", {"fast": 12, "slow": 26})
    for _ in range(50):
        assert crossover(a, b, rng) in (a, b)


def test_tournament_select_returns_fittest_contender_when_k_covers_all():
    rng = random.Random(5)
    scored = [
        (random_genome(rng), -1.0),
        (random_genome(rng), 5.0),
        (random_genome(rng), 2.0),
    ]
    # k >= population => the whole field competes => the max must win every time.
    for _ in range(20):
        assert tournament_select(scored, rng, k=3) is scored[1][0]


def test_evolve_is_deterministic_for_a_seed():
    def fitness(g):
        return float(g.params.get("period", g.params.get("fast", 0)))

    cfg = GAConfig(population=12, generations=6, seed=7)
    a = evolve(fitness, cfg)
    b = evolve(fitness, cfg)
    assert a.best == b.best
    assert a.best_fitness == b.best_fitness


def test_evolve_improves_fitness_over_generations():
    # A synthetic objective with a clear optimum the GA should climb toward: a specific pair plus
    # an RSI period near 30 (the top of its range). Final best must beat the random gen-0 best.
    def fitness(g: Genome) -> float:
        if g.family != "rsi_meanreversion":
            return -100.0
        pair_bonus = 10.0 if g.pair == "XRP/ETH" else 0.0
        return pair_bonus - abs(g.params["period"] - 30.0)

    result = evolve(fitness, GAConfig(population=20, generations=15, seed=0))
    assert result.history[-1].best_fitness > result.history[0].best_fitness
    assert result.best.family == "rsi_meanreversion"
    assert result.best.pair == "XRP/ETH"
    assert abs(result.best.params["period"] - 30.0) < 3.0


def test_evolve_history_length_matches_generations():
    def fitness(g):
        return 1.0

    result = evolve(fitness, GAConfig(population=6, generations=4, seed=1))
    assert [h.index for h in result.history] == [0, 1, 2, 3]


def test_evolve_memoizes_fitness_calls():
    calls = {"n": 0}

    def fitness(g: Genome) -> float:
        calls["n"] += 1
        return 0.0  # constant => elites/duplicates recur => memo must collapse the calls

    cfg = GAConfig(population=10, generations=10, seed=2)
    evolve(fitness, cfg)
    # Without caching this would be ~population*generations (100); memoization makes it far fewer.
    assert calls["n"] < cfg.population * cfg.generations
