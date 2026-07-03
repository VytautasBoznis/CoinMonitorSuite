from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import pandas as pd

from coinmon.backtest.result import TradeRecord
from coinmon.search.evidence import (
    EdgeCertificate,
    EvidenceReport,
    build_evidence,
    certify,
    pool_trades,
    select_eval_pairs,
)
from coinmon.search.genome import Genome
from coinmon.search.robustness import _abs_corr

# Chunk Y step 2 — the ensemble as its own certified unit (see .claude/plans/alpha-hunt.md §Y.2).
# A single genome's pooled OOS ledger often can't reach the certificate's N >= 300 floor on its own
# (C1); small edges become tradable only aggregated. This module takes several frozen winners, keeps
# a DECORRELATED top-k of them (so pooling two copies of the same crash-short doesn't fake-inflate N
# with non-independent trades — the failure mode C1/C4 exist to catch), then EQUAL-WEIGHTS their
# ledgers into one pool and certifies THAT as its own unit. The portfolio, not the lone genome, is
# the deployment unit chunk R will allocate.
#
# "Equal-weight the pooled ledger" = every closed trade is one per-trade net-return sample no matter
# which member produced it, exactly how chunk U already pools across pairs (it doesn't reweight by a
# pair's trade count either) — so the ensemble ledger is just the union of its members' ledgers.
# Decorrelation is measured on each member's DAILY realized P&L stream (not the equity level, which
# is trivially autocorrelated): two genomes betting the same way on the same days co-move here.

_MS_PER_DAY = 86_400_000  # open_time is epoch ms UTC (see data/models.py)


def daily_pnl(trades: Sequence[TradeRecord]) -> pd.Series:
    """A member's realized per-day net-return stream: sum each trade's ``net_return_pct`` into the
    UTC day it CLOSED on (``exit_time``). This is the decorrelation signal — two members that make
    the same bets on the same days produce correlated streams and shouldn't both be pooled. Returns
    an empty Series for an empty ledger."""
    if not trades:
        return pd.Series(dtype=float)
    by_day: dict[int, float] = {}
    for t in trades:
        day = t.exit_time // _MS_PER_DAY
        by_day[day] = by_day.get(day, 0.0) + t.net_return_pct
    return pd.Series(by_day).sort_index()


def pick_decorrelated_members(
    order: Sequence[int],
    pnl_of: Callable[[int], pd.Series],
    k: int,
    *,
    max_corr: float = 0.7,
) -> tuple[int, ...]:
    """Greedily keep up to ``k`` members from ``order`` (already ranked best-first) such that each
    kept member's daily-P&L stream has absolute correlation <= ``max_corr`` with every member
    already kept. Best-first order means the strongest survivors are preferred when two members are
    redundant — the 'top-k decorrelated' selection. Reuses chunk O's ``_abs_corr`` (inner-join
    overlap, flat/no-overlap treated as decorrelated)."""
    kept: list[int] = []
    for i in order:
        if len(kept) >= k:
            break
        series = pnl_of(i)
        if all(_abs_corr(series, pnl_of(j)) <= max_corr for j in kept):
            kept.append(i)
    return tuple(kept)


@dataclass(frozen=True)
class EnsembleMember:
    """One candidate genome's individual pooled-ledger stats, and whether the decorrelation pick
    kept it in the ensemble. ``t_exp`` is the member's own certificate score (ranks the pick)."""

    genome: Genome
    n_trades: int
    t_exp: float
    selected: bool


@dataclass(frozen=True)
class EnsembleReport:
    """The ensemble's own Edge Certificate over its selected members' pooled ledger, plus the
    per-candidate breakdown (which were kept, which were dropped as redundant)."""

    members: tuple[EnsembleMember, ...]
    evidence: EvidenceReport
    certificate: EdgeCertificate

    def summary(self) -> str:
        kept = [m for m in self.members if m.selected]
        lines = [
            f"Ensemble of {len(kept)}/{len(self.members)} decorrelated members:",
        ]
        for m in self.members:
            mark = "KEEP" if m.selected else "drop"
            lines.append(
                f"  [{mark}] {m.genome.family:<18} {m.genome.pair:<10} "
                f"trades {m.n_trades:>4}  t_exp {m.t_exp:+.2f}"
            )
        lines.append("")
        lines.append(self.certificate.summary())
        return "\n".join(lines)


def certify_ensemble(
    candidates: Sequence[Genome],
    read: Callable[[str], pd.DataFrame],
    taker_fee: float,
    universe: Sequence[str],
    *,
    k: int,
    eval_pairs: int = 8,
    seed: int = 0,
    window_size: float = 0.6,
    step: float = 0.2,
    holdout_fraction: float = 0.2,
    max_corr: float = 0.7,
    n_regimes: int = 2,
    resamples: int = 5000,
    read_funding: Callable[[str], pd.DataFrame] | None = None,
) -> EnsembleReport:
    """Pool the top-``k`` DECORRELATED members of ``candidates`` and certify the portfolio as its
    own unit. Each candidate is first evaluated exactly like ``coinmon certify`` — its own
    strictly-OOS ledger pooled across its decorrelated peer pairs x rolling windows
    (``select_eval_pairs`` + ``pool_trades``) — then ranked by individual ``t_exp`` and thinned so
    no two kept members co-move on daily P&L. The kept members' ledgers are unioned and judged by
    the same ``certify``. C4/C6 stay PENDING (an ensemble-level null is out of scope) so the
    ensemble can't reach CERTIFIED unaided — the report is the honest 'is the pool an edge?'."""
    ledgers: list[list[TradeRecord]] = []
    t_exps: list[float] = []
    for genome in candidates:
        pairs = select_eval_pairs(
            genome, read, universe, eval_pairs, holdout_fraction=holdout_fraction, seed=seed
        )
        ledger = pool_trades(
            genome, read, taker_fee, pairs,
            window_size=window_size, step=step, holdout_fraction=holdout_fraction,
            read_funding=read_funding,
        )
        ledgers.append(ledger)
        member_ev = build_evidence(ledger, seed=seed, resamples=resamples, n_regimes=n_regimes)
        t_exps.append(member_ev.t_exp)

    streams = [daily_pnl(ledger) for ledger in ledgers]
    order = sorted(range(len(candidates)), key=lambda i: t_exps[i], reverse=True)
    chosen = set(pick_decorrelated_members(order, lambda i: streams[i], k, max_corr=max_corr))

    pooled = [t for i in sorted(chosen) for t in ledgers[i]]
    evidence = build_evidence(pooled, seed=seed, resamples=resamples, n_regimes=n_regimes)
    certificate = certify(evidence)

    members = tuple(
        EnsembleMember(
            genome=candidates[i],
            n_trades=len(ledgers[i]),
            t_exp=t_exps[i],
            selected=i in chosen,
        )
        for i in range(len(candidates))
    )
    return EnsembleReport(members=members, evidence=evidence, certificate=certificate)
