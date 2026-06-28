from __future__ import annotations

import random
import statistics
from collections.abc import Callable
from dataclasses import dataclass

from coinmon.search.genome import FAMILIES, LEVERAGE, UNIVERSE, Genome, ParamSpec

# Chunk C: the evolutionary search. This module is the GA *mechanics* only — purely a function
# of a seeded ``random.Random`` and a caller-supplied ``fitness(genome) -> float`` — so it carries
# no I/O and is deterministic and unit-testable without the DB. The runner (search/runner.py)
# supplies the real fitness (OOS ``evaluate_fitness`` + fragility gate) and the candle data.
#
# The discipline from [[search-overfits-not-strategy]] lives in that fitness, not here: this loop
# only proposes genomes and trusts the OOS/fragility score to reject the overfit corners. So the
# param ranges in FAMILIES are explored freely — a junk band just scores poorly out-of-sample.


def _sample_param(spec: ParamSpec, rng: random.Random) -> float:
    if spec.integer:
        return float(rng.randint(int(spec.low), int(spec.high)))
    return rng.uniform(spec.low, spec.high)


def _clamp(value: float, spec: ParamSpec) -> float:
    value = max(spec.low, min(spec.high, value))
    return float(round(value)) if spec.integer else value


def random_genome(rng: random.Random) -> Genome:
    """A uniformly-sampled valid genome: random family, random pair from the UNIVERSE pool, each
    param drawn within its spec, and a coin-flip direction gene (long/flat spot vs a leveraged
    perp short) with leverage drawn within its range. Used to seed the initial population."""
    family = rng.choice(list(FAMILIES))
    spec = FAMILIES[family]
    params = {name: _sample_param(s, rng) for name, s in spec.params.items()}
    pair = rng.choice(UNIVERSE)
    short = rng.random() < 0.5
    leverage = _sample_param(LEVERAGE, rng)
    return Genome(family, pair, params, short, leverage)


def mutate(
    genome: Genome,
    rng: random.Random,
    *,
    rate: float = 0.3,
    sigma: float = 0.2,
    family_switch_rate: float = 0.05,
) -> Genome:
    """Return a mutated copy. With ``family_switch_rate`` the genome jumps to a different family
    (resampling that family's params, keeping the pair) so neither family can go extinct mid-run.
    Otherwise each param is jittered with probability ``rate`` by a Gaussian step of ``sigma`` of
    its range (then clamped/rounded to stay valid), and the pair gene is re-rolled with the same
    probability — pair choice dominated in chunk A, so it must stay mobile. The direction genes
    (short on/off, leverage) also mutate at ``rate`` so the GA can flip a strategy bearish (or
    dial its leverage) without waiting for a fresh random genome; both survive a family switch."""
    short = (not genome.short) if rng.random() < rate else genome.short
    leverage = (
        _clamp(genome.leverage + rng.gauss(0.0, sigma * (LEVERAGE.high - LEVERAGE.low)), LEVERAGE)
        if rng.random() < rate
        else genome.leverage
    )
    if FAMILIES.keys() - {genome.family} and rng.random() < family_switch_rate:
        new_family = rng.choice([f for f in FAMILIES if f != genome.family])
        spec = FAMILIES[new_family]
        params = {name: _sample_param(s, rng) for name, s in spec.params.items()}
        return Genome(new_family, genome.pair, params, short, leverage)

    family = FAMILIES[genome.family]
    params = dict(genome.params)
    for name, spec in family.params.items():
        if rng.random() < rate:
            step = rng.gauss(0.0, sigma * (spec.high - spec.low))
            params[name] = _clamp(params[name] + step, spec)
    pair = rng.choice(UNIVERSE) if rng.random() < rate else genome.pair
    return Genome(genome.family, pair, params, short, leverage)


