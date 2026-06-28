from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass

import pandas as pd

from coinmon.data.candles import split_holdout
from coinmon.search.genome import Genome
from coinmon.search.runner import FitnessParams, _score_genome

# Chunk N2: CPU multiprocessing for the GA's per-genome fitness map. Determinism is preserved by
# construction — the GA's RNG stream stays serial in the parent (ga.evolve); only the pure,
# RNG-free ``genome -> float`` is fanned across processes here, and the map is order-preserving, so
# a parallel run is bit-identical to serial.
#
# Windows uses the spawn start method, so workers can't inherit the parent's DB connection or candle
# cache. Instead the parent preloads every UNIVERSE pair into a plain dict of DataFrames (picklable)
# and ships it once per worker via the pool initializer — "reload candles from DB" reduced to "send
# the already-loaded candles," which is cheap for the small daily universe and removes the DB from
# the workers entirely. The scoring itself reuses the runner's exact ``_score_genome`` so a worker
# computes the same number the serial path would.


@dataclass(frozen=True)
class WorkerContext:
    """Everything a worker needs to score a genome — the same inputs the serial ``fitness`` closure
    in the runner captures, but picklable so they can cross the process boundary. ``candles`` is the
    full per-pair frame; the worker carves the search head itself (matching the serial path)."""

    candles: dict[str, pd.DataFrame]
    taker_fee: float
    fitness_params: FitnessParams
    holdout_fraction: float


# Set once per worker process by the pool initializer; read by ``_score_one``. A module global is
# how the spawn start method hands per-worker state to the mapped function without re-pickling it on
# every call.
_CTX: WorkerContext | None = None


def _init(ctx: WorkerContext) -> None:
    global _CTX
    _CTX = ctx


def _score_one(genome: Genome) -> float:
    """Score one genome in a worker — a mirror of the runner's serial ``fitness``: resolve the
    pair's search span, evaluate OOS fitness, and map a too-short series or missing leg to ``-inf``
    (so the GA discards it) exactly as the serial path does."""
    ctx = _CTX
    assert ctx is not None  # set by _init before any task runs
    frame = ctx.candles.get(genome.pair)
    if frame is None or frame.empty:
        return float("-inf")
    span = split_holdout(frame, ctx.holdout_fraction)[0] if ctx.holdout_fraction else frame
    try:
        return _score_genome(genome, span, ctx.taker_fee, ctx.fitness_params).fitness
    except (ValueError, KeyError):  # too few bars for the folds/embargo, or missing legs
        return float("-inf")


def resolve_workers(workers: int) -> int:
    """``workers <= 0`` means "all cores"; otherwise the requested count (clamped to >= 1)."""
    return max(1, os.cpu_count() or 1) if workers <= 0 else max(1, workers)


class ParallelScorer:
    """A ``score_batch`` for ``ga.evolve`` backed by a process pool. Use as a context manager so
    the pool is created once for the whole run (not per generation) and shut down cleanly. The map
    preserves input order, which is what keeps the GA deterministic across worker counts."""

    def __init__(self, ctx: WorkerContext, workers: int) -> None:
        self._ctx = ctx
        self._workers = resolve_workers(workers)
        self._pool: ProcessPoolExecutor | None = None

    def __enter__(self) -> ParallelScorer:
        self._pool = ProcessPoolExecutor(
            max_workers=self._workers, initializer=_init, initargs=(self._ctx,)
        )
        return self

    def __exit__(self, *exc: object) -> bool:
        assert self._pool is not None
        self._pool.shutdown()
        self._pool = None
        return False

    def __call__(self, genomes: list[Genome]) -> list[float]:
        assert self._pool is not None  # only callable inside the context
        return list(self._pool.map(_score_one, genomes))
