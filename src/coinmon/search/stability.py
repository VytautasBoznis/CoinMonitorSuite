from __future__ import annotations

import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import pandas as pd

from coinmon.data.candles import load_candles, split_holdout
from coinmon.data.funding import attach_funding
from coinmon.search.ga import GAConfig
from coinmon.search.genome import FAMILIES, Genome
from coinmon.search.graduation import GraduationReport, graduate
from coinmon.search.runner import (
    _DEFAULT_FITNESS,
    FitnessParams,
    SearchReport,
    run_search,
)

# Walk-forward parameter stability. The nested holdout ([[nested-holdout-refutes-golden]]) showed
# the binding failure mode of this whole project in one shot: move the holdout window earlier and
# the "convergent" golden genome vanishes, and a genome that passed the gate on one window bought
# ZERO edge on the next. This module turns that one-shot finding into a rolling diagnostic: re-run
# the ENTIRE selection process (GA -> graduation, via the unchanged ``run_search``) on a sequence of
# windows stepping through time, then measure two things an overfit search betrays and a structural
# edge survives:
#   1. SELECTION AGREEMENT — do the winners look alike across windows (same family/pair/direction,
#      nearby params)? A curve-fit hops; an edge recurs.
#   2. FORWARD PERSISTENCE — does a window's frozen winner still GO on the NEXT window's holdout
#      (genuinely later, unseen bars)? Passing the gate on window i must buy edge on window i+1, or
#      "passed the gate" means nothing (exactly the 0/2 the nested holdout found).
# It adds NO new gate and changes no verdict — it only measures how the already-validated judge
# behaves as the clock advances, so we can tell a stable edge from a holdout-luck artifact.

INITIAL_CAPITAL = 10_000.0


def window_bounds(
    window_size: float, step: float, n_windows: int | None = None
) -> list[tuple[float, float]]:
    """Rolling fractional windows over a series: ``(lo, hi)`` pairs in [0, 1], each ``window_size``
    wide, advancing by ``step``. ``step <= window_size`` so consecutive windows overlap (an edge
    should survive the overlap; the non-overlapping tail is the genuine forward test). Stops at the
    last window that fits inside [0, 1], or after ``n_windows`` if given. Fractions, not bar counts,
    so every pair is sliced proportionally regardless of its own length."""
    if not 0.0 < window_size <= 1.0:
        raise ValueError(f"window_size must be in (0, 1], got {window_size}")
    if not 0.0 < step <= window_size:
        raise ValueError(f"step must be in (0, window_size], got {step}")
    bounds: list[tuple[float, float]] = []
    lo = 0.0
    while lo + window_size <= 1.0 + 1e-9:
        bounds.append((round(lo, 10), round(min(lo + window_size, 1.0), 10)))
        if n_windows is not None and len(bounds) >= n_windows:
            break
        lo += step
    return bounds


def _slice(frame: pd.DataFrame, lo: float, hi: float) -> pd.DataFrame:
    """Carve the fractional ``[lo, hi)`` slice of a series, index reset so it stands alone."""
    n = len(frame)
    return frame.iloc[int(n * lo) : int(n * hi)].reset_index(drop=True)


@dataclass(frozen=True)
class StabilityWindow:
    """One window's full search verdict (the winner + its graduation), tagged with the window's
    fractional bounds so the report can show how the choice moved as the clock advanced."""

    index: int
    lo: float
    hi: float
    report: SearchReport

    @property
    def winner(self) -> Genome:
        return self.report.best

    @property
    def passed(self) -> bool:
        g = self.report.graduation
        return bool(g and g.passed)


@dataclass(frozen=True)
class ForwardStep:
    """Window ``from_index``'s frozen winner re-graduated on window ``to_index``'s holdout — the
    later, unseen bars. ``persisted`` is the gate's go/no-go on that next window."""

    from_index: int
    to_index: int
    from_passed: bool  # did the winner GO on its OWN window? (the interesting subset)
    graduation: GraduationReport

    @property
    def persisted(self) -> bool:
        return self.graduation.passed


