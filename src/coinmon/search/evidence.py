from __future__ import annotations

import math
import random
import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import pandas as pd

from coinmon.backtest.engine import BacktestEngine
from coinmon.backtest.result import TradeRecord
from coinmon.data.candles import load_candles, split_holdout
from coinmon.data.funding import attach_funding
from coinmon.search.genome import Genome, decode, decode_portfolio, decode_stop
from coinmon.search.robustness import pick_decorrelated_pairs
from coinmon.search.stability import window_bounds

# Chunk U — the Edge Certificate (the project-level definition of "at least 51%", see
# [[alpha-definition-edge-certificate]] and .claude/plans/alpha-hunt.md §1). The graduation gate
# (chunk D) scores ONE holdout equity curve on 13-20 trades — that measures "bet the right regime",
# not "per-decision edge", and its verdicts ride on a noise floor 10x the edge being hunted
# ([[nested-holdout-refutes-golden]]). This module instead POOLS a frozen genome's per-trade ledger
# across many decorrelated pairs x many rolling-window holdouts (the only way to reach the N the
# arithmetic demands), then judges the pool against six criteria:
#   C1 evidence floor   — N >= 300 pooled OOS trades (below this, 51% indistinguishable from luck)
#   C2 win rate         — p_hat >= 0.51 AND Wilson one-sided 95% lower bound > 0.50
#   C3 expectancy       — mean net return/trade > 0 AND block-bootstrap 95% CI excludes 0
#   C4 beats the null   — score > 95th pct of the null distribution (chunk V; PENDING till supplied)
#   C5 regime spread    — trades span >= 2 disjoint time regimes, expectancy positive in >= 2, never
#                         catastrophic in any
#   C6 fragility        — Monte-Carlo stress >= 95% positive (chunk D's kill-filter; PENDING here)
# Verdicts: CERTIFIED (all six PASS) / REFUTED (N>=300 and any of C2-C6 fail) / UNPROVEN (not enough
# evidence to certify or refute — the honest "keep collecting" state). The graduation gate stays a
# cheap pre-filter inside the search; this certificate is what "alpha" means and what any live
# intent must clear. Never tune anything to pass it — it is the exam, not the training set.

INITIAL_CAPITAL = 10_000.0

# The standard-normal 95th percentile — the z for a one-sided 95% Wilson bound (C2 is one-sided:
# "the true win rate is at least this", so all the confidence sits on the lower tail).
Z_95_ONE_SIDED = 1.6448536269514722


def wilson_lower_bound(wins: int, n: int, z: float = Z_95_ONE_SIDED) -> float:
    """One-sided Wilson score lower bound on the success probability given ``wins`` of ``n`` tries —
    the 'even if we were unlucky, the true win rate is at least this' number that makes C2's 51%
    claim robust to luck. Returns 0.0 for ``n == 0``."""
    if n == 0:
        return 0.0
    phat = wins / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = phat + z2 / (2 * n)
    margin = z * math.sqrt(phat * (1.0 - phat) / n + z2 / (4 * n * n))
    return (centre - margin) / denom


def block_bootstrap_ci(
    values: Sequence[float],
    *,
    seed: int,
    resamples: int = 5000,
    block_len: int | None = None,
    alpha: float = 0.05,
) -> tuple[float, float, float]:
    """Moving-block bootstrap over the TIME-ORDERED ``values`` (per-trade net returns): resample
    contiguous circular blocks of length ~sqrt(N) rather than iid draws, because pooled trades are
    cross-pair correlated and iid resampling would understate the CI. Returns
    ``(ci_low, ci_high, boot_std)`` at the two-sided ``alpha`` — ``boot_std`` is the spread the
    certificate's ``t_exp`` divides by. Returns zeros for ``n < 2`` (no dispersion to estimate)."""
    n = len(values)
    if n < 2:
        return (0.0, 0.0, 0.0)
    block = block_len or max(1, round(math.sqrt(n)))
    n_blocks = math.ceil(n / block)
    rng = random.Random(seed)
    means: list[float] = []
    for _ in range(resamples):
        sample: list[float] = []
        for _ in range(n_blocks):
            start = rng.randrange(n)
            sample.extend(values[(start + i) % n] for i in range(block))
        means.append(statistics.fmean(sample[:n]))  # trim to exactly N: every resample is N trades
    means.sort()
    lo = means[int(alpha / 2 * resamples)]
    hi = means[min(resamples - 1, int((1.0 - alpha / 2) * resamples))]
    return (lo, hi, statistics.pstdev(means))


