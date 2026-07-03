from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import pandas as pd

from coinmon.backtest.fitness import FitnessResult, evaluate_fitness
from coinmon.backtest.stress import MonteCarloResult, run_monte_carlo
from coinmon.data.candles import load_candles, split_holdout
from coinmon.data.funding import attach_funding
from coinmon.search.ga import GAConfig, GAResult, evolve
from coinmon.search.genome import (
    FAMILIES,
    Genome,
    build_universe,
    decode,
    decode_portfolio,
    decode_stop,
)
from coinmon.search.graduation import GraduationReport, graduate
from coinmon.search.robustness import (
    RobustnessReport,
    classify_robustness,
    pick_decorrelated_pairs,
)

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
    may be a synthetic ratio (two DB reads); caching avoids re-loading on every evaluation.

    ``read_funding`` (chunk W3 step 2c), when given, attaches a per-bar ``funding_rate`` column to
    each DIRECT perp pair (``attach_funding``) so the carry family is scored with real funding and
    every downstream slice carries it for free. ``None`` (default) leaves frames candle-only —
    every existing search/test path is byte-unchanged."""

    def __init__(
        self,
        read: Callable[[str], pd.DataFrame],
        read_funding: Callable[[str], pd.DataFrame] | None = None,
    ) -> None:
        self._read = read
        self._read_funding = read_funding
        self._cache: dict[str, pd.DataFrame] = {}

    def get(self, pair: str) -> pd.DataFrame:
        if pair not in self._cache:
            frame = load_candles(self._read, pair)
            if self._read_funding is not None:
                frame = attach_funding(frame, pair, self._read_funding)
            self._cache[pair] = frame
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
    robustness: RobustnessReport | None = None

    def summary(self) -> str:
        # A family may render its params as a readable rule (chunk P's combo, whose flat genes are
        # opaque); otherwise fall back to the raw key=value dump.
        describe = FAMILIES[self.best.family].describe
        p = (
            describe(self.best.params)
            if describe is not None
            else ", ".join(f"{k}={v:g}" for k, v in sorted(self.best.params.items()))
        )
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
        if self.robustness is not None:
            lines += ["", self.robustness.summary()]
        return "\n".join(lines)


def _score_genome(
    genome: Genome, candles: pd.DataFrame, taker_fee: float, fp: FitnessParams
) -> FitnessResult:
    return evaluate_fitness(
        candles,
        decode(genome),
        taker_fee,
        make_portfolio=decode_portfolio(genome),
        stop_pct=decode_stop(genome),
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
    cross_pair_n: int = 0,
    cross_pair_min: int = 3,
    cross_pair_max_corr: float = 0.7,
    workers: int = 1,
    cache: CandleCache | None = None,
    read_funding: Callable[[str], pd.DataFrame] | None = None,
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
    worker count — only the pure ``genome -> float`` is parallelized, never the RNG stream.

    ``cross_pair_n`` (chunk O) enables the cross-pair robustness classifier: after a winner
    GRADUATES GO, the SAME genome (pair gene overridden) is re-graduated on ``cross_pair_n``
    randomly-picked DECORRELATED pairs and TAGGED ``golden`` (held up on >= ``cross_pair_min`` of
    them, a structural edge) or ``specialist`` (its own pair only, a pair-tailored edge). It only
    classifies a GO and never changes the go/no-go — a trust label, not a kill gate. ``0`` (default)
    skips it (chunk-N behavior unchanged).

    ``cache`` lets a caller (the multi-seed sweep) share one resolved-candle cache across runs so
    the DB is read once, not once per seed; default ``None`` builds a fresh cache (unchanged).
    ``read_funding`` (chunk W3 step 2c) is threaded into that fresh cache so the carry family is
    scored with real per-bar funding; ``None`` (default) keeps every frame candle-only. It is
    ignored when a pre-built ``cache`` is supplied (the caller owns that cache's funding wiring)."""
    cache = cache if cache is not None else CandleCache(read, read_funding)

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
    robustness: RobustnessReport | None = None
    if holdout_fraction:
        fragility_runs = fragility_runs or 200

        def holdout_of(pair: str) -> pd.DataFrame:
            return split_holdout(cache.get(pair), holdout_fraction)[1]

        graduation = graduate(
            ga.best,
            holdout_of(ga.best.pair),
            taker_fee,
            fragility_runs=fragility_runs,
            min_fraction_positive=fragility_min_positive,
            min_trades=graduate_min_trades,
        )
        if cross_pair_n and graduation.passed:
            robustness = _classify_cross_pair(
                ga.best,
                config,
                holdout_of,
                taker_fee,
                fragility_runs=fragility_runs,
                fragility_min_positive=fragility_min_positive,
                graduate_min_trades=graduate_min_trades,
                cross_pair_n=cross_pair_n,
                cross_pair_min=cross_pair_min,
                cross_pair_max_corr=cross_pair_max_corr,
            )
    elif fragility_runs:
        build_portfolio = decode_portfolio(ga.best)
        fragility = run_monte_carlo(
            decode(ga.best),
            lambda: build_portfolio(INITIAL_CAPITAL, taker_fee),
            cache.get(ga.best.pair),
            runs=fragility_runs,
            stop_pct=decode_stop(ga.best),
        )
        passed = fragility_verdict(fragility, fragility_min_positive)

    return SearchReport(
        best=ga.best,
        fitness=best_fitness,
        ga=ga,
        fragility=fragility,
        passed_fragility=passed,
        graduation=graduation,
        robustness=robustness,
    )