def crossover(a: Genome, b: Genome, rng: random.Random) -> Genome:
    """Uniform crossover. Across different families the param schemas are incompatible, so one
    parent is inherited wholesale (with its direction genes); within a family each param, the pair
    gene and the direction genes are picked independently from either parent."""
    if a.family != b.family:
        return a if rng.random() < 0.5 else b
    family = FAMILIES[a.family]
    params = {
        name: (a.params[name] if rng.random() < 0.5 else b.params[name]) for name in family.params
    }
    pair = a.pair if rng.random() < 0.5 else b.pair
    short = a.short if rng.random() < 0.5 else b.short
    leverage = a.leverage if rng.random() < 0.5 else b.leverage
    return Genome(a.family, pair, params, short, leverage)


def tournament_select(
    scored: list[tuple[Genome, float]], rng: random.Random, k: int
) -> Genome:
    """Pick the fittest of ``k`` random contenders — selection pressure tunable via ``k``."""
    contenders = rng.sample(scored, min(k, len(scored)))
    return max(contenders, key=lambda sg: sg[1])[0]


@dataclass(frozen=True)
class GAConfig:
    population: int = 30
    generations: int = 12
    elite: int = 2  # fittest genomes copied unchanged into the next generation
    tournament_size: int = 3
    mutation_rate: float = 0.3
    seed: int = 0


@dataclass(frozen=True)
class Generation:
    """One generation's fitness snapshot — the trace used to prove the GA actually improves."""

    index: int
    best_fitness: float
    mean_fitness: float


@dataclass
class GAResult:
    best: Genome
    best_fitness: float
    history: list[Generation]
    scored_final: list[tuple[Genome, float]]  # final population, fittest first


def _key(genome: Genome) -> tuple:
    """Hashable identity for fitness memoization (``params`` is an unhashable dict). Includes the
    direction genes so a long and a short variant of the same family/pair/params don't collide."""
    return (
        genome.family,
        genome.pair,
        tuple(sorted(genome.params.items())),
        genome.short,
        genome.leverage,
    )


def evolve(
    fitness: Callable[[Genome], float],
    config: GAConfig,
    *,
    rng: random.Random | None = None,
) -> GAResult:
    """Run the GA: random initial population, then ``generations`` rounds of elitism + tournament
    selection + crossover + mutation, maximizing ``fitness``. Returns the best genome and the
    per-generation fitness history. Fitness is memoized by genome identity so the expensive
    backtest isn't repeated for carried-over elites or duplicate children — perf is the binding
    GA constraint (see [[chunk-a-findings]])."""
    rng = rng or random.Random(config.seed)
    cache: dict[tuple, float] = {}

    def score(genomes: list[Genome]) -> list[tuple[Genome, float]]:
        out = []
        for g in genomes:
            key = _key(g)
            if key not in cache:
                cache[key] = fitness(g)
            out.append((g, cache[key]))
        return out

    population = [random_genome(rng) for _ in range(config.population)]
    scored = sorted(score(population), key=lambda sg: sg[1], reverse=True)
    history = [_summarize(0, scored)]

    for gen in range(1, config.generations):
        elites = [g for g, _ in scored[: config.elite]]
        children: list[Genome] = []
        while len(children) < config.population - len(elites):
            p1 = tournament_select(scored, rng, config.tournament_size)
            p2 = tournament_select(scored, rng, config.tournament_size)
            children.append(mutate(crossover(p1, p2, rng), rng, rate=config.mutation_rate))
        scored = sorted(score(elites + children), key=lambda sg: sg[1], reverse=True)
        history.append(_summarize(gen, scored))

    return GAResult(
        best=scored[0][0],
        best_fitness=scored[0][1],
        history=history,
        scored_final=scored,
    )


def _summarize(index: int, scored: list[tuple[Genome, float]]) -> Generation:
    finite = [f for _, f in scored if f != float("-inf")]
    mean = statistics.fmean(finite) if finite else float("-inf")
    return Generation(index=index, best_fitness=scored[0][1], mean_fitness=mean)