def _regime_expectancies(trades: Sequence[TradeRecord], n_regimes: int) -> tuple[float, ...]:
    """Split the pooled ledger into ``n_regimes`` DISJOINT equal-time spans by entry time and return
    each non-empty span's mean net return — C5's 'positive in >= 2 disjoint regimes' evidence. Uses
    calendar time (not trade index) so a regime is a genuine market period; a ledger confined to one
    instant collapses to a single regime (which then fails C5's spread test, as it should)."""
    if not trades or n_regimes < 1:
        return ()
    times = [t.entry_time for t in trades]
    lo, hi = min(times), max(times)
    span = hi - lo
    if span == 0:
        return (statistics.fmean([t.net_return_pct for t in trades]),)
    buckets: list[list[float]] = [[] for _ in range(n_regimes)]
    for t in trades:
        idx = min(n_regimes - 1, int((t.entry_time - lo) / span * n_regimes))
        buckets[idx].append(t.net_return_pct)
    return tuple(statistics.fmean(b) for b in buckets if b)


@dataclass(frozen=True)
class EvidenceReport:
    """The pooled-ledger statistics the certificate judges. All figures are per-trade, net of costs,
    over the strictly-out-of-sample pool ``pool_trades`` collected."""

    n_trades: int
    wins: int
    win_rate: float
    wilson_lower: float
    expectancy: float
    expectancy_ci: tuple[float, float]
    expectancy_boot_std: float
    t_exp: float
    regime_expectancies: tuple[float, ...]

    def summary(self) -> str:
        lo, hi = self.expectancy_ci
        pos = sum(1 for e in self.regime_expectancies if e > 0)
        return "\n".join(
            [
                f"  pooled OOS trades  {self.n_trades}",
                f"  win rate           {self.win_rate:.3f}  "
                f"(Wilson 95% lower {self.wilson_lower:.3f})",
                f"  expectancy/trade   {self.expectancy:+.4f}  "
                f"(95% CI [{lo:+.4f}, {hi:+.4f}])",
                f"  t_exp              {self.t_exp:+.2f}",
                f"  regimes positive   {pos}/{len(self.regime_expectancies)}  "
                f"(expectancies {', '.join(f'{e:+.3f}' for e in self.regime_expectancies)})",
            ]
        )


def build_evidence(
    trades: Sequence[TradeRecord],
    *,
    seed: int = 0,
    resamples: int = 5000,
    n_regimes: int = 2,
) -> EvidenceReport:
    """Reduce a pooled trade ledger to the certificate's statistics. Pure — takes trades, returns
    numbers — so it is unit-testable on synthetic ledgers without any DB or engine."""
    ordered = sorted(trades, key=lambda t: t.entry_time)
    rets = [t.net_return_pct for t in ordered]
    n = len(rets)
    wins = sum(1 for r in rets if r > 0)
    win_rate = wins / n if n else 0.0
    expectancy = statistics.fmean(rets) if rets else 0.0
    ci_low, ci_high, boot_std = block_bootstrap_ci(rets, seed=seed, resamples=resamples)
    t_exp = expectancy / boot_std if boot_std > 0 else 0.0
    return EvidenceReport(
        n_trades=n,
        wins=wins,
        win_rate=win_rate,
        wilson_lower=wilson_lower_bound(wins, n),
        expectancy=expectancy,
        expectancy_ci=(ci_low, ci_high),
        expectancy_boot_std=boot_std,
        t_exp=t_exp,
        regime_expectancies=_regime_expectancies(ordered, n_regimes),
    )