def _classify_cross_pair(
    genome: Genome,
    config: GAConfig,
    holdout_of: Callable[[str], pd.DataFrame],
    taker_fee: float,
    *,
    fragility_runs: int,
    fragility_min_positive: float,
    graduate_min_trades: int,
    cross_pair_n: int,
    cross_pair_min: int,
    cross_pair_max_corr: float,
) -> RobustnessReport:
    """Chunk O: tag a graduated winner golden/specialist by re-graduating it on decorrelated peer
    pairs. Picks the test pairs from the search universe (the genome's own pair excluded — it
    already graduated) by holdout-return decorrelation, then runs the same gate on each."""
    candidates = [p for p in config.universe if p != genome.pair]

    def returns_of(pair: str) -> pd.Series | None:
        try:
            holdout = holdout_of(pair)
        except (ValueError, KeyError):
            return None
        if holdout.empty:
            return None
        return holdout.set_index("open_time")["close"].pct_change()

    test_pairs = pick_decorrelated_pairs(
        candidates, returns_of, cross_pair_n, seed=config.seed, max_corr=cross_pair_max_corr
    )
    return classify_robustness(
        genome,
        test_pairs,
        holdout_of,
        taker_fee,
        fragility_runs=fragility_runs,
        min_fraction_positive=fragility_min_positive,
        min_trades=graduate_min_trades,
        min_pass=cross_pair_min,
    )


# Chunk N6 — the payoff test. A single search is one draw from a noisy process: its winner is the
# luckiest genome on one seed's RNG stream. The multi-seed sweep runs the SAME graduation search
# across many seeds and asks the question N4's scale made urgent (see
# [[regime-adaptive-multiseed-sweep]], [[search-overfits-not-strategy]]): do the GOs name a
# CONSISTENT structural edge, or do they hop pairs/families by seed like lottery tickets? It adds
# no new gate — it just measures how the already-validated judge behaves under repetition, so a
# future O can decide what to trust.


@dataclass(frozen=True)
class SweepRow:
    """One seed's graduation verdict, flattened for aggregation. Pulled from a holdout
    ``SearchReport`` so the summary needs none of the heavy GA/fitness objects."""

    seed: int
    passed: bool
    family: str
    pair: str
    direction: str
    holdout_return: float
    holdout_trades: int
    fragility_positive: float
    benchmark_return: float
    tier: str | None = None  # chunk O cross-pair tag (golden/specialist); None if not classified


def sweep_row(seed: int, report: SearchReport) -> SweepRow:
    """Flatten a holdout ``SearchReport`` into a ``SweepRow``. Requires the graduation gate to have
    run (``holdout_fraction > 0``) — a sweep without a verdict has nothing to aggregate. Carries the
    chunk-O cross-pair ``tier`` when the winner was classified (``None`` for a NO-GO or when the
    sweep ran without ``--cross-pair``)."""
    g = report.graduation
    if g is None:
        raise ValueError("sweep_row needs a graduated report (run the sweep with a holdout)")
    return SweepRow(
        seed=seed,
        passed=g.passed,
        family=g.genome.family,
        pair=g.genome.pair,
        direction=g.genome.direction,
        holdout_return=g.holdout_return,
        holdout_trades=g.holdout_trades,
        fragility_positive=g.fragility.fraction_positive,
        benchmark_return=g.benchmark_return,
        tier=report.robustness.tier if report.robustness is not None else None,
    )


def summarize_sweep(rows: Sequence[SweepRow]) -> str:
    """Aggregate a multi-seed sweep into a verdict table + the lottery-vs-edge diagnosis. A
    structural edge GOs on the SAME pair across seeds; a curve-fit GOs on a DIFFERENT pair each
    time — so the headline counts GO seeds AND the distinct pairs those GOs land on."""
    lines = ["multi-seed sweep — graduation verdict per seed:"]
    for r in sorted(rows, key=lambda x: x.seed):
        verdict = "GO   " if r.passed else "NO-GO"
        tier = f"  [{r.tier.upper()}]" if r.tier else ""
        lines.append(
            f"  seed {r.seed:>3}  [{verdict}]  {r.family} on {r.pair} ({r.direction})  "
            f"ret {r.holdout_return:+.2%}  trades {r.holdout_trades:>3}  "
            f"frag {r.fragility_positive:.0%}  (B&H {r.benchmark_return:+.2%}){tier}"
        )
    gos = [r for r in rows if r.passed]
    lines.append("")
    lines.append(f"GO: {len(gos)}/{len(rows)} seeds")
    if gos:
        go_pairs = sorted({r.pair for r in gos})
        returns = sorted(r.holdout_return for r in gos)
        median = returns[len(returns) // 2]
        lines.append(
            f"  GOs span {len(go_pairs)} distinct pair(s): {', '.join(go_pairs)}"
            + ("  (one pair across seeds = consistent; many = lottery)" if len(gos) > 1 else "")
        )
        lines.append(
            f"  GO holdout return: median {median:+.2%}, "
            f"range {returns[0]:+.2%}..{returns[-1]:+.2%}"
        )
        # Chunk O tier aggregation: golden (structural — held up on K-of-N decorrelated peers)
        # vs specialist (own pair only). Surfaced only when --cross-pair tagged the GOs.
        tagged = [r.tier for r in gos if r.tier]
        if tagged:
            golden = tagged.count("golden")
            specialist = tagged.count("specialist")
            lines.append(
                f"  tiers: {golden} golden, {specialist} specialist  "
                "(golden = structural, generalizes across peers; specialist = own pair only)"
            )
    return "\n".join(lines)
