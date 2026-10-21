"""The swarm: paper bots trading live Hyperliquid data next to the real F8 bot
([[swarm-and-cross-market-ideas]]).

Owner decisions 2026-10-21: every swarm bot trades on paper by default; one gets real money only
after it clears a bar written down before it starts, and then trades from its own wallet. Each
entry in ``BOTS`` is that record: the rule, the question its forward run answers, and the bar.
Change a bar only before the bot's first run; after that, a new bar means a new bot name.

All paper bots run in one process (``coinmon swarm run``) on one shared market reader, apart from
the live bot's process. No key is ever loaded here, so nothing in the swarm can touch an account.
Paper fills are touch-fills (``paper.py``): an upper bound, which is why the F8 twin exists.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from coinmon.live.control import RUN, Store, bot_on, now_ms
from coinmon.live.ladder import COINS, F8, POLL_S, LadderBot, Rule, until_reachable
from coinmon.live.paper import MIN, PAPER, HLMarket, PaperVenue

log = logging.getLogger("coinmon.swarm")

DAY = 24 * 60 * MIN

# Approved by the owner 2026-10-21, before any paper bot's first run.
PROMOTION = (
    "Judged once, 6 months after its first run (once more at 12 months if N < 50 then;"
    " after that it is retired). ALL of: N >= 50 closed paper round trips; mean net per round"
    " trip > 0 with the 95% CI (bootstrap over UTC days) excluding zero; paper yield >= 5%/yr"
    " (net USD / (coins x rung) / years, 1x). A pass earns micro-live money from its own wallet,"
    " sized like F8's, never more."
)


@dataclass(frozen=True)
class Baseline:
    """A bot's own backtest, frozen before its first run: the scoreboard's reference
    (``probes/swarm_baselines.py`` -> runs/swarm_baselines.log). The paper venue's replay on the
    six coins over the F8 grid's holdout, 2024-09-30 -> 2026-09-30, at Hyperliquid fees."""

    per_year: float  # round trips per year
    mean: float  # net per round trip
    ci: tuple[float, float]  # 95%, bootstrap over UTC days
    tp_hit: float
    yield_yr: float  # sum of net / coins / years, 1x


F8_BASELINE = Baseline(123.1, 0.00500, (0.00147, 0.00831), 0.858, 0.1026)


@dataclass(frozen=True)
class PaperBot:
    name: str
    rule: Rule
    question: str
    bar: str
    baseline: Baseline


BOTS = (
    PaperBot(
        "f8-twin", F8,
        question="How much of the touch-fill backtest survives the real venue? The live bot's"
                 " rule on the same coins and minutes: the fills the live bot missed (queue,"
                 " post-only rejects) and the net per fill, live vs paper.",
        bar="None: a measurement, never promoted (F8 already trades live).",
        baseline=F8_BASELINE,
    ),
    PaperBot(
        "f8-wide", Rule(0.015, 0.020, 240 * MIN),
        question="Does the F8 grid's train pick (1.5% / 2.0% / 240m) keep its holdout lead"
                 " forward? Holdout +16.8%/yr vs F8 +10.0%/yr, difference CI [-8.3, +22.6]"
                 " (runs/f8_param_grid.log).",
        bar=PROMOTION,
        baseline=Baseline(333.2, 0.00315, (0.00018, 0.00596), 0.592, 0.1751),
    ),
    PaperBot(
        "f8-trend", Rule(F8.drop, F8.target, F8.hold_ms, trend_ms=30 * DAY),
        question="Does bidding only while the coin is up over 30 days avoid F8's falling knives?"
                 " Post-hoc from F8S Q1: +0.684%/event in up markets vs +0.267% in down"
                 " (runs/f8s_squeeze_ladder_proxy.log); this run is its out-of-sample test.",
        bar=PROMOTION,
        # Below plain F8 and under the bar's 5%/yr over these two years: the gate halved N.
        baseline=Baseline(62.0, 0.00454, (-0.00041, 0.00849), 0.815, 0.0469),
    ),
)


def run(rung_usd: float) -> None:
    """Run every paper bot until the process is stopped. Paper bots start in mode RUN."""
    market = until_reachable("connect", HLMarket)
    coins = market.listed(COINS)
    bots = []
    for spec in BOTS:
        store = Store(bot_on(PAPER, spec.name), initial=RUN)
        store.init()
        venue = PaperVenue(market, store.trades(PAPER, open_only=True))
        bots.append(LadderBot(venue, store, rung_usd, coins, spec.rule))
        log.info("%s: %s on %s, %s USDC per rung", store.bot, spec.rule, coins, rung_usd)
    books: dict[str, list[dict] | None] = {}  # bot -> the book last written
    while True:
        started = time.monotonic()
        for bot in bots:
            try:
                bot.cycle(now_ms())
                if (book := bot.hl.book()) != books.get(bot.store.bot):
                    bot.store.save_book(book)  # the dashboard's only view of a paper bot's orders
                    books[bot.store.bot] = book
            except Exception:
                bot.log.exception("cycle failed")
        time.sleep(max(0.0, POLL_S - (time.monotonic() - started)))