@dataclass(frozen=True)
class EdgeCertificate:
    """The six-criterion verdict on a pooled ledger. ``criteria`` is ``(id, status, detail)`` per
    criterion (status PASS/FAIL/PENDING), like ``GraduationReport``'s explicit-reasons style."""

    verdict: str  # CERTIFIED / UNPROVEN / REFUTED
    evidence: EvidenceReport
    criteria: tuple[tuple[str, str, str], ...]

    def summary(self) -> str:
        lines = [
            f"Edge Certificate [{self.verdict}]:",
            self.evidence.summary(),
            "  criteria:",
        ]
        for cid, status, detail in self.criteria:
            lines.append(f"    [{status:<7}] {cid:<18} {detail}")
        return "\n".join(lines)


def certify(
    evidence: EvidenceReport,
    *,
    null_beaten: bool | None = None,
    fragility_positive: float | None = None,
    min_trades: int = 300,
    min_win_rate: float = 0.51,
    min_fraction_positive: float = 0.95,
    catastrophic: float = -0.05,
) -> EdgeCertificate:
    """Apply the six criteria to a pooled ``evidence`` report. ``null_beaten`` (chunk V) and
    ``fragility_positive`` (chunk D's kill-filter) are optional: ``None`` leaves that criterion
    PENDING, which blocks a CERTIFIED verdict but never forces REFUTED. Verdict rule: N < 300 (or
    a PENDING criterion with the rest clean) -> UNPROVEN; N >= 300 with any of C2-C6 failing ->
    REFUTED; all six PASS -> CERTIFIED."""
    ev = evidence

    def mark(ok: bool) -> str:
        return "PASS" if ok else "FAIL"

    c1 = ev.n_trades >= min_trades
    c2 = ev.win_rate >= min_win_rate and ev.wilson_lower > 0.50
    c3 = ev.expectancy > 0 and ev.expectancy_ci[0] > 0
    positive_regimes = sum(1 for e in ev.regime_expectancies if e > 0)
    worst = min(ev.regime_expectancies) if ev.regime_expectancies else 0.0
    c5 = (
        len(ev.regime_expectancies) >= 2
        and positive_regimes >= 2
        and worst >= catastrophic
    )

    criteria: list[tuple[str, str, str]] = [
        ("C1 evidence floor", mark(c1), f"{ev.n_trades} pooled OOS trades (min {min_trades})"),
        (
            "C2 win rate",
            mark(c2),
            f"p_hat {ev.win_rate:.3f}, Wilson lower {ev.wilson_lower:.3f} (need >= 0.51 / > 0.50)",
        ),
        (
            "C3 expectancy",
            mark(c3),
            f"exp {ev.expectancy:+.4f}, 95% CI low {ev.expectancy_ci[0]:+.4f} (need > 0)",
        ),
    ]

    if null_beaten is None:
        criteria.append(("C4 beats null", "PENDING", "null distribution not supplied (chunk V)"))
    else:
        criteria.append(
            (
                "C4 beats null",
                mark(null_beaten),
                "score > null 95th pct" if null_beaten else "does not beat the null",
            )
        )
    criteria.append(
        (
            "C5 regime spread",
            mark(c5),
            f"{positive_regimes}/{len(ev.regime_expectancies)} regimes positive, "
            f"worst {worst:+.4f} (min 2 positive, none < {catastrophic:+.2f})",
        )
    )
    if fragility_positive is None:
        criteria.append(("C6 fragility", "PENDING", "fragility not supplied"))
    else:
        c6 = fragility_positive >= min_fraction_positive
        criteria.append(
            (
                "C6 fragility",
                mark(c6),
                f"{fragility_positive:.0%} positive (min {min_fraction_positive:.0%})",
            )
        )

    hard_fail = not (c2 and c3 and c5)
    optional_fail = (null_beaten is False) or (
        fragility_positive is not None and fragility_positive < min_fraction_positive
    )
    pending = null_beaten is None or fragility_positive is None

    if not c1:
        verdict = "UNPROVEN"
    elif hard_fail or optional_fail:
        verdict = "REFUTED"
    elif pending:
        verdict = "UNPROVEN"  # clears C1-C3,C5 but can't be CERTIFIED without the null / fragility
    else:
        verdict = "CERTIFIED"

    return EdgeCertificate(verdict=verdict, evidence=ev, criteria=tuple(criteria))


