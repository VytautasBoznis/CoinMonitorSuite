from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from coinmon.backtest.engine import BacktestEngine
from coinmon.backtest.stress import MonteCarloResult, run_monte_carlo
from coinmon.search.genome import Genome, decode, decode_portfolio

# Chunk D: the graduation gate — the ONLY path from "GA winner" to "live-eligible". The GA's
# winner was chosen on the search span; here it faces a final holdout span the search never saw
# (carved off before evolution, see ``split_holdout``) plus the full fragility kill-filter. The
# verdict is a hard go/no-go with explicit reasons. This is where overfit dies: a genome the
# search loved but that bleeds, barely trades, or shatters under friction on truly unseen bars
# is rejected. Passing is not a promise of profit — only that the edge survived an honest test.

INITIAL_CAPITAL = 10_000.0


@dataclass(frozen=True)
class GraduationReport:
    """Go/no-go for one genome on the never-searched holdout. ``passed`` is true exactly when
    ``reasons`` is empty; each reason names a gate the genome failed."""

    genome: Genome
    holdout_bars: int
    holdout_return: float
    holdout_trades: int
    benchmark_return: float  # buy & hold over the same holdout span (informational)
    fragility: MonteCarloResult
    passed: bool
    reasons: tuple[str, ...]

    def summary(self) -> str:
        verdict = "GO" if self.passed else "NO-GO"
        book = (
            f"{self.genome.leverage:.1f}x perp regime-adaptive (MA{int(self.genome.trend_period)})"
            if self.genome.direction == "adaptive"
            else "long/flat spot"
        )
        stop = f", {self.genome.stop_pct:.0%} stop" if self.genome.stop_pct is not None else ""
        lines = [
            f"graduation gate [{verdict}] — {self.genome.family} on {self.genome.pair} "
            f"[{book}{stop}]",
            f"  holdout span     {self.holdout_bars} bars (never seen by the search)",
            f"  holdout return   {self.holdout_return:+.2%}  "
            f"(buy & hold {self.benchmark_return:+.2%})",
            f"  holdout trades   {self.holdout_trades}",
            "  fragility:",
            *("  " + line for line in self.fragility.summary().splitlines()),
        ]
        if self.reasons:
            lines.append("  rejected because:")
            lines += [f"    - {r}" for r in self.reasons]
        return "\n".join(lines)


def graduate(
    genome: Genome,
    holdout: pd.DataFrame,
    taker_fee: float,
    *,
    fragility_runs: int = 200,
    min_fraction_positive: float = 0.9,
    min_trades: int = 5,
) -> GraduationReport:
    """Run ``genome`` on the unseen ``holdout`` span and decide go/no-go. A genome graduates only
    if it clears every gate: it makes money on the holdout, trades often enough to be more than
    luck, and stays positive under the fragility kill-filter. ``fragility_runs`` must be >= 1 —
    the gate is incomplete without the stress test."""
    factory = decode(genome)
    build_portfolio = decode_portfolio(genome)
    result = BacktestEngine(
        factory(), build_portfolio(INITIAL_CAPITAL, taker_fee), stop_pct=genome.stop_pct
    ).run(holdout)
    holdout_return = result.metrics["total_return"]
    holdout_trades = int(result.metrics["trades"])
    # B&H over the holdout span, gross of the entry fee (matches the walk-forward benchmark).
    benchmark_return = float(holdout["close"].iloc[-1] / holdout["open"].iloc[0] - 1.0)

    fragility = run_monte_carlo(
        factory,
        lambda: build_portfolio(INITIAL_CAPITAL, taker_fee),
        holdout,
        runs=fragility_runs,
        benchmark_return=benchmark_return,
        stop_pct=genome.stop_pct,
    )

    reasons: list[str] = []
    if holdout_return <= 0:
        reasons.append(f"holdout return {holdout_return:+.2%} not positive")
    if holdout_trades < min_trades:
        reasons.append(f"only {holdout_trades} holdout trades (min {min_trades})")
    if fragility.fraction_positive < min_fraction_positive:
        reasons.append(
            f"fragility {fragility.fraction_positive:.0%} positive < {min_fraction_positive:.0%}"
        )

    return GraduationReport(
        genome=genome,
        holdout_bars=len(holdout),
        holdout_return=holdout_return,
        holdout_trades=holdout_trades,
        benchmark_return=benchmark_return,
        fragility=fragility,
        passed=not reasons,
        reasons=tuple(reasons),
    )
