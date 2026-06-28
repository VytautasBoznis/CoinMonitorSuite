from __future__ import annotations

import random
import statistics
from collections.abc import Callable
from dataclasses import dataclass

from coinmon.search.genome import (
    DIRECTIONS,
    FAMILIES,
    LEVERAGE,
    STOP,
    TREND,
    UNIVERSE,
    Genome,
    ParamSpec,
)

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


def _sample_stop(rng: random.Random) -> float | None:
    """A coin-flip stop gene: half the genomes carry a stop drawn within its range, half run with
    no stop (``None``). Both must be reachable — a stop helps some families and hurts others
    ([[stop-loss-hurts-mean-reversion]]), so the GA has to be able to pick either."""
    return _sample_param(STOP, rng) if rng.random() < 0.5 else None


def random_genome(rng: random.Random) -> Genome:
    """A uniformly-sampled valid genome: random family, random pair from the UNIVERSE pool, each
    param drawn within its spec, a direction gene (long/flat spot vs a regime-adaptive perp) with
    leverage and a regime window drawn within their ranges, and a coin-flip intrabar stop gene. Used
    to seed the initial population."""
    family = rng.choice(list(FAMILIES))
    spec = FAMILIES[family]
    params = {name: _sample_param(s, rng) for name, s in spec.params.items()}
    pair = rng.choice(UNIVERSE)
    direction = rng.choice(DIRECTIONS)
    leverage = _sample_param(LEVERAGE, rng)
    trend_period = _sample_param(TREND, rng)
    stop_pct = _sample_stop(rng)
    return Genome(family, pair, params, direction, leverage, trend_period, stop_pct)


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
    (long/adaptive, leverage, regime window) and the stop gene also mutate at ``rate`` so the GA can
    flip a strategy regime-adaptive, dial its leverage or regime window, or arm/disarm its stop
    without waiting for a fresh random genome; all survive a family switch."""
    direction = (
        rng.choice([d for d in DIRECTIONS if d != genome.direction])
        if rng.random() < rate
        else genome.direction
    )
    leverage = (
        _clamp(genome.leverage + rng.gauss(0.0, sigma * (LEVERAGE.high - LEVERAGE.low)), LEVERAGE)
        if rng.random() < rate
        else genome.leverage
    )
    trend_period = (
        _clamp(genome.trend_period + rng.gauss(0.0, sigma * (TREND.high - TREND.low)), TREND)
        if rng.random() < rate
        else genome.trend_period
    )
    stop_pct = _mutate_stop(genome.stop_pct, rng, rate, sigma)
    if FAMILIES.keys() - {genome.family} and rng.random() < family_switch_rate:
        new_family = rng.choice([f for f in FAMILIES if f != genome.family])
        spec = FAMILIES[new_family]
        params = {name: _sample_param(s, rng) for name, s in spec.params.items()}
        return Genome(new_family, genome.pair, params, direction, leverage, trend_period, stop_pct)

    family = FAMILIES[genome.family]
    params = dict(genome.params)
    for name, spec in family.params.items():
        if rng.random() < rate:
            step = rng.gauss(0.0, sigma * (spec.high - spec.low))
            params[name] = _clamp(params[name] + step, spec)
    pair = rng.choice(UNIVERSE) if rng.random() < rate else genome.pair
    return Genome(genome.family, pair, params, direction, leverage, trend_period, stop_pct)


def _mutate_stop(
    stop_pct: float | None, rng: random.Random, rate: float, sigma: float
) -> float | None:
    """Mutate the stop gene at ``rate``: a disarmed stop arms (drawn within its range), an armed
    stop either jitters its threshold (Gaussian, clamped) or — one time in five — disarms entirely,
    so the GA can move freely between no-stop and any threshold."""
    if rng.random() >= rate:
        return stop_pct
    if stop_pct is None:
        return _sample_param(STOP, rng)
    if rng.random() < 0.2:
        return None
    return _clamp(stop_pct + rng.gauss(0.0, sigma * (STOP.high - STOP.low)), STOP)


def crossover(a: Genome, b: Genome, rng: random.Random) -> Genome:
    """Uniform crossover. Across different families the param schemas are incompatible, so one
    parent is inherited wholesale (with its direction + stop genes); within a family each param, the
    pair gene, the direction genes and the stop gene are picked independently from either parent."""
    if a.family != b.family:
        return a if rng.random() < 0.5 else b
    family = FAMILIES[a.family]
    params = {
        name: (a.params[name] if rng.random() < 0.5 else b.params[name]) for name in family.params
    }
    pair = a.pair if rng.random() < 0.5 else b.pair
    direction = a.direction if rng.random() < 0.5 else b.direction
    leverage = a.leverage if rng.random() < 0.5 else b.leverage
    trend_period = a.trend_period if rng.random() < 0.5 else b.trend_period
    stop_pct = a.stop_pct if rng.random() < 0.5 else b.stop_pct
    return Genome(a.family, pair, params, direction, leverage, trend_period, stop_pct)


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
    direction, regime and stop genes so long/adaptive or stopped/unstopped variants of the same
    family/pair/params don't collide."""
    return (
        genome.family,
        genome.pair,
        tuple(sorted(genome.params.items())),
        genome.direction,
        genome.leverage,
        genome.trend_period,
        genome.stop_pct,
    )


def evolve(
    fitness: Callable[[Genome], float],
    config: GAConfig,
    *,
    rng: random.Random | None = None,
    score_batch: Callable[[list[Genome]], list[float]] | None = None,
) -> GAResult:
    """Run the GA: random initial population, then ``generations`` rounds of elitism + tournament
    selection + crossover + mutation, maximizing ``fitness``. Returns the best genome and the
    per-generation fitness history. Fitness is memoized by genome identity so the expensive
    backtest isn't repeated for carried-over elites or duplicate children — perf is the binding
    GA constraint (see [[chunk-a-findings]]).

    The RNG stream (population, mutation, crossover, selection) is serial and seed-deterministic;
    only the per-genome fitness MAP is parallelizable. ``score_batch`` (chunk N2) scores a list of
    genomes at once — a process pool can fan it across cores. Because each fitness is a pure,
    RNG-free ``genome -> float``, an order-preserving parallel map is bit-identical to serial, so
    determinism holds regardless of ``score_batch``. Default: a serial map over ``fitness``."""
    rng = rng or random.Random(config.seed)
    cache: dict[tuple, float] = {}
    if score_batch is None:
        def score_batch(genomes: list[Genome]) -> list[float]:
            return [fitness(g) for g in genomes]

    def score(genomes: list[Genome]) -> list[tuple[Genome, float]]:
        # Score only the genomes not already memoized, deduped within this batch, then map them in
        # one call so the batch scorer can parallelize. Results stay aligned with ``pending`` order
        # (the map is order-preserving), so the cache fills correctly and the run is deterministic.
        pending: list[Genome] = []
        seen: set[tuple] = set()
        for g in genomes:
            key = _key(g)
            if key not in cache and key not in seen:
                seen.add(key)
                pending.append(g)
        if pending:
            for g, f in zip(pending, score_batch(pending), strict=True):
                cache[_key(g)] = f
        return [(g, cache[_key(g)]) for g in genomes]

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