# Chunk U.3 — the sweep's certificate ranking. `coinmon sweep` graduates one winner per seed and
# ranks them by raw holdout return (one equity curve, the wrong currency — see the alpha-hunt plan).
# `--certify` replaces that: pool each GO winner's strictly-OOS per-trade ledger and rank by the
# certificate SCORE (t_exp), the evidence the project actually trusts. The ranked list is what the
# ensemble file lists best-first, so the user no longer hand-picks GO genomes for the ensemble.


@dataclass(frozen=True)
class CertifiedRow:
    """A sweep GO winner paired with its pooled-ledger Edge Certificate."""

    genome: Genome
    certificate: EdgeCertificate


def rank_certified(rows: Sequence[CertifiedRow]) -> list[CertifiedRow]:
    """The GO winners, best certificate score (t_exp) first — the order the ensemble file is written
    in and the summary prints."""
    return sorted(rows, key=lambda r: r.certificate.evidence.t_exp, reverse=True)


def summarize_certified_sweep(rows: Sequence[CertifiedRow]) -> str:
    """Rank a sweep's GO winners by Edge-Certificate t_exp (best first) and tally the verdicts. Pure
    — takes rows, returns text — so it is testable without a DB."""
    if not rows:
        return "certified sweep — no GO winners to certify."
    ranked = rank_certified(rows)
    lines = ["certified sweep — GO winners ranked by certificate score (t_exp):"]
    for r in ranked:
        e = r.certificate.evidence
        lines.append(
            f"  [{r.certificate.verdict:<9}] {r.genome.family} on {r.genome.pair} "
            f"({r.genome.direction})  t_exp {e.t_exp:+.2f}  N {e.n_trades:>4}  "
            f"win {e.win_rate:.3f} (Wilson {e.wilson_lower:.3f})  exp {e.expectancy:+.4f}"
        )
    verdicts = [r.certificate.verdict for r in ranked]
    lines.append("")
    lines.append(
        f"{verdicts.count('CERTIFIED')} CERTIFIED, {verdicts.count('UNPROVEN')} UNPROVEN, "
        f"{verdicts.count('REFUTED')} REFUTED of {len(ranked)} GO winner(s)"
    )
    return "\n".join(lines)


def select_eval_pairs(
    genome: Genome,
    read: Callable[[str], pd.DataFrame],
    universe: Sequence[str],
    n_peers: int,
    *,
    holdout_fraction: float,
    seed: int,
    max_corr: float = 0.7,
) -> tuple[str, ...]:
    """The genome's own pair plus up to ``n_peers`` DECORRELATED peers from ``universe`` — the
    pooling set. Reuses chunk O's ``pick_decorrelated_pairs`` (holdout-return decorrelation) so
    three majors crashing together count as one test, not three."""

    def returns_of(pair: str) -> pd.Series | None:
        try:
            frame = load_candles(read, pair)
        except (ValueError, KeyError):
            return None
        holdout = split_holdout(frame, holdout_fraction)[1]
        if holdout.empty:
            return None
        return holdout.set_index("open_time")["close"].pct_change()

    candidates = [p for p in universe if p != genome.pair]
    peers = pick_decorrelated_pairs(
        candidates, returns_of, n_peers, seed=seed, max_corr=max_corr
    )
    return (genome.pair, *peers)


