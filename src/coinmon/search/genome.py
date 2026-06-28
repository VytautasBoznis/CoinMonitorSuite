from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from coinmon.backtest.portfolio import PerpPortfolio, Portfolio, SpotPortfolio
from coinmon.feed import CostModel
from coinmon.strategies.atr_channel import ATRChannelBreakout
from coinmon.strategies.base import Strategy
from coinmon.strategies.directional import RegimeAdaptive
from coinmon.strategies.ema_crossover import EMACrossover
from coinmon.strategies.indicator_combo import (
    COMBO_FAMILY,
    INDICATOR_COUNT,
    N_CONDITIONS,
    build_combo,
    describe_combo,
)
from coinmon.strategies.rsi_meanreversion import RSIMeanReversion

# Chunk B: a Genome is the GA's unit of selection — *what* to trade (the pair, a gene per the
# chunk-A finding that pair choice dominated param choice) plus *how* (a strategy family and its
# params). ``decode`` turns a genome into a fresh-Strategy factory the engine and the fitness rig
# (``evaluate_fitness``) already accept, so they can score any genome unchanged. The pair gene is
# resolved to candles at data-load time (the strategy itself is pair-agnostic), wired in by the
# search loop (chunk C); the genome only carries the choice.


@dataclass(frozen=True)
class ParamSpec:
    """The domain of one tunable parameter: inclusive ``[low, high]``, integer-valued or not.
    The GA samples and mutates within this range (chunk C); ``decode`` validates against it."""

    low: float
    high: float
    integer: bool = False


@dataclass(frozen=True)
class StrategyFamily:
    """A strategy class plus the param ranges that make it searchable. ``build`` decodes a param
    dict into a concrete ``Strategy``. ``describe`` (optional) renders those params as a readable
    rule for summaries — used by the chunk-P combo family, whose flat genes are otherwise opaque."""

    name: str
    params: Mapping[str, ParamSpec]
    build: Callable[[Mapping[str, float]], Strategy]
    describe: Callable[[Mapping[str, float]], str] | None = None


def _build_rsi(p: Mapping[str, float]) -> Strategy:
    return RSIMeanReversion(
        period=int(p["period"]), oversold=p["oversold"], exit_level=p["exit_level"]
    )


def _build_ema(p: Mapping[str, float]) -> Strategy:
    # Cost-aware band fees come from config, matching the CLI's strategy construction.
    return EMACrossover(CostModel.from_settings(), fast=int(p["fast"]), slow=int(p["slow"]))


def _build_atr(p: Mapping[str, float]) -> Strategy:
    return ATRChannelBreakout(period=int(p["period"]), mult=p["mult"])


# The registry of searchable families. Ranges are deliberately broad-but-sane: the OOS fitness +
# fragility gate (not a tight prior) is what's trusted to reject the junk corners. The soft
# orderings oversold < exit_level and fast < slow are NOT hard-enforced — a malformed band just
# scores poorly out-of-sample, which is the honest signal, and a hard constraint would bias what
# the search is allowed to explore.
FAMILIES: dict[str, StrategyFamily] = {
    "rsi_meanreversion": StrategyFamily(
        name="rsi_meanreversion",
        params={
            "period": ParamSpec(2, 40, integer=True),
            "oversold": ParamSpec(5.0, 45.0),
            "exit_level": ParamSpec(45.0, 90.0),
        },
        build=_build_rsi,
    ),
    "ema_crossover": StrategyFamily(
        name="ema_crossover",
        params={
            "fast": ParamSpec(2, 50, integer=True),
            "slow": ParamSpec(5, 200, integer=True),
        },
        build=_build_ema,
    ),
    "atr_channel": StrategyFamily(
        name="atr_channel",
        params={
            "period": ParamSpec(5, 40, integer=True),
            "mult": ParamSpec(0.5, 4.0),
        },
        build=_build_atr,
    ),
}


def _combo_param_specs() -> dict[str, ParamSpec]:
    """Chunk P: the flat, SCALE-FREE param schema for the bounded multi-indicator family. Per
    condition: an indicator index (integer), then unit [0, 1] ``period``/``threshold`` genes the
    indicator's spec maps onto its own ranges at decode time (so one uniform schema covers every
    indicator's scale), and an op gene (0 = ``<``, 1 = ``>``). One ``combine`` gene picks AND vs OR.
    The unit-genotype trick is what lets the GA mutate a single schema while every indicator still
    gets meaningful periods/thresholds — see ``indicator_combo``."""
    specs: dict[str, ParamSpec] = {}
    for i in range(N_CONDITIONS):
        specs[f"ind{i}"] = ParamSpec(0, INDICATOR_COUNT - 1, integer=True)
        specs[f"period{i}"] = ParamSpec(0.0, 1.0)
        specs[f"op{i}"] = ParamSpec(0, 1, integer=True)
        specs[f"thr{i}"] = ParamSpec(0.0, 1.0)
    specs["combine"] = ParamSpec(0, 1, integer=True)
    return specs


