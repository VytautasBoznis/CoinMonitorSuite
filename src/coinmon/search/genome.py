from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from coinmon.backtest.portfolio import PerpPortfolio, Portfolio, SpotPortfolio
from coinmon.feed import CostModel
from coinmon.strategies.atr_channel import ATRChannelBreakout
from coinmon.strategies.base import Strategy
from coinmon.strategies.directional import ShortWhenFlat
from coinmon.strategies.ema_crossover import EMACrossover
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
    dict into a concrete ``Strategy``."""

    name: str
    params: Mapping[str, ParamSpec]
    build: Callable[[Mapping[str, float]], Strategy]


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

# The pair gene's sampling pool (chunk-A: pair selection dominates how-to-trade). USDC legs trade
# directly; coin/coin entries are synthesized as ratios at load time. XRP ratios are in because
# chunk A found the only fragility-robust edge there; the junk pairs stay in so the search has to
# reject them rather than being handed a curated shortlist.
UNIVERSE: tuple[str, ...] = (
    "BTC/USDC", "ETH/USDC", "SOL/USDC", "BNB/USDC", "XRP/USDC",
    "ETH/BTC", "SOL/BTC", "BNB/BTC", "XRP/BTC",
    "XRP/ETH", "SOL/ETH", "BNB/ETH",
)

# Chunk K2: directionality is a gene. ``short`` flips the account from long/flat spot to an
# always-directional leveraged perp (the bearish leg — see [[perp-short-capability]]): the strategy
# is wrapped in ``ShortWhenFlat`` so its exit-to-cash becomes a short, and the book becomes a
# ``PerpPortfolio`` at ``leverage``. The GA chooses whether to short and how hard; the OOS fitness +
# fragility + holdout gate is what punishes reckless leverage, not a hand-tuned cap. The leverage
# range stays modest (a wider band just gets pruned out-of-sample). When ``short`` is False the
# leverage gene is inert and the spot path is byte-unchanged (parity preserved).
LEVERAGE = ParamSpec(1.0, 5.0)


@dataclass(frozen=True)
class Genome:
    """One search candidate: trade ``pair`` with strategy ``family`` configured by ``params``,
    either long/flat on spot or (``short``) always-directional on a ``leverage``-x perp. Frozen
    so a generation is a stable snapshot; ``params`` is a plain dict (genomes aren't hashed).
    ``short``/``leverage`` default to the long/flat spot book, so a genome built without them is
    the chunk-B behavior unchanged."""

    family: str
    pair: str
    params: Mapping[str, float]
    short: bool = False
    leverage: float = 1.0


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
    if not LEVERAGE.low <= genome.leverage <= LEVERAGE.high:
        raise ValueError(
            f"leverage={genome.leverage} outside [{LEVERAGE.low}, {LEVERAGE.high}]"
        )


def decode(genome: Genome) -> Callable[[], Strategy]:
    """Turn a genome into a zero-arg factory of FRESH strategies — the exact ``make_strategy``
    contract ``evaluate_fitness`` and the engine already consume. Each call builds a new instance
    (strategies carry rolling state, so folds and stress runs must not share one). A ``short``
    genome wraps the family in ``ShortWhenFlat`` so its exit-to-cash becomes a short — pair this
    with ``decode_portfolio``'s perp book to actually profit from the drop."""
    validate(genome)
    family = FAMILIES[genome.family]
    if genome.short:
        return lambda: ShortWhenFlat(family.build(genome.params))
    return lambda: family.build(genome.params)


def decode_portfolio(genome: Genome) -> Callable[[float, float], Portfolio]:
    """Turn a genome into a ``(cash, taker_fee) -> Portfolio`` factory — the book the genome trades
    in. A ``short`` genome trades a leveraged ``PerpPortfolio`` (the bearish leg); otherwise the
    long/flat ``SpotPortfolio``. Separate from ``decode`` because the eval rig builds the strategy
    and the book at different points (fold loop, fragility, holdout) with different capital."""
    validate(genome)
    if genome.short:
        leverage = genome.leverage
        return lambda cash, fee: PerpPortfolio(cash, fee, leverage)
    return lambda cash, fee: SpotPortfolio(cash, fee)