def _iter_segments(
    genome: Genome,
    read: Callable[[str], pd.DataFrame],
    taker_fee: float,
    eval_pairs: Sequence[str],
    *,
    window_size: float,
    step: float,
    n_windows: int | None,
    holdout_fraction: float,
    read_funding: Callable[[str], pd.DataFrame] | None = None,
):
    """Yield ``(pair, holdout_frame, BacktestResult)`` for each (pair, window) OOS slice — the
    single grid iteration ``pool_trades``/``pool_segments`` (chunk V2)/``pool_carry_bars`` (W3 step
    3b) share, so the leakage-critical 'only strictly-OOS bars' logic lives in ONE place. Each
    window's holdout is bars the producing search never touched. The ``pair`` is yielded so the
    carry pooler can count how many perps actually contributed. A pair that won't load, or a window
    too short, is skipped, not crashed on.

    ``read_funding`` (chunk W3 step 2c), when given, attaches the per-bar ``funding_rate`` column so
    a carry genome's pooled certificate ledger includes real funding; ``None`` keeps frames
    candle-only (byte-unchanged for every price-shape genome)."""
    factory = decode(genome)
    build_portfolio = decode_portfolio(genome)
    stop_pct = decode_stop(genome)
    bounds = window_bounds(window_size, step, n_windows)
    for pair in eval_pairs:
        try:
            frame = load_candles(read, pair)
        except (ValueError, KeyError):
            continue
        if read_funding is not None:
            frame = attach_funding(frame, pair, read_funding)
        n = len(frame)
        for lo, hi in bounds:
            window = frame.iloc[int(n * lo) : int(n * hi)].reset_index(drop=True)
            if len(window) < 3:
                continue
            holdout = split_holdout(window, holdout_fraction)[1]
            if len(holdout) < 3:
                continue
            result = BacktestEngine(
                factory(),
                build_portfolio(INITIAL_CAPITAL, taker_fee),
                stop_pct=stop_pct,
            ).run(holdout)
            yield pair, holdout, result


def pool_trades(
    genome: Genome,
    read: Callable[[str], pd.DataFrame],
    taker_fee: float,
    eval_pairs: Sequence[str],
    *,
    window_size: float = 0.6,
    step: float = 0.2,
    n_windows: int | None = None,
    holdout_fraction: float = 0.2,
    read_funding: Callable[[str], pd.DataFrame] | None = None,
) -> list[TradeRecord]:
    """Run the frozen ``genome`` (pair gene overridden to each of ``eval_pairs``) over the holdout
    tail of each rolling window and pool every closed trade — the strictly-OOS ledger the
    certificate scores. Reuses chunk S's ``window_bounds`` and chunk D's ``split_holdout``: each
    window's holdout is bars the producing search never touched, so pooling multiplies evidence
    without leaking. A pair that won't load, or a window too short, is skipped, not crashed on.
    ``read_funding`` (chunk W3 step 2c) includes real funding for a carry genome; ``None`` =
    candle-only."""
    pooled: list[TradeRecord] = []
    for _pair, _holdout, result in _iter_segments(
        genome, read, taker_fee, eval_pairs,
        window_size=window_size, step=step, n_windows=n_windows, holdout_fraction=holdout_fraction,
        read_funding=read_funding,
    ):
        pooled.extend(result.trades)
    return pooled


@dataclass(frozen=True)
class EvalSegment:
    """One (pair, window) holdout slice used for pooling: the OOS price series the genome traded on
    (``opens``/``closes``, both needed to replay a fill-at-open + mark-at-close round-trip) plus the
    ``(direction, duration_bars)`` of each closed trade it made there. Chunk V2's exposure-matched
    null replays random-entry trades of the SAME durations and directions on these same prices."""

    opens: tuple[float, ...]
    closes: tuple[float, ...]
    trades: tuple[tuple[int, int], ...]