# Registered as an ordinary family so chunk P reuses the WHOLE pipeline unchanged (GA sampling/
# mutation/crossover, decode/decode_portfolio, fitness, graduation, cross-pair). It is explored by
# every search BY DEFAULT — that is the point of P: grow the searchable surface by a bounded,
# watchable amount and ask whether the O-hardened gate holds its false-GO rate against it.
FAMILIES[COMBO_FAMILY] = StrategyFamily(
    name=COMBO_FAMILY,
    params=_combo_param_specs(),
    build=build_combo,
    describe=describe_combo,
)

# The pair gene's sampling pool (chunk-A: pair selection dominates how-to-trade). USDC legs trade
# directly; coin/coin entries are synthesized as ratios at load time. XRP ratios are in because
# chunk A found the only fragility-robust edge there; the junk pairs stay in so the search has to
# reject them rather than being handed a curated shortlist.
UNIVERSE: tuple[str, ...] = (
    "BTC/USDC", "ETH/USDC", "SOL/USDC", "BNB/USDC", "XRP/USDC",
    "ETH/BTC", "SOL/BTC", "BNB/BTC", "XRP/BTC",
    "XRP/ETH", "SOL/ETH", "BNB/ETH",
)


def build_universe(bases: Sequence[str], quote: str) -> tuple[str, ...]:
    """Chunk N4: generate the FULL pair universe from a set of base coins — every ``BASE/QUOTE``
    direct (USDC-quoted) pair plus every unordered ``BASE_i/BASE_j`` ratio (synthesized at load
    time via ``build_ratio``). ``n`` bases yield ``n`` direct + ``C(n,2)`` ratios (~14 bases ≈ 105
    pairs), so the search universe scales with what the scraper covers instead of a hand-curated
    shortlist. Bases are de-duped and sorted so a seeded run is reproducible regardless of input
    order; a base equal to ``quote`` is dropped (no ``USDC/USDC``)."""
    coins = sorted({b for b in bases if b != quote})
    direct = [f"{b}/{quote}" for b in coins]
    ratios = [
        f"{coins[i]}/{coins[j]}"
        for i in range(len(coins))
        for j in range(i + 1, len(coins))
    ]
    return tuple(direct + ratios)

# Directionality is a gene, but NOT a fixed direction. A fixed per-genome ``short`` was the overfit
# vector — chosen in-sample, blind to the holdout regime, so it bet the wrong way every live run
# ([[direction-gene-overfits-regime]]). ``direction`` instead picks between:
#   "long"     — long/flat spot (the chunk-B default; ``leverage``/``trend_period`` are inert).
#   "adaptive" — a regime-adaptive leveraged perp (the bearish leg, [[perp-short-capability]]): the
#                strategy is wrapped in ``RegimeAdaptive`` so it longs a rising market and shorts a
#                falling one by reading the CURRENT-bar trend; the book is a ``PerpPortfolio`` at
#                ``leverage``. The GA chooses whether to go adaptive and how hard to lever; the OOS
#                fitness + fragility + holdout gate punishes reckless leverage, not a cap.
# When ``direction`` is "long" the perp genes are inert and the spot path is byte-unchanged.
DIRECTIONS: tuple[str, ...] = ("long", "adaptive")
LEVERAGE = ParamSpec(1.0, 5.0)

# The regime gene: the SMA window ``RegimeAdaptive`` uses to call up- vs down-regime. A slow range,
# so it defines a *regime*, not noise — but a gene, not a hand-picked constant, so the OOS fitness
# rejects a too-fast/whippy window rather than a tight prior choosing for us. Inert unless adaptive.
TREND = ParamSpec(20, 200, integer=True)

