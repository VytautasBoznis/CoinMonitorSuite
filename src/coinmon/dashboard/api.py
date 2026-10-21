"""The live-bot dashboard (``coinmon dashboard``): a JSON API, plus the built web frontend at ``/``.

Reads the bots' DB rows (mode, heartbeat, ledger; the live bot and the swarm's paper bots), the
liquidation collector's prints, and public Hyperliquid data (``market.py``: no key). Its only
writes are the two stops ([[live-bot-dashboard-plan]]), and they act on the live bot only: paper
bots hold no money. DRAIN sets the mode and the running bot works it. PANIC calls the same
``stop.panic`` as ``coinmon stop --now``, so it works with the bot dead or the DB down, but needs
the agent key in this process's env. Resume stays CLI-only.

No login: anyone who can reach the port can PANIC or DRAIN (flatten only, never open risk). Both
POSTs take a JSON body, so another site cannot fire them from a visitor's browser: FastAPI rejects
non-JSON bodies, and cross-origin JSON needs a CORS preflight this app never grants.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from coinmon.config import settings
from coinmon.dashboard import views
from coinmon.dashboard.market import INTERVAL_MS, WS, Market
from coinmon.data import db
from coinmon.live import score, stop, swarm
from coinmon.live.control import BOT, DRAIN, RUN, Store, bot_on, now_ms
from coinmon.live.hyperliquid import Hyperliquid, venue_name
from coinmon.live.ladder import COINS, DROP, F8, HOLD_MS, TARGET, Rule
from coinmon.live.paper import PAPER

LIQ_EXCHANGE = "bybit"  # the collector's venue; its symbols are ccxt's, e.g. BTC/USDT:USDT
TAPE_LOOKBACK_MS = 24 * 3_600_000
SCORE_LIMIT = 100_000  # round trips read per bot for the scoreboard: all of them
LIVE_QUESTION = ("What the venue really pays for F8's touch-fills: the frozen rule with real money"
                 " (queue position, post-only rejects, partial fills).")
LIVE_BAR = ("None: micro-live data gathering, never a deployment; real capital still needs"
            " 5%/yr forward.")


def _paper_store(name: str) -> Store:
    return Store(bot_on(PAPER, name), initial=RUN)


def _bot(bot: str, paper: bool, rule: Rule, question: str, bar: str, baseline: swarm.Baseline,
         state: dict) -> dict:
    return {"id": bot, "paper": paper, "question": question, "bar": bar,
            "rule": {"drop": rule.drop, "target": rule.target, "hold_ms": rule.hold_ms,
                     "trend_ms": rule.trend_ms},
            "baseline": asdict(baseline), "state": state}


class PanicRequest(BaseModel):
    confirm: Literal[True]


class DrainRequest(BaseModel):
    minutes: int = Field(ge=1, le=24 * 60)


def _check(coin: str, interval: str) -> None:
    if coin not in COINS or interval not in INTERVAL_MS:
        raise HTTPException(422, f"coin is one of {COINS}, interval one of {list(INTERVAL_MS)}")


def _venue_client() -> Hyperliquid:
    return Hyperliquid(settings.hl_address, settings.hl_agent_key, testnet=settings.hl_testnet)


def create_app(store: Store | None = None, market: Market | None = None,
               venue_client: Callable[[], Hyperliquid] = _venue_client,
               dist: Path | None = None,
               paper_store: Callable[[str], Store] = _paper_store) -> FastAPI:
    venue = venue_name(settings.hl_testnet)
    store = store or Store(bot_on(venue))
    papers = {s.name: (s, paper_store(s.name)) for s in swarm.BOTS}
    market = market or Market(settings.hl_testnet)
    dist = settings.dashboard_dist if dist is None else dist
    app = FastAPI(title="coinmon dashboard", docs_url=None, redoc_url=None, openapi_url=None)

    def ledger(bot: str) -> tuple[Store, str]:
        """``bot``'s store and the venue its ledger rows are under."""
        if bot == BOT:
            return store, venue
        if bot in papers:
            return papers[bot][1], PAPER
        raise HTTPException(422, f"bot is one of {[BOT, *papers]}")

    def state_of(st: Store) -> dict:
        ts = now_ms()
        try:
            c = st.read()
        except Exception as e:
            return {"now": ts, "db": False, "error": str(e)}
        return {
            "now": ts, "db": True, "mode": c.mode, "reason": c.reason,
            "deadline_ms": c.deadline_ms, "updated_ms": c.updated_ms,
            "heartbeat_ms": c.heartbeat_ms, "heartbeat": views.heartbeat_state(c.heartbeat_ms, ts),
            "started_ms": c.started_ms, "book": c.book,
        }

    def keyed() -> bool:
        return bool(settings.hl_address and settings.hl_agent_key)

    def listed() -> tuple[str, ...]:
        """The bot's coins this venue lists (testnet lacks some); all if it is unreachable."""
        try:
            return tuple(c for c in COINS if c in market.contexts(COINS))
        except httpx.HTTPError:
            return COINS

    def from_venue(fn, *args):
        try:
            return fn(*args)
        except httpx.HTTPError as e:
            raise HTTPException(502, f"venue unreachable: {e}") from e

    @app.get("/api/health")
    def health():
        """Liveness for k8s probes: the process answers. Touches neither the DB nor the venue."""
        return {"ok": True}

    @app.get("/api/config")
    def config():
        coins = listed()
        return {
            "venue": venue, "testnet": settings.hl_testnet, "ws": WS[settings.hl_testnet],
            "coins": coins, "unlisted": [c for c in COINS if c not in coins],
            "intervals": list(INTERVAL_MS), "address": settings.hl_address or None,
            "keyed": keyed(), "stale_s": views.STALE_S,
            "rule": {"drop": DROP, "target": TARGET, "hold_ms": HOLD_MS},
        }

    @app.get("/api/state")
    def state():
        """The live bot's: the stops act on it."""
        return state_of(store)

    @app.get("/api/bots")
    def bots():
        """The live bot, then the swarm's paper bots: rule, frozen backtest, and state (a paper
        bot's state carries its book, the resting simulated orders)."""
        live = _bot(BOT, False, F8, LIVE_QUESTION, LIVE_BAR, swarm.F8_BASELINE, state_of(store))
        return [live] + [_bot(s.name, True, s.rule, s.question, s.bar, s.baseline, state_of(st))
                         for s, st in papers.values()]

    @app.get("/api/scoreboard")
    def scoreboard():
        """Each bot's forward record against its own frozen backtest; a paper bot with a bar gets
        the bar's verdict, the twin its live-capture measurement."""
        ts = now_ms()
        try:
            live = store.trades(venue, limit=SCORE_LIMIT)
            cards = [{"id": BOT, **score.card(live, store.read().started_ms, ts, len(listed()),
                                              swarm.F8_BASELINE)}]
            for s, st in papers.values():
                started = st.read().started_ms
                trades = st.trades(PAPER, limit=SCORE_LIMIT)
                c = {"id": s.name, **score.card(trades, started, ts, len(COINS), s.baseline)}
                if s.bar == swarm.PROMOTION:
                    c["bar"] = score.judge(trades, started, ts, len(COINS))
                if s.rule == F8:
                    c["capture"] = score.capture(trades, live, started)
                cards.append(c)
        except Exception as e:
            raise HTTPException(503, f"control store unreachable: {e}") from e
        return cards

    @app.get("/api/market")
    def market_contexts():
        return from_venue(market.contexts, COINS)

    @app.get("/api/candles")
    def candles(coin: str, interval: str = "1m", limit: int = Query(500, ge=10, le=2000)):
        _check(coin, interval)
        return from_venue(market.candles, coin, interval, limit, now_ms())

    @app.get("/api/account")
    def account():
        if not settings.hl_address:
            return {"configured": False}
        return {"configured": True} | from_venue(market.account, settings.hl_address)

    @app.get("/api/burn")
    def burn():
        """The account's equity and PnL since it opened: the burn meter."""
        if not settings.hl_address:
            return {"configured": False}
        return {"configured": True,
                "points": from_venue(market.portfolio, settings.hl_address)}

    @app.get("/api/trades")
    def trades(bot: str = BOT, limit: int = Query(200, ge=1, le=1000)):
        st, v = ledger(bot)
        rows = views.ledger_rows(st.trades(v, limit=limit))
        return {"rows": rows, "summary": views.ledger_summary(rows)}

    @app.get("/api/liquidations")
    def liquidations(coin: str, start_ms: int, end_ms: int, interval: str = "1m"):
        _check(coin, interval)
        symbol = f"{coin}/USDT:USDT"
        with db.connect() as conn:
            prints = db.read_liquidations(conn, LIQ_EXCHANGE, symbol, start_ms, end_ms)
            spans = db.read_liquidation_coverage(conn, LIQ_EXCHANGE, symbol, start_ms, end_ms)
        gaps = views.coverage_gaps(spans, start_ms, end_ms)
        return {
            "buckets": views.liquidation_buckets(prints, INTERVAL_MS[interval]),
            "gaps": gaps,
            "coverage": 1 - sum(b - a for a, b in gaps) / max(end_ms - start_ms, 1),
        }

    @app.get("/api/liquidations/recent")
    def recent_liquidations(limit: int = Query(60, ge=1, le=500)):
        """The newest stored prints across the ladder's coins (the tape's backfill)."""
        end = now_ms()
        rows = []
        with db.connect() as conn:
            for coin in listed():
                df = db.read_liquidations(conn, LIQ_EXCHANGE, f"{coin}/USDT:USDT",
                                          end - TAPE_LOOKBACK_MS, end)
                rows += [{"coin": coin, "ts": int(r.ts), "side": r.side, "price": float(r.price),
                          "size": float(r.size)} for r in df.itertuples()]
        return sorted(rows, key=lambda r: r["ts"], reverse=True)[:limit]

    @app.post("/api/panic")
    def panic(_: PanicRequest):
        if not keyed():
            raise HTTPException(409, "no agent key in the dashboard env: run `coinmon stop --now`")
        try:
            return {"flat": stop.panic(venue_client(), store, "dashboard panic")}
        except Exception as e:
            raise HTTPException(502, f"PANIC failed ({e}): run `coinmon stop --now`") from e

    @app.post("/api/drain")
    def drain(req: DrainRequest):
        try:
            c = store.read()
        except Exception as e:
            raise HTTPException(503, f"control store unreachable: {e}") from e
        if c.mode != RUN:
            raise HTTPException(409, f"DRAIN needs mode RUN; it is {c.mode}")
        deadline = now_ms() + req.minutes * 60_000
        store.set_mode(DRAIN, "dashboard drain", deadline)
        return {"mode": DRAIN, "deadline_ms": deadline}

    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="web")
    return app