def pool_segments(
    genome: Genome,
    read: Callable[[str], pd.DataFrame],
    taker_fee: float,
    eval_pairs: Sequence[str],
    *,
    window_size: float = 0.6,
    step: float = 0.2,
    n_windows: int | None = None,
    holdout_fraction: float = 0.2,
    read_funding: Callable[[str], pd.DataFrame] | None = None,
) -> list[EvalSegment]:
    """The same OOS grid as ``pool_trades``, but returning per-segment price series + the
    (direction, duration-in-bars) of each closed trade — the structure chunk V2's exposure-matched
    random-entry null needs to place matched-but-randomly-timed trades on the very series the
    candidate traded. Duration is the bar-index gap between the entry and exit fills (fills land at
    a bar's open, so both times are in the holdout frame). Segments with no closed trade are
    dropped (nothing to exposure-match). ``read_funding`` (chunk W3 step 2c) includes real funding
    for a carry genome; ``None`` = candle-only."""
    segments: list[EvalSegment] = []
    for _pair, holdout, result in _iter_segments(
        genome, read, taker_fee, eval_pairs,
        window_size=window_size, step=step, n_windows=n_windows, holdout_fraction=holdout_fraction,
        read_funding=read_funding,
    ):
        if not result.trades:
            continue
        idx = {int(t): i for i, t in enumerate(holdout["open_time"].to_numpy())}
        trades = tuple(
            (tr.direction, idx[tr.exit_time] - idx[tr.entry_time]) for tr in result.trades
        )
        segments.append(
            EvalSegment(
                opens=tuple(float(x) for x in holdout["open"].to_numpy()),
                closes=tuple(float(x) for x in holdout["close"].to_numpy()),
                trades=trades,
            )
        )
    return segments


# Chunk W3 step 3b — the CARRY-appropriate Edge Certificate. The chunk-U certificate above judges a
# per-TRADE ledger (N>=300 closed round-trips, a Wilson win-rate bound). A funding-carry hold makes
# only ~5-10 round-trips per perp and each held trade is almost always net-positive, so that ledger
# is both starved (N) and its win-rate inflated (a hold that survives positive funding "wins" almost
# by construction). The economically meaningful unit for carry is instead the PER-BAR net carry
# return: (equity_t - equity_{t-1}) / equity_{t-1} on the market-neutral CarryPortfolio, whose
# equity is price-independent so a bar's return is exactly the funding it collected minus any taker
# fee that rebalanced on it. Pooling those bars over DIRECT funded perps x rolling windows asks the
# real question — "held across settlements, does the premium out-earn the round-trip fees, per unit
# time, across regimes?" — with an N (bars) that clears any floor and a block-bootstrap CI that
# accounts for funding's autocorrelation. Fees are attributed with no bookkeeping: they land on the
# rebalance bar's return, held bars carry the funding credit, flat bars return 0 (an honest "earned
# nothing then"). Same six-criterion shape as ``certify``, minus C2 (win-rate is not carry's
# invariant — reported as fraction-of-positive-bars only) and with C1 an evidence+breadth floor.


def _regime_means(
    times: Sequence[int], values: Sequence[float], n_regimes: int
) -> tuple[float, ...]:
    """Split ``(times, values)`` into ``n_regimes`` DISJOINT equal-time spans by ``times`` and give
    each non-empty span's mean — the per-bar analogue of ``_regime_expectancies`` (C5 evidence: the
    carry premium must be positive in >= 2 genuine market periods, not one funding regime). Uses
    calendar time so a regime is a real period; a pool confined to one instant collapses to one
    regime (which then fails C5's spread test, as it should)."""
    if not times or n_regimes < 1:
        return ()
    lo, hi = min(times), max(times)
    span = hi - lo
    if span == 0:
        return (statistics.fmean(values),)
    buckets: list[list[float]] = [[] for _ in range(n_regimes)]
    for t, v in zip(times, values, strict=True):
        idx = min(n_regimes - 1, int((t - lo) / span * n_regimes))
        buckets[idx].append(v)
    return tuple(statistics.fmean(b) for b in buckets if b)