# Chunk L Part A: an intrabar stop-loss is a gene — the brake that lets the search keep leverage a
# free gene without the ruin it caused ([[leverage-breaks-fitness-scaling]]). ``stop_pct`` is the
# fraction the price may move against the entry before the engine force-closes flat mid-bar (against
# the bar's low/high, not its close). ``None`` means NO stop, and the GA can reach it: a stop is not
# universally good ([[stop-loss-hurts-mean-reversion]] found it hurts mean-reversion), so "off" must
# be a first-class choice the search can keep. The range is broad-but-sane; OOS fitness + the gate
# reject the junk corners, not a tight prior.
STOP = ParamSpec(0.02, 0.50)


@dataclass(frozen=True)
class Genome:
    """One search candidate: trade ``pair`` with strategy ``family`` configured by ``params``,
    either long/flat on spot (``direction="long"``) or regime-adaptive on a ``leverage``-x perp
    with a ``trend_period`` regime window (``direction="adaptive"``), optionally braked by an
    intrabar ``stop_pct``. Frozen so a generation is a stable snapshot; ``params`` is a plain dict
    (genomes aren't hashed). The perp/regime/stop genes default to long/flat spot with no stop, so a
    genome built without them is the chunk-B behavior unchanged."""

    family: str
    pair: str
    params: Mapping[str, float]
    direction: str = "long"
    leverage: float = 1.0
    trend_period: float = 50.0
    stop_pct: float | None = None


def validate(genome: Genome) -> None:
    """Raise if the genome is ill-formed: unknown family, wrong/out-of-range params, or a pair
    that isn't ``BASE/QUOTE``. The GA stays inside the ranges, but ``decode`` validates
    defensively so a bad mutation fails loudly rather than silently mis-running."""
    if genome.family not in FAMILIES:
        raise ValueError(f"unknown strategy family {genome.family!r}")
    family = FAMILIES[genome.family]
    if set(genome.params) != set(family.params):
        raise ValueError(
            f"{genome.family} expects params {sorted(family.params)}, got {sorted(genome.params)}"
        )
    for name, spec in family.params.items():
        value = genome.params[name]
        if not spec.low <= value <= spec.high:
            raise ValueError(f"{genome.family}.{name}={value} outside [{spec.low}, {spec.high}]")
    legs = genome.pair.split("/")
    if len(legs) != 2 or not all(legs):
        raise ValueError(f"pair must be BASE/QUOTE, got {genome.pair!r}")
    if genome.direction not in DIRECTIONS:
        raise ValueError(f"direction must be one of {DIRECTIONS}, got {genome.direction!r}")
    if not LEVERAGE.low <= genome.leverage <= LEVERAGE.high:
        raise ValueError(
            f"leverage={genome.leverage} outside [{LEVERAGE.low}, {LEVERAGE.high}]"
        )
    if not TREND.low <= genome.trend_period <= TREND.high:
        raise ValueError(f"trend_period={genome.trend_period} outside [{TREND.low}, {TREND.high}]")
    if genome.stop_pct is not None and not STOP.low <= genome.stop_pct <= STOP.high:
        raise ValueError(f"stop_pct={genome.stop_pct} outside [{STOP.low}, {STOP.high}]")


def decode(genome: Genome) -> Callable[[], Strategy]:
    """Turn a genome into a zero-arg factory of FRESH strategies — the exact ``make_strategy``
    contract ``evaluate_fitness`` and the engine already consume. Each call builds a new instance
    (strategies carry rolling state, so folds and stress runs must not share one). An ``adaptive``
    genome wraps the family in ``RegimeAdaptive`` so it longs a rising market and shorts a falling
    one by the current-bar trend — pair this with ``decode_portfolio``'s perp book to profit from
    the drop."""
    validate(genome)
    family = FAMILIES[genome.family]
    if genome.direction == "adaptive":
        return lambda: RegimeAdaptive(family.build(genome.params), int(genome.trend_period))
    return lambda: family.build(genome.params)


def decode_portfolio(genome: Genome) -> Callable[[float, float], Portfolio]:
    """Turn a genome into a ``(cash, taker_fee) -> Portfolio`` factory — the book the genome trades
    in. An ``adaptive`` genome trades a leveraged ``PerpPortfolio`` (it may short); otherwise the
    long/flat ``SpotPortfolio``. Separate from ``decode`` because the eval rig builds the strategy
    and the book at different points (fold loop, fragility, holdout) with different capital."""
    validate(genome)
    if genome.direction == "adaptive":
        leverage = genome.leverage
        return lambda cash, fee: PerpPortfolio(cash, fee, leverage)
    return lambda cash, fee: SpotPortfolio(cash, fee)
