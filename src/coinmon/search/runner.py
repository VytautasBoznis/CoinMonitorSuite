from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from coinmon.backtest.fitness import FitnessResult, evaluate_fitness
from coinmon.backtest.portfolio import SpotPortfolio
from coinmon.backtest.stress import MonteCarloResult, run_monte_carlo
from coinmon.data.candles import load_candles
from coinmon.search.ga import GAConfig, GAResult, evolve
from coinmon.search.genome import Genome, decode

# Chunk C orchestration: glue the pure GA (search/ga.py) to real data and the honest score.
# It resolves each genome's pair gene to candles (the same load_candles path the CLI uses),
# scores it with the OOS multi-fold ``evaluate_fitness`` during evolution, then runs the
# fragility kill-filter on the winner as a POST-FILTER gate. Fragility is deliberately not in
# the per-genome fitness: it costs hundreds of backtests per genome, and the O(n^2) engine is
# the binding constraint ([[chunk-a-findings]]) — so the cheap OOS folds drive selection and the
# expensive stress test only judges the finalist (the brief's "reject garbage" proof).

INITIAL_CAPITAL = 10_000.0


class CandleCache:
    """Resolve + cache candles per pair. Genomes reuse pairs heavily across a run, and a pair
    may be a synthetic ratio (two DB reads); caching avoids re-loading on every evaluation."""

    def __init__(self, read: Callable[[str], pd.DataFrame]) -> None:
        self._read = read
        self._cache: dict[str, pd.DataFrame] = {}

    def get(self, pair: str) -> pd.DataFrame:
        if pair not in self._cache:
            self._cache[pair] = load_candles(self._read, pair)
        return self._cache[pair]


@dataclass(frozen=True)
class FitnessParams:
    """OOS scoring knobs handed to ``evaluate_fitness`` for every genome (chunk-A defaults:
    4 folds, a 5-bar embargo to purge boundary autocorrelation, a 20-trade floor)."""

    folds: int = 4
    embargo_bars: int = 5
    min_trades: int = 20


_DEFAULT_FITNESS = FitnessParams()  # module-level singleton (avoids a call in arg defaults)


@dataclass
class SearchReport:
    best: Genome
    fitness: FitnessResult
    ga: GAResult
    fragility: MonteCarloResult | None
    passed_fragility: bool | None

    def summary(self) -> str:
        p = ", ".join(f"{k}={v:g}" for k, v in sorted(self.best.params.items()))
        lines = [
            f"best genome: {self.best.family} on {self.best.pair} ({p})",
            "",
            self.fitness.summary(),
            "",
            "GA fitness by generation (best / mean):",
        ]
        for g in self.ga.history:
            lines.append(f"  gen {g.index:>2}  {g.best_fitness:+.4f} / {g.mean_fitness:+.4f}")
        if self.fragility is not None:
            verdict = "PASS" if self.passed_fragility else "REJECT"
            lines += ["", f"fragility gate [{verdict}]:", self.fragility.summary()]
        return "\n".join(lines)


def _score_genome(
    genome: Genome, cache: CandleCache, taker_fee: float, fp: FitnessParams
) -> FitnessResult:
    return evaluate_fitness(
        cache.get(genome.pair),
        decode(genome),
        taker_fee,
        folds=fp.folds,
        embargo_bars=fp.embargo_bars,
        min_trades=fp.min_trades,
    )


def fragility_verdict(result: MonteCarloResult, min_fraction_positive: float) -> bool:
    """A genome passes the gate if at least ``min_fraction_positive`` of perturbed runs stay
    positive. A kill-filter, not a green light ([[fragility-stress-test]]): failing rejects the
    genome; passing only means it isn't obviously fragile."""
    return result.fraction_positive >= min_fraction_positive


def run_search(
    read: Callable[[str], pd.DataFrame],
    taker_fee: float,
    config: GAConfig,
    *,
    fitness_params: FitnessParams = _DEFAULT_FITNESS,
    fragility_runs: int = 0,
    fragility_min_positive: float = 0.9,
) -> SearchReport:
    """Run the GA over genomes scored by OOS fitness, then gate the winner with the fragility
    kill-filter. A genome whose pair has too little data (or any scoring error) is assigned
    ``-inf`` so the GA discards it rather than crashing the run."""
    cache = CandleCache(read)

    def fitness(genome: Genome) -> float:
        try:
            return _score_genome(genome, cache, taker_fee, fitness_params).fitness
        except (ValueError, KeyError):  # too few bars for the folds/embargo, or missing legs
            return float("-inf")

    ga = evolve(fitness, config)
    if ga.best_fitness == float("-inf"):
        raise SystemExit("no genome could be scored — is the candle data present for the UNIVERSE?")

    best_fitness = _score_genome(ga.best, cache, taker_fee, fitness_params)

    fragility: MonteCarloResult | None = None
    passed: bool | None = None
    if fragility_runs:
        fragility = run_monte_carlo(
            decode(ga.best),
            lambda: SpotPortfolio(INITIAL_CAPITAL, taker_fee),
            cache.get(ga.best.pair),
            runs=fragility_runs,
        )
        passed = fragility_verdict(fragility, fragility_min_positive)

    return SearchReport(
        best=ga.best,
        fitness=best_fitness,
        ga=ga,
        fragility=fragility,
        passed_fragility=passed,
    )