@dataclass(frozen=True)
class CarryEvidence:
    """The pooled per-bar carry statistics the carry certificate judges. All figures are per-bar,
    net of taker fees, over the strictly-OOS bar pool. ``annualized`` is the simple (non-compounded)
    ``mean_return * bars_per_year`` — a readability aid, never gated on."""

    n_bars: int
    n_pairs: int
    mean_return: float
    return_ci: tuple[float, float]
    boot_std: float
    t_stat: float
    fraction_positive: float
    annualized: float
    regime_means: tuple[float, ...]

    def summary(self) -> str:
        lo, hi = self.return_ci
        pos = sum(1 for e in self.regime_means if e > 0)
        return "\n".join(
            [
                f"  pooled OOS bars    {self.n_bars}  ({self.n_pairs} funded perps)",
                f"  mean carry/bar     {self.mean_return:+.6f}  "
                f"(95% CI [{lo:+.6f}, {hi:+.6f}])",
                f"  ~annualized        {self.annualized:+.2%}  (simple, mean x bars/yr)",
                f"  t-stat             {self.t_stat:+.2f}",
                f"  positive bars      {self.fraction_positive:.1%}",
                f"  regimes positive   {pos}/{len(self.regime_means)}  "
                f"(means {', '.join(f'{e:+.6f}' for e in self.regime_means)})",
            ]
        )


def build_carry_evidence(
    bars: Sequence[tuple[int, float]],
    n_pairs: int,
    *,
    bars_per_year: float,
    seed: int = 0,
    resamples: int = 5000,
    n_regimes: int = 2,
) -> CarryEvidence:
    """Reduce a pooled per-bar carry ledger (``(open_time, net_return)`` pairs) to the carry
    certificate's statistics. Pure — takes bars, returns numbers — so it is unit-testable on
    synthetic bar streams without any DB or engine."""
    ordered = sorted(bars, key=lambda b: b[0])
    times = [t for t, _ in ordered]
    rets = [r for _, r in ordered]
    n = len(rets)
    mean = statistics.fmean(rets) if rets else 0.0
    positive = sum(1 for r in rets if r > 0)
    ci_low, ci_high, boot_std = block_bootstrap_ci(rets, seed=seed, resamples=resamples)
    return CarryEvidence(
        n_bars=n,
        n_pairs=n_pairs,
        mean_return=mean,
        return_ci=(ci_low, ci_high),
        boot_std=boot_std,
        t_stat=mean / boot_std if boot_std > 0 else 0.0,
        fraction_positive=positive / n if n else 0.0,
        annualized=mean * bars_per_year,
        regime_means=_regime_means(times, rets, n_regimes),
    )


@dataclass(frozen=True)
class CarryCertificate:
    """The carry verdict on a pooled per-bar ledger, same explicit-criteria shape as
    ``EdgeCertificate``. ``criteria`` is ``(id, status, detail)`` per criterion."""

    verdict: str  # CERTIFIED / UNPROVEN / REFUTED
    evidence: CarryEvidence
    criteria: tuple[tuple[str, str, str], ...]

    def summary(self) -> str:
        lines = [
            f"Carry Certificate [{self.verdict}]:",
            self.evidence.summary(),
            "  criteria:",
        ]
        for cid, status, detail in self.criteria:
            lines.append(f"    [{status:<7}] {cid:<18} {detail}")
        return "\n".join(lines)


