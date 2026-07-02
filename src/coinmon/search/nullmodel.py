from __future__ import annotations

import math
import random
import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import pandas as pd

from coinmon.backtest.portfolio import Portfolio
from coinmon.search.evidence import (
    INITIAL_CAPITAL,
    EvalSegment,
    build_evidence,
    pool_trades,
)
from coinmon.search.ga import random_genome
from coinmon.search.genome import UNIVERSE, Genome

# Chunk V — null calibration (the certificate's C4, see .claude/plans/alpha-hunt.md §V). The Edge
# Certificate (chunk U) can measure that a frozen genome's pooled OOS ledger is profitable and
# stable, but it cannot on its own answer the only question that matters after a big search: is the
# winner a real edge, or the luckiest of thousands of tries? A 30-seed x pop-300 x 80-gen search
# over correlated pairs manufactures a high score from noise alone; without a null distribution to
# compare against, "beats zero" is not "beats chance". This module builds that null.
#
# V1 = the random-genome null (the cheapest and most fundamental of the plan's three): sample M
# genomes uniformly at random (no evolution), score each by the SAME pooled-ledger certificate
# statistic (t_exp) over the SAME evaluation grid, and compare the candidate against the
# distribution of the BEST-of-M random tries. The real search SELECTS its winner from many genomes,
# so the fair null for a selected statistic is the distribution of the selected statistic under the
# null — the maximum, not a single random draw (``null_from_scores``). This doubles as the standing
# "is the GA even beating random search?" audit the plan's §4 demands.
#
# V2 = the exposure-matched random-entry null (``random_entry_null``): given the candidate's own OOS
# ledger, replay the SAME number of trades, the SAME holding-duration distribution and the SAME
# direction mix — but at RANDOM entry times — on the very same OOS series, R times, and ask whether
# the candidate's expectancy clears the 95th percentile of that matched-random distribution. This is
# the per-candidate null that kills "beta dressed as alpha" (profitable only by being long through a
# bull tail / short through a bleed) — the failure mode behind every prior GO. Unlike V1 there is no
# selection, so the null is the DIRECT distribution's upper tail (``null_from_distribution``), not a
# best-of-M maximum, and the statistic compared is expectancy (per the plan §V.2), not t_exp.
#
# (V3 surrogate-data null — a full re-search on signal-destroyed data — is a separate sub-chunk.)


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
                f"  candidate score           {self.candidate_score:+.3f}",
                f"  null samples scored        {len(finite)}/{self.n_samples} finite",
                f"  best null sample           {best:+.3f}",
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


def null_from_distribution(
    candidate_score: float,
    sample_scores: Sequence[float],
    *,
    mode: str = "matched",
    quantile: float = 0.95,
) -> NullResult:
    """Reduce a candidate score + a DIRECT null distribution (chunk V2: one score per matched-random
    resample) to a verdict. Unlike ``null_from_scores`` there is no best-of-M bootstrap — the
    candidate wasn't selected from these samples, so the null is the distribution's own ``quantile``
    upper tail. Pure, so it is unit-testable without any engine. With no finite sample the threshold
    is +inf (never beaten)."""
    finite = sorted(s for s in sample_scores if math.isfinite(s))
    if not finite:
        return NullResult(
            mode=mode,
            candidate_score=candidate_score,
            null_scores=tuple(sample_scores),
            percentile=float("inf"),
            quantile=quantile,
            beaten=False,
        )
    idx = min(len(finite) - 1, int(quantile * len(finite)))
    percentile = finite[idx]
    return NullResult(
        mode=mode,
        candidate_score=candidate_score,
        null_scores=tuple(sample_scores),
        percentile=percentile,
        quantile=quantile,
        beaten=candidate_score > percentile,
    )


def _synthetic_return(
    build_portfolio: Callable[[float, float], Portfolio],
    taker_fee: float,
    opens: Sequence[float],
    closes: Sequence[float],
    entry_idx: int,
    duration: int,
    direction: int,
) -> float:
    """Net per-trade return of ONE random-entry trade that enters at ``opens[entry_idx]``, is marked
    (for liquidation) at each held bar's close, and exits ``duration`` bars later at its open —
    computed through the genome's OWN portfolio (``build_portfolio``), so leverage, fee legs and
    isolated-margin liquidation match the engine's economics EXACTLY (no re-derived formula to drift
    from). Mirrors ``BarStepper``: fill at open, mark closes[entry_idx .. entry_idx+duration-1],
    then close at the exit bar's open. A fresh portfolio per trade makes the result the scale-free
    per-collateral return the ledger records."""
    portfolio = build_portfolio(INITIAL_CAPITAL, taker_fee)
    portfolio.rebalance(direction, opens[entry_idx])
    for k in range(entry_idx, entry_idx + duration):
        portfolio.equity(closes[k])  # latch a liquidation the way the engine marks each bar close
    portfolio.rebalance(0, opens[entry_idx + duration])
    return portfolio.closed_trades[-1].net_return_pct


def random_entry_null(
    candidate_expectancy: float,
    segments: Sequence[EvalSegment],
    build_portfolio: Callable[[float, float], Portfolio],
    taker_fee: float,
    *,
    resamples: int = 1000,
    seed: int = 0,
    quantile: float = 0.95,
) -> NullResult:
    """The exposure-matched random-entry null (chunk V2). For each of ``resamples`` draws, replay
    every one of the candidate's closed trades — keeping its segment, direction and holding duration
    but drawing a fresh RANDOM entry bar (uniform over the placements that fit the duration) — pool
    the synthetic per-trade returns, and take that pool's expectancy. The candidate's expectancy
    must clear the ``quantile`` upper tail of that distribution (via ``null_from_distribution``) to
    earn C4: an edge that's only market exposure in disguise scores no better than random entry with
    the same footprint."""
    rng = random.Random(seed)
    sample_scores: list[float] = []
    for _ in range(resamples):
        rets: list[float] = []
        for seg in segments:
            n = len(seg.opens)
            for direction, duration in seg.trades:
                entry_idx = rng.randint(0, n - 1 - duration)  # room for the full hold
                rets.append(
                    _synthetic_return(
                        build_portfolio, taker_fee,
                        seg.opens, seg.closes, entry_idx, duration, direction,
                    )
                )
        if rets:
            sample_scores.append(statistics.fmean(rets))
    return null_from_distribution(
        candidate_expectancy, sample_scores, mode="matched", quantile=quantile
    )