@dataclass
class StabilityReport:
    windows: list[StabilityWindow]
    forward: list[ForwardStep]

    def summary(self) -> str:
        lines = ["walk-forward stability — full search re-run per window:"]
        for w in self.windows:
            verdict = "GO   " if w.passed else "NO-GO"
            g = w.winner
            book = "adaptive" if g.direction == "adaptive" else "long"
            grad = w.report.graduation
            ret = f"{grad.holdout_return:+.2%}" if grad else "n/a"
            trades = grad.holdout_trades if grad else 0
            lines.append(
                f"  win {w.index} [{w.lo:.2f}-{w.hi:.2f}]  [{verdict}]  "
                f"{g.family} on {g.pair} ({book})  holdout {ret}  trades {trades:>3}"
            )

        lines += ["", _selection_summary(self.windows), "", _forward_summary(self.forward)]
        return "\n".join(lines)


def param_drift(a: Genome, b: Genome) -> float | None:
    """Normalized param distance between two SAME-FAMILY genomes: mean over the family's params of
    ``|a - b| / range``, so 0 = identical and 1 = opposite corners of the search box, comparable
    across params on different scales. ``None`` when the families differ (params aren't comparable —
    a family switch is itself maximal instability, counted separately)."""
    if a.family != b.family:
        return None
    specs = FAMILIES[a.family].params
    dists = [
        abs(a.params[name] - b.params[name]) / (spec.high - spec.low)
        for name, spec in specs.items()
        if spec.high > spec.low
    ]
    return statistics.fmean(dists) if dists else 0.0


def _selection_summary(windows: Sequence[StabilityWindow]) -> str:
    """SELECTION AGREEMENT: do the per-window winners recur, or hop? A structural edge keeps naming
    the same family/pair; a curve-fit picks a new one each window. Also reports the mean param drift
    between consecutive winners that DID keep the family (in-family wandering is overfit too)."""
    winners = [w.winner for w in windows]
    n = len(winners)
    families = [g.family for g in winners]
    pairs = [g.pair for g in winners]
    directions = [g.direction for g in winners]

    def modal(items: list[str]) -> tuple[str, int]:
        top = max(set(items), key=items.count)
        return top, items.count(top)

    fam_top, fam_n = modal(families)
    pair_top, pair_n = modal(pairs)

    # Param drift only where the family held across the step (else a switch — counted as a hop).
    drifts = [
        d
        for a, b in zip(winners, winners[1:], strict=False)
        if (d := param_drift(a, b)) is not None
    ]
    switches = (n - 1) - len(drifts)
    switch_line = (
        f"  family switches    {switches}/{n - 1} steps"
        if n > 1
        else "  family switches    n/a"
    )
    drift_line = (
        f"  param drift (same-family steps)  {statistics.fmean(drifts):.2f}  "
        f"(0 = identical, 1 = opposite corners)"
        if drifts
        else "  param drift (same-family steps)  n/a  (no two consecutive windows shared a family)"
    )

    return "\n".join(
        [
            "selection agreement across windows:",
            f"  distinct families  {len(set(families))}/{n}  "
            f"(most common: {fam_top} x{fam_n})",
            f"  distinct pairs     {len(set(pairs))}/{n}  (most common: {pair_top} x{pair_n})",
            f"  distinct directions {len(set(directions))}/{n}",
            switch_line,
            drift_line,
        ]
    )


def _forward_summary(forward: Sequence[ForwardStep]) -> str:
    """FORWARD PERSISTENCE: of the winners that GO'd on their own window, how many still GO on the
    next window's later, unseen bars? This is the metric the nested holdout failed (0/2). A low
    ratio means 'passed the gate' does not predict the next regime — the core open question."""
    if not forward:
        return "forward persistence: n/a (need >= 2 windows)"
    go_steps = [s for s in forward if s.from_passed]
    lines = ["forward persistence (each window's winner on the NEXT window's holdout):"]
    for s in forward:
        own = "GO   " if s.from_passed else "NO-GO"
        nxt = "GO   " if s.persisted else "NO-GO"
        g = s.graduation
        lines.append(
            f"  win {s.from_index}->{s.to_index}  own [{own}]  next [{nxt}]  "
            f"ret {g.holdout_return:+.2%}  trades {g.holdout_trades:>3}  "
            f"(B&H {g.benchmark_return:+.2%})"
        )
    persisted = sum(1 for s in go_steps if s.persisted)
    lines.append("")
    if go_steps:
        lines.append(
            f"  of GO winners, {persisted}/{len(go_steps)} still GO one window forward  "
            "(low = 'passed the gate' doesn't predict the next regime)"
        )
    else:
        lines.append("  no window produced a GO winner — nothing to carry forward")
    return "\n".join(lines)


