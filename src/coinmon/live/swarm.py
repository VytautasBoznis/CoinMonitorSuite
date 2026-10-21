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
class PaperBot:
    name: str
    rule: Rule
    question: str
    bar: str


BOTS = (
    PaperBot(
        "f8-twin", F8,
        question="How much of the touch-fill backtest survives the real venue? The live bot's"
                 " rule on the same coins and minutes: the fills the live bot missed (queue,"
                 " post-only rejects) and the net per fill, live vs paper.",
        bar="None: a measurement, never promoted (F8 already trades live).",
    ),
    PaperBot(
        "f8-wide", Rule(0.015, 0.020, 240 * MIN),
        question="Does the F8 grid's train pick (1.5% / 2.0% / 240m) keep its holdout lead"
                 " forward? Holdout +16.8%/yr vs F8 +10.0%/yr, difference CI [-8.3, +22.6]"
                 " (runs/f8_param_grid.log).",
        bar=PROMOTION,
    ),
    PaperBot(
        "f8-trend", Rule(F8.drop, F8.target, F8.hold_ms, trend_ms=30 * DAY),
        question="Does bidding only while the coin is up over 30 days avoid F8's falling knives?"
                 " Post-hoc from F8S Q1: +0.684%/event in up markets vs +0.267% in down"
                 " (runs/f8s_squeeze_ladder_proxy.log); this run is its out-of-sample test.",
        bar=PROMOTION,
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
    while True:
        started = time.monotonic()
        for bot in bots:
            try:
                bot.cycle(now_ms())
            except Exception:
                bot.log.exception("cycle failed")
        time.sleep(max(0.0, POLL_S - (time.monotonic() - started)))