def certify_carry(
    evidence: CarryEvidence,
    *,
    null_beaten: bool | None = None,
    fragility_positive: float | None = None,
    min_bars: int = 300,
    min_pairs: int = 3,
    catastrophic: float = -0.0005,
) -> CarryCertificate:
    """Apply the carry criteria to a pooled ``evidence`` report. Same verdict logic as ``certify``
    with carry's unit: C1 breadth (>= ``min_bars`` pooled bars AND >= ``min_pairs`` funded perps —
    a per-bar N is huge, so breadth-across-perps is the real floor), C3 expectancy (mean carry/bar
    > 0 AND block-bootstrap CI low > 0 — the core test), C5 regime spread (positive in >= 2 disjoint
    time regimes, none worse than ``catastrophic`` per bar). No C2 (win-rate is not carry's
    invariant). ``null_beaten`` (shuffled-funding null, W3 step 3c) and ``fragility_positive`` are
    optional: ``None`` leaves that criterion PENDING, which blocks CERTIFIED but never forces
    REFUTED."""
    ev = evidence

    def mark(ok: bool) -> str:
        return "PASS" if ok else "FAIL"

    c1 = ev.n_bars >= min_bars and ev.n_pairs >= min_pairs
    c3 = ev.mean_return > 0 and ev.return_ci[0] > 0
    positive_regimes = sum(1 for e in ev.regime_means if e > 0)
    worst = min(ev.regime_means) if ev.regime_means else 0.0
    c5 = len(ev.regime_means) >= 2 and positive_regimes >= 2 and worst >= catastrophic

    criteria: list[tuple[str, str, str]] = [
        (
            "C1 evidence floor",
            mark(c1),
            f"{ev.n_bars} bars / {ev.n_pairs} perps (min {min_bars} / {min_pairs})",
        ),
        (
            "C3 expectancy",
            mark(c3),
            f"mean/bar {ev.mean_return:+.6f}, 95% CI low {ev.return_ci[0]:+.6f} (need > 0)",
        ),
    ]
    if null_beaten is None:
        criteria.append(
            ("C4 beats null", "PENDING", "shuffled-funding null not supplied (W3 step 3c)")
        )
    else:
        criteria.append(
            (
                "C4 beats null",
                mark(null_beaten),
                "score > null 95th pct" if null_beaten else "does not beat the null",
            )
        )
    criteria.append(
        (
            "C5 regime spread",
            mark(c5),
            f"{positive_regimes}/{len(ev.regime_means)} regimes positive, "
            f"worst {worst:+.6f} (min 2 positive, none < {catastrophic:+.6f})",
        )
    )
    if fragility_positive is None:
        criteria.append(("C6 fragility", "PENDING", "fragility not supplied"))
    else:
        c6 = fragility_positive >= 0.95
        criteria.append(
            ("C6 fragility", mark(c6), f"{fragility_positive:.0%} positive (min 95%)")
        )

    hard_fail = not (c3 and c5)
    optional_fail = (null_beaten is False) or (
        fragility_positive is not None and fragility_positive < 0.95
    )
    pending = null_beaten is None or fragility_positive is None

    if not c1:
        verdict = "UNPROVEN"
    elif hard_fail or optional_fail:
        verdict = "REFUTED"
    elif pending:
        verdict = "UNPROVEN"
    else:
        verdict = "CERTIFIED"

    return CarryCertificate(verdict=verdict, evidence=ev, criteria=tuple(criteria))


def pool_carry_bars(
    genome: Genome,
    read: Callable[[str], pd.DataFrame],
    taker_fee: float,
    eval_pairs: Sequence[str],
    *,
    window_size: float = 0.6,
    step: float = 0.2,
    n_windows: int | None = None,
    holdout_fraction: float = 0.2,
    read_funding: Callable[[str], pd.DataFrame] | None = None,
) -> tuple[list[tuple[int, float]], int]:
    """Run the frozen carry ``genome`` over the holdout tail of each rolling window on every DIRECT
    funded perp in ``eval_pairs`` and pool every bar's net carry return — the strictly-OOS per-bar
    ledger the carry certificate scores. Returns ``(bars, n_pairs)`` where ``bars`` is
    ``(open_time, net_return)`` per holdout bar (equity ``pct_change``: funding credit minus any
    rebalance fee, price PnL cancels on the neutral book) and ``n_pairs`` is how many perps actually
    contributed a bar. Reuses ``_iter_segments`` so the leakage-critical OOS-window logic is shared;
    ``read_funding`` MUST be supplied for a carry genome (without funding the hedge never opens and
    every bar returns 0)."""
    bars: list[tuple[int, float]] = []
    pairs: set[str] = set()
    for pair, _holdout, result in _iter_segments(
        genome, read, taker_fee, eval_pairs,
        window_size=window_size, step=step, n_windows=n_windows, holdout_fraction=holdout_fraction,
        read_funding=read_funding,
    ):
        rets = result.equity_curve.pct_change().dropna()
        if rets.empty:
            continue
        pairs.add(pair)
        bars.extend(
            (int(t), float(r)) for t, r in zip(rets.index, rets.to_numpy(), strict=True)
        )
    return bars, len(pairs)
