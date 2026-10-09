"""The live-bot dashboard (``coinmon dashboard``): a JSON API, plus the built web frontend at ``/``.

Reads the bot's DB rows (mode, heartbeat, ledger), the liquidation collector's prints, and public
Hyperliquid data (``market.py``: no key). Its only writes are the two stops
([[live-bot-dashboard-plan]]). DRAIN sets the mode and the running bot works it. PANIC calls the
same ``stop.panic`` as ``coinmon stop --now``, so it works with the bot dead or the DB down, but
needs the agent key in this process's env. Resume stays CLI-only.

No login: anyone who can reach the port can PANIC or DRAIN (flatten only, never open risk). Both
POSTs take a JSON body, so another site cannot fire them from a visitor's browser: FastAPI rejects
non-JSON bodies, and cross-origin JSON needs a CORS preflight this app never grants.
"""

from __future__ import annotations

from collections.abc import Callable
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
from coinmon.live import stop
from coinmon.live.control import DRAIN, RUN, Store, now_ms
from coinmon.live.hyperliquid import Hyperliquid, venue_name
from coinmon.live.ladder import COINS, DROP, HOLD_MS, TARGET

LIQ_EXCHANGE = "bybit"  # the collector's venue; its symbols are ccxt's, e.g. BTC/USDT:USDT
TAPE_LOOKBACK_MS = 24 * 3_600_000


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
               dist: Path | None = None) -> FastAPI:
    store = store or Store()
    market = market or Market(settings.hl_testnet)
    dist = settings.dashboard_dist if dist is None else dist
    venue = venue_name(settings.hl_testnet)
    app = FastAPI(title="coinmon dashboard", docs_url=None, redoc_url=None, openapi_url=None)

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
        ts = now_ms()
        try:
            c = store.read()
        except Exception as e:
            return {"now": ts, "db": False, "error": str(e)}
        return {
            "now": ts, "db": True, "mode": c.mode, "reason": c.reason,
            "deadline_ms": c.deadline_ms, "updated_ms": c.updated_ms,
            "heartbeat_ms": c.heartbeat_ms, "heartbeat": views.heartbeat_state(c.heartbeat_ms, ts),
        }

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

    @app.get("/api/trades")
    def trades(limit: int = Query(200, ge=1, le=1000)):
        rows = views.ledger_rows(store.trades(venue, limit=limit))
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
