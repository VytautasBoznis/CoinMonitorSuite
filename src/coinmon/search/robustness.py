from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

import pandas as pd

from coinmon.search.genome import Genome
from coinmon.search.graduation import graduate

# Chunk O: the trust-discriminator. The graduation gate (chunk D) proves a genome held up on its
# OWN pair's unseen holdout — but chunk A found edges are often pair-SPECIFIC
# ([[chunk-a-findings]]),
# and the N6 sweep's GOs hopped pairs by seed like lottery tickets (see
# [[regime-adaptive-multiseed-sweep]]). So a single-pair GO can't tell a structural edge
# from a holdout-luck curve-fit. This module re-runs the SAME genome with its pair gene OVERRIDDEN
# on K-of-N randomly-picked, DECORRELATED pairs and TAGS the result — a classifier, NOT a kill
# filter ([[build-roadmap]] chunk O):
#   golden     — held up (sign/profitability persistence) on >= min_pass of the tested pairs: the
#                edge generalizes across coins, so it's structural and earns core trust.
#   specialist — graduated on its own pair only: a real but pair-tailored edge (chunk A's XRP
#                ratios), kept at lower trust rather than discarded.
# The invariant is sign/profitability persistence (positive return + fragility-positive + clears
# min-trades), NOT a magnitude match: returns don't match across pairs of different volatility, so a
# +/-10% band would reject genuinely robust edges (the metric correction in chunk O's notes). The
# test pairs must be DECORRELATED — three majors crashing together is one test, not three — so the
# pick rejects pairs whose holdout returns are correlated with an already-chosen one.


@dataclass(frozen=True)
class PairVerdict:
    """How the genome fared on one overridden test pair's holdout span. ``passed`` is the same
    graduation go/no-go used on the genome's own pair, so the cross-pair bar is identical."""

    pair: str
    passed: bool
    holdout_return: float
    holdout_trades: int
    fragility_positive: float


@dataclass(frozen=True)
class RobustnessReport:
    """The cross-pair classification of a graduated genome. ``tier`` is ``golden`` when the genome
    held up on at least ``min_pass`` of the tested decorrelated pairs, else ``specialist``."""

    genome: Genome
    verdicts: tuple[PairVerdict, ...]
    pass_count: int
    min_pass: int
    tier: str

    def summary(self) -> str:
        tested = len(self.verdicts)
        lines = [
            f"cross-pair robustness [{self.tier.upper()}] — held on {self.pass_count}/{tested} "
            f"decorrelated pairs (min {self.min_pass} for golden):"
        ]
        for v in self.verdicts:
            mark = "PASS " if v.passed else "NO-GO"
            lines.append(
                f"  {v.pair:<10} [{mark}]  ret {v.holdout_return:+.2%}  "
                f"trades {v.holdout_trades:>3}  frag {v.fragility_positive:.0%}"
            )
        note = (
            "structural edge — generalizes across pairs, core trust"
            if self.tier == "golden"
            else "pair-tailored edge — graduated on its own pair only, conditional trust"
        )
        lines.append(f"  -> tier: {self.tier} ({note})")
        return "\n".join(lines)


def build_robustness_report(
    genome: Genome, verdicts: Sequence[PairVerdict], min_pass: int
) -> RobustnessReport:
    """Tally the per-pair verdicts into a tier. Split out from ``classify_robustness`` so the
    label logic is testable without running backtests."""
    pass_count = sum(1 for v in verdicts if v.passed)
    tier = "golden" if pass_count >= min_pass else "specialist"
    return RobustnessReport(
        genome=genome,
        verdicts=tuple(verdicts),
        pass_count=pass_count,
        min_pass=min_pass,
        tier=tier,
    )


def _abs_corr(a: pd.Series, b: pd.Series) -> float:
    """Absolute return correlation of two pairs over their overlapping bars. NaN (no overlap or a
    flat series) is treated as 0.0 — uninformative, so it doesn't block selection."""
    joined = pd.concat([a, b], axis=1, join="inner").dropna()
    if len(joined) < 2:
        return 0.0
    x, y = joined.iloc[:, 0], joined.iloc[:, 1]
    if x.std() == 0 or y.std() == 0:  # a flat series has no correlation — treat as decorrelated
        return 0.0
    c = x.corr(y)
    return 0.0 if pd.isna(c) else abs(float(c))


def pick_decorrelated_pairs(
    candidates: Sequence[str],
    returns_of: Callable[[str], pd.Series | None],
    n: int,
    *,
    seed: int,
    max_corr: float = 0.7,
) -> tuple[str, ...]:
    """Pick up to ``n`` pairs from ``candidates`` that are mutually decorrelated, so each is an
    independent test of the genome (not the same regime restated). ``returns_of`` maps a pair to its
    holdout return series (or ``None`` if it can't be loaded). The pick is seeded for
    reproducibility: shuffle, then greedily accept a pair only if its absolute return correlation
    with every already-chosen pair is <= ``max_corr``. If decorrelation leaves fewer than ``n``
    (a small/tightly-correlated universe), top up with the remaining usable pairs so the test still
    runs — a thinner-but-honest signal beats none."""
    rng = random.Random(seed)
    order = list(candidates)
    rng.shuffle(order)

    series: dict[str, pd.Series] = {}
    for pair in order:
        r = returns_of(pair)
        if r is not None and len(r.dropna()) >= 2:
            series[pair] = r
    usable = [p for p in order if p in series]

    selected: list[str] = []
    for pair in usable:
        if len(selected) >= n:
            break
        if all(_abs_corr(series[pair], series[q]) <= max_corr for q in selected):
            selected.append(pair)
    if len(selected) < n:
        for pair in usable:
            if len(selected) >= n:
                break
            if pair not in selected:
                selected.append(pair)
    return tuple(selected)


def classify_robustness(
    genome: Genome,
    test_pairs: Sequence[str],
    holdout_of: Callable[[str], pd.DataFrame],
    taker_fee: float,
    *,
    fragility_runs: int,
    min_fraction_positive: float,
    min_trades: int,
    min_pass: int,
) -> RobustnessReport:
    """Re-graduate ``genome`` (pair gene overridden) on each of ``test_pairs`` and tag the result
    golden/specialist. Each pair faces the SAME graduation gate as the genome's own pair, so a
    ``passed`` here means the same sign/profitability-persistence bar held on that pair's unseen
    holdout span. ``holdout_of`` returns the holdout frame for a pair."""
    verdicts = []
    for pair in test_pairs:
        report = graduate(
            replace(genome, pair=pair),
            holdout_of(pair),
            taker_fee,
            fragility_runs=fragility_runs,
            min_fraction_positive=min_fraction_positive,
            min_trades=min_trades,
        )
        verdicts.append(
            PairVerdict(
                pair=pair,
                passed=report.passed,
                holdout_return=report.holdout_return,
                holdout_trades=report.holdout_trades,
                fragility_positive=report.fragility.fraction_positive,
            )
        )
    return build_robustness_report(genome, verdicts, min_pass)
