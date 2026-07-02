from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import pandas as pd

from coinmon.search.evidence import build_evidence, pool_trades
from coinmon.search.ga import random_genome
from coinmon.search.genome import UNIVERSE, Genome

# Chunk V — null calibration (the certificate's C4, see .claude/plans/alpha-hunt.md §V). The Edge
# Certificate (chunk U) can measure that a frozen genome's pooled OOS ledger is profitable and
# stable, but it cannot on its own answer the only question that matters after a big search: is the
# winner a real edge, or the luckiest of thousands of tries? A 30-seed x pop-300 x 80-gen search
# over correlated pairs manufactures a high score from noise alone; without a null distribution to
# compare against, "beats zero" is not "beats chance". This module builds that null.
#
# THIS FILE = V1, the random-genome null (the cheapest and most fundamental of the plan's three):
# sample M genomes uniformly at random (no evolution), score each by the SAME pooled-ledger
# certificate statistic (t_exp) over the SAME evaluation grid, and compare the candidate against
# the distribution of the BEST-of-M random tries. The real search SELECTS its winner from many
# genomes, so the fair null for a selected statistic is the distribution of the selected statistic
# under the null — the maximum, not a single random draw. This same run doubles as the standing
# "is the GA even beating random search?" audit the plan's §4 demands: at <=10 dims, if evolved
# winners don't clear best-of-M-random, run random search and save the compute.
#
# (V2 exposure-matched random-entry null and V3 surrogate-data null are separate sub-chunks — they
# need per-pair duration mechanics / a full re-search on signal-destroyed data respectively.)


@dataclass(frozen=True)
class NullResult:
    """A candidate's certificate score judged against a null distribution. ``beaten`` — the value
    C4 consumes — is ``candidate_score > percentile`` (the candidate clears the null's upper tail).
    ``null_scores`` are the raw per-random-genome scores; ``percentile`` is the bootstrapped
    best-of-M upper tail the candidate must exceed."""

    mode: str
    candidate_score: float
    null_scores: tuple[float, ...]
    percentile: float
    quantile: float
    beaten: bool

    @property
    def n_samples(self) -> int:
        return len(self.null_scores)

    def summary(self) -> str:
        finite = [s for s in self.null_scores if math.isfinite(s)]
        best = max(finite) if finite else float("nan")
        return "\n".join(
            [
                f"Null calibration [{self.mode}] - {'BEATS' if self.beaten else 'does NOT beat'} "
                "the null:",
                f"  candidate score (t_exp)  {self.candidate_score:+.3f}",
                f"  random genomes scored     {len(finite)}/{self.n_samples} finite",
                f"  best random score         {best:+.3f}",
                f"  null {self.quantile:.0%} threshold      {self.percentile:+.3f}",
                f"  verdict                   candidate {'>' if self.beaten else '<='} threshold "
                f"-> C4 {'PASS' if self.beaten else 'FAIL'}",
            ]
        )

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "candidate_score": self.candidate_score,
            "null_scores": list(self.null_scores),
            "percentile": self.percentile,
            "quantile": self.quantile,
            "beaten": self.beaten,
        }

    @classmethod
    def from_dict(cls, data: dict) -> NullResult:
        return cls(
            mode=data["mode"],
            candidate_score=data["candidate_score"],
            null_scores=tuple(data["null_scores"]),
            percentile=data["percentile"],
            quantile=data["quantile"],
            beaten=data["beaten"],
        )


def null_from_scores(
    candidate_score: float,
    sample_scores: Sequence[float],
    *,
    mode: str = "random",
    seed: int = 0,
    resamples: int = 2000,
    quantile: float = 0.95,
) -> NullResult:
    """Reduce a candidate score + a sample of random-genome scores to a verdict. Pure — so it is
    unit-testable without any DB or engine. The null distribution is the BOOTSTRAPPED MAXIMUM: each
    resample draws M scores with replacement from the sample and keeps the max, approximating the
    sampling distribution of the best-of-M random tries (the White's-Reality-Check correction for
    selecting a winner from many genomes). ``beaten`` = candidate clears the ``quantile`` upper
    tail. With no finite sample scores the null can't be formed, so the threshold is +inf (never
    beaten)."""
    finite = [s for s in sample_scores if math.isfinite(s)]
    if not finite:
        return NullResult(
            mode=mode,
            candidate_score=candidate_score,
            null_scores=tuple(sample_scores),
            percentile=float("inf"),
            quantile=quantile,
            beaten=False,
        )
    rng = random.Random(seed)
    m = len(finite)
    maxes = sorted(max(rng.choice(finite) for _ in range(m)) for _ in range(resamples))
    idx = min(resamples - 1, int(quantile * resamples))
    percentile = maxes[idx]
    return NullResult(
        mode=mode,
        candidate_score=candidate_score,
        null_scores=tuple(sample_scores),
        percentile=percentile,
        quantile=quantile,
        beaten=candidate_score > percentile,
    )


def random_genome_null(
    candidate_score: float,
    read: Callable[[str], pd.DataFrame],
    taker_fee: float,
    eval_pairs: Sequence[str],
    *,
    universe: Sequence[str] = UNIVERSE,
    n_genomes: int = 50,
    sample_seed: int = 0,
    boot_seed: int = 0,
    boot_resamples: int = 2000,
    evidence_resamples: int = 2000,
    n_regimes: int = 2,
    window_size: float = 0.6,
    step: float = 0.2,
    holdout_fraction: float = 0.2,
    quantile: float = 0.95,
    score_genome: Callable[[Genome], float] | None = None,
) -> NullResult:
    """Sample ``n_genomes`` uniformly-random genomes and score each by the certificate statistic
    (``t_exp`` of its pooled OOS ledger) over the SAME ``eval_pairs`` and window/holdout grid the
    candidate was measured on, then judge the candidate against the best-of-M null (see
    ``null_from_scores``). ``score_genome`` is injectable so tests can drive it without a DB;
    the default pools each genome exactly as ``pool_trades`` + ``build_evidence`` do for the
    candidate, so candidate and nulls are scored by an identical protocol (a fair comparison)."""
    if score_genome is None:

        def score_genome(genome: Genome) -> float:
            trades = pool_trades(
                genome,
                read,
                taker_fee,
                eval_pairs,
                window_size=window_size,
                step=step,
                holdout_fraction=holdout_fraction,
            )
            return build_evidence(
                trades, seed=boot_seed, resamples=evidence_resamples, n_regimes=n_regimes
            ).t_exp

    rng = random.Random(sample_seed)
    sample_scores = [score_genome(random_genome(rng, universe)) for _ in range(n_genomes)]
    return null_from_scores(
        candidate_score,
        sample_scores,
        mode="random",
        seed=boot_seed,
        resamples=boot_resamples,
        quantile=quantile,
    )