def run_stability(
    read: Callable[[str], pd.DataFrame],
    taker_fee: float,
    config: GAConfig,
    *,
    holdout_fraction: float,
    window_size: float = 0.6,
    step: float = 0.2,
    n_windows: int | None = None,
    fitness_params: FitnessParams = _DEFAULT_FITNESS,
    fragility_runs: int = 0,
    fragility_min_positive: float = 0.9,
    graduate_min_trades: int = 15,
    workers: int = 1,
    read_funding: Callable[[str], pd.DataFrame] | None = None,
) -> StabilityReport:
    """Run the full graduation search (``run_search``) on each rolling window of the data, then
    measure selection agreement + forward persistence (see module header).

    Each window is the fractional ``[lo, hi)`` slice of every series; ``run_search`` carves that
    window's own ``holdout_fraction`` tail as its graduation holdout, exactly as a normal search
    does — so each window is an honest, self-contained selection. Forward persistence then takes
    window ``i``'s winner and runs the graduation gate on window ``i+1``'s holdout (later, unseen
    bars), reusing the same ``graduate`` the search trusts.

    ``window_size``/``step`` are FRACTIONS of each series (defaults: 60% windows advancing 20%, so
    a 14-base daily DB of ~600 bars gives ~3 windows of ~360 bars). The window must be wide enough
    that ``(1 - holdout_fraction) * window_size`` of a pair still spans the fitness folds, or every
    genome scores ``-inf`` and ``run_search`` fails loudly — the signal that the windows are thin.
    """
    if not 0.0 < holdout_fraction < 1.0:
        raise ValueError(f"holdout_fraction must be in (0, 1), got {holdout_fraction}")
    fragility_runs = fragility_runs or 200
    cache: dict[str, pd.DataFrame] = {}  # resolved per-pair frames, for the forward holdouts

    def resolve(pair: str) -> pd.DataFrame:
        if pair not in cache:
            frame = load_candles(read, pair)
            if read_funding is not None:  # forward-holdout carry winners need funding too (W3 2c)
                frame = attach_funding(frame, pair, read_funding)
            cache[pair] = frame
        return cache[pair]

    bounds = window_bounds(window_size, step, n_windows)
    windows: list[StabilityWindow] = []
    for index, (lo, hi) in enumerate(bounds):

        def windowed_read(symbol: str, lo: float = lo, hi: float = hi) -> pd.DataFrame:
            return _slice(read(symbol), lo, hi)

        report = run_search(
            windowed_read,
            taker_fee,
            config,
            fitness_params=fitness_params,
            fragility_runs=fragility_runs,
            fragility_min_positive=fragility_min_positive,
            holdout_fraction=holdout_fraction,
            graduate_min_trades=graduate_min_trades,
            workers=workers,
            read_funding=read_funding,
        )
        windows.append(StabilityWindow(index=index, lo=lo, hi=hi, report=report))

    forward: list[ForwardStep] = []
    for prev, nxt in zip(windows, windows[1:], strict=False):
        winner = prev.winner
        next_window = _slice(resolve(winner.pair), nxt.lo, nxt.hi)
        next_holdout = split_holdout(next_window, holdout_fraction)[1]
        grad = graduate(
            winner,
            next_holdout,
            taker_fee,
            fragility_runs=fragility_runs,
            min_fraction_positive=fragility_min_positive,
            min_trades=graduate_min_trades,
        )
        forward.append(
            ForwardStep(
                from_index=prev.index,
                to_index=nxt.index,
                from_passed=prev.passed,
                graduation=grad,
            )
        )

    return StabilityReport(windows=windows, forward=forward)
