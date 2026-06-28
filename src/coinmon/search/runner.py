from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import pandas as pd

from coinmon.backtest.fitness import FitnessResult, evaluate_fitness
from coinmon.backtest.stress import MonteCarloResult, run_monte_carlo
from coinmon.data.candles import load_candles, split_holdout
from coinmon.search.ga import GAConfig, GAResult, evolve
from coinmon.search.genome import Genome, build_universe, decode, decode_portfolio
from coinmon.search.graduation import GraduationReport, graduate

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
    graduation: GraduationReport | None = None

    def summary(self) -> str:
        p = ", ".join(f"{k}={v:g}" for k, v in sorted(self.best.params.items()))
        book = (
            f"{self.best.leverage:.1f}x perp regime-adaptive (MA{int(self.best.trend_period)})"
            if self.best.direction == "adaptive"
            else "long/flat spot"
        )
        stop = f", {self.best.stop_pct:.0%} stop" if self.best.stop_pct is not None else ""
        lines = [
            f"best genome: {self.best.family} on {self.best.pair} [{book}{stop}] ({p})",
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
        if self.graduation is not None:
            lines += ["", self.graduation.summary()]
        return "\n".join(lines)


def _score_genome(
    genome: Genome, candles: pd.DataFrame, taker_fee: float, fp: FitnessParams
) -> FitnessResult:
    return evaluate_fitness(
        candles,
        decode(genome),
        taker_fee,
        make_portfolio=decode_portfolio(genome),
        stop_pct=genome.stop_pct,
        folds=fp.folds,
        embargo_bars=fp.embargo_bars,
        min_trades=fp.min_trades,
    )


def fragility_verdict(result: MonteCarloResult, min_fraction_positive: float) -> bool:
    """A genome passes the gate if at least ``min_fraction_positive`` of perturbed runs stay
    positive. A kill-filter, not a green light ([[fragility-stress-test]]): failing rejects the
    genome; passing only means it isn't obviously fragile."""
    return result.fraction_positive >= min_fraction_positive


def discover_universe(
    series: Sequence[tuple[str, str, str]], *, exchange: str, quote: str, timeframe: str
) -> tuple[str, ...]:
    """Chunk N4: auto-build the search universe from what the scraper has stored. Takes the
    ``(exchange, symbol, timeframe)`` rows ``db.list_series`` returns, keeps the ``quote``-quoted
    symbols for this ``exchange``/``timeframe``, and expands their base coins into the full direct +
    ratio universe (``build_universe``). Raises ``SystemExit`` if nothing matches so the run fails
    with a clear message rather than an empty-pool crash."""
    bases = sorted(
        {
            sym.split("/")[0]
            for ex, sym, tf in series
            if ex == exchange and tf == timeframe and sym.endswith(f"/{quote}")
        }
    )
    if not bases:
        raise SystemExit(
            f"no {quote}-quoted {exchange} symbols stored for {timeframe} — run the scraper first"
        )
    return build_universe(bases, quote)


def _preload_universe(
    cache: CandleCache, universe: Sequence[str]
) -> dict[str, pd.DataFrame]:
    """Resolve every ``universe`` pair up front so the per-pair frames can be shipped to worker
    processes (the serial path loads them lazily; parallel needs them all). A pair that fails to
    load becomes an empty frame, which the worker maps to ``-inf`` — the same result the serial
    fitness gives when ``load_candles`` raises."""
    empty = pd.DataFrame({c: [] for c in ("open_time", "open", "high", "low", "close", "volume")})
    frames: dict[str, pd.DataFrame] = {}
    for pair in universe:
        try:
            frames[pair] = cache.get(pair)
        except (ValueError, KeyError):
            frames[pair] = empty
    return frames


def _evolve(
    fitness: Callable[[Genome], float],
    config: GAConfig,
    cache: CandleCache,
    taker_fee: float,
    fitness_params: FitnessParams,
    holdout_fraction: float,
    workers: int,
) -> GAResult:
    """Run the GA serially (``workers == 1``) or fan the fitness map across a process pool. Import
    of the parallel scorer is deferred so the serial path carries no multiprocessing dependency."""
    from coinmon.search.parallel import ParallelScorer, WorkerContext, resolve_workers

    if resolve_workers(workers) == 1:
        return evolve(fitness, config)
    ctx = WorkerContext(
        _preload_universe(cache, config.universe), taker_fee, fitness_params, holdout_fraction
    )
    with ParallelScorer(ctx, workers) as scorer:
        return evolve(fitness, config, score_batch=scorer)


def run_search(
    read: Callable[[str], pd.DataFrame],
    taker_fee: float,
    config: GAConfig,
    *,
    fitness_params: FitnessParams = _DEFAULT_FITNESS,
    fragility_runs: int = 0,
    fragility_min_positive: float = 0.9,
    holdout_fraction: float = 0.0,
    graduate_min_trades: int = 15,
    workers: int = 1,
) -> SearchReport:
    """Run the GA over genomes scored by OOS fitness, then gate the winner.

    With ``holdout_fraction == 0`` (default) this is the chunk-C run: the GA sees the full series
    and the winner faces the fragility kill-filter as a post-filter. With ``holdout_fraction > 0``
    the chunk-D graduation gate engages instead: the last fraction of each pair is carved off
    *before* evolution, the GA scores only the search head, and the winner is graduated on the
    never-seen holdout tail (full fragility + go/no-go). The fragility post-filter is skipped in
    this mode — graduation supersedes it. A genome whose pair has too little data (or any scoring
    error) is assigned ``-inf`` so the GA discards it rather than crashing the run.

    ``workers`` (chunk N2) fans the per-genome fitness map across CPU cores (``<= 0`` = all cores);
    ``1`` (default) keeps the serial path byte-unchanged. The result is identical regardless of
    worker count — only the pure ``genome -> float`` is parallelized, never the RNG stream."""
    cache = CandleCache(read)

    def search_span(pair: str) -> pd.DataFrame:
        frame = cache.get(pair)
        return split_holdout(frame, holdout_fraction)[0] if holdout_fraction else frame

    def fitness(genome: Genome) -> float:
        try:
            result = _score_genome(genome, search_span(genome.pair), taker_fee, fitness_params)
            return result.fitness
        except (ValueError, KeyError):  # too few bars for the folds/embargo, or missing legs
            return float("-inf")

    ga = _evolve(fitness, config, cache, taker_fee, fitness_params, holdout_fraction, workers)
    if ga.best_fitness == float("-inf"):
        raise SystemExit("no genome could be scored — is the candle data present for the UNIVERSE?")

    best_fitness = _score_genome(ga.best, search_span(ga.best.pair), taker_fee, fitness_params)

    fragility: MonteCarloResult | None = None
    passed: bool | None = None
    graduation: GraduationReport | None = None
    if holdout_fraction:
        holdout = split_holdout(cache.get(ga.best.pair), holdout_fraction)[1]
        graduation = graduate(
            ga.best,
            holdout,
            taker_fee,
            fragility_runs=fragility_runs or 200,
            min_fraction_positive=fragility_min_positive,
            min_trades=graduate_min_trades,
        )
    elif fragility_runs:
        build_portfolio = decode_portfolio(ga.best)
        fragility = run_monte_carlo(
            decode(ga.best),
            lambda: build_portfolio(INITIAL_CAPITAL, taker_fee),
            cache.get(ga.best.pair),
            runs=fragility_runs,
            stop_pct=ga.best.stop_pct,
        )
        passed = fragility_verdict(fragility, fragility_min_positive)

    return SearchReport(
        best=ga.best,
        fitness=best_fitness,
        ga=ga,
        fragility=fragility,
        passed_fragility=passed,
        graduation=graduation,
    )
