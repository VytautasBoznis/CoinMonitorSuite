"""Bybit v5 ``allLiquidation`` websocket collector (idea-8 cascade-ladder research).

Bybit serves no liquidation history over REST, so the only record is what a running collector
saw. Every linear perpetual (USDT- and USDC-settled, trading or pre-launch) is subscribed, one
topic per request (a single bad topic fails its whole subscribe batch), sharded over a few
connections. Two tables are written, in one transaction per flush:

* ``liquidations`` — one natural-keyed row per print (collectors on separate machines stitch by
  upsert-merge).
* ``liquidation_coverage`` — per-symbol spans from the symbol's subscribe ack to the last message
  heard on its connection. A crash loses at most one flush interval of prints AND of coverage
  together, so coverage never claims a window whose prints were lost.

Run: ``python -m coinmon.scraper.liquidations`` (same image as the candle scraper).
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal
import time
from dataclasses import dataclass, field

import aiohttp
import psycopg

from coinmon.data import db

log = logging.getLogger("coinmon.liquidations")

EXCHANGE = "bybit"
WS_URL = "wss://stream.bybit.com/v5/public/linear"
INSTRUMENTS_URL = "https://api.bybit.com/v5/market/instruments-info"

SHARD_SIZE = 200  # topics per connection (Bybit caps a connection's total args at ~21k chars)
PING_S = 20  # Bybit asks for an app-level ping every 20s
STALE_S = 60  # nothing heard (not even a pong) for this long -> reconnect
RECONNECT_S = 5
FLUSH_S = 10
REFRESH_S = 6 * 3600  # re-read the instrument list to pick up new listings
REPORT_S = 600


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


def parse_message(msg: dict, names: dict[str, str], recv_ms: int) -> list[tuple]:
    """Liquidation rows ``(exchange, symbol, ts, side, price, size, recv_ms)`` from one websocket
    message, symbols mapped to unified form via ``names``; ``[]`` for acks, pongs and the rest."""
    if not str(msg.get("topic", "")).startswith("allLiquidation."):
        return []
    return [
        (EXCHANGE, names.get(d["s"], d["s"]), int(d["T"]), d["S"], float(d["p"]), float(d["v"]),
         recv_ms)
        for d in msg.get("data", [])
    ]


async def fetch_perps(session: aiohttp.ClientSession) -> dict[str, str]:
    """Bybit id -> unified ``BASE/QUOTE:SETTLE`` for every trading or pre-launch linear perp."""
    names: dict[str, str] = {}
    for status in ("Trading", "PreLaunch"):
        cursor = ""
        while True:
            params = {"category": "linear", "status": status, "limit": "1000"}
            if cursor:
                params["cursor"] = cursor
            async with session.get(INSTRUMENTS_URL, params=params) as resp:
                body = await resp.json()
            if body.get("retCode") != 0:
                raise RuntimeError(f"instruments-info failed: {body.get('retMsg')}")
            for i in body["result"]["list"]:
                if i["contractType"] == "LinearPerpetual":
                    names[i["symbol"]] = f"{i['baseCoin']}/{i['quoteCoin']}:{i['settleCoin']}"
            cursor = body["result"].get("nextPageCursor") or ""
            if not cursor:
                break
    return names


async def _subscribe(ws: aiohttp.ClientWebSocketResponse, symbols: list[str]) -> None:
    for s in symbols:
        await ws.send_json({"op": "subscribe", "req_id": s, "args": [f"allLiquidation.{s}"]})


async def _ping(ws: aiohttp.ClientWebSocketResponse) -> None:
    while not ws.closed:
        await asyncio.sleep(PING_S)
        await ws.send_json({"op": "ping"})


@dataclass
class _Shard:
    """One connection's topics and the coverage it has earned since it last (re)connected."""

    symbols: list[str]
    started: dict[str, int] = field(default_factory=dict)  # symbol -> coverage start (its ack)
    last_msg_ms: int = 0
    ws: aiohttp.ClientWebSocketResponse | None = None


class LiquidationCollector:
    """Buffers prints and coverage spans from every shard until the next flush."""

    def __init__(self) -> None:
        self.names: dict[str, str] = {}
        self.shards: list[_Shard] = []
        self.rows: list[tuple] = []
        self.closed: list[tuple] = []  # spans frozen by a dropped connection, not yet written

    def _span(self, symbol: str, start: int, end: int) -> tuple[str, str, int, int]:
        return (EXCHANGE, self.names.get(symbol, symbol), start, end)

    def handle(self, shard: _Shard, msg: dict, recv_ms: int) -> None:
        shard.last_msg_ms = recv_ms
        if msg.get("op") == "subscribe":
            symbol = msg.get("req_id", "")
            if msg.get("success"):
                shard.started.setdefault(symbol, recv_ms)
            else:
                log.warning("subscribe %s failed: %s", symbol, msg.get("ret_msg"))
            return
        self.rows.extend(parse_message(msg, self.names, recv_ms))

    def end_coverage(self, shard: _Shard) -> None:
        """Connection gone: freeze its spans at the last message heard on it."""
        self.closed += [self._span(s, t, shard.last_msg_ms) for s, t in shard.started.items()]
        shard.started.clear()

    def snapshot(self) -> tuple[list[tuple], list[tuple], list[tuple]]:
        """Take ``(rows, closed, spans)`` for one flush; ``spans`` = closed + every live span."""
        rows, closed = self.rows, self.closed
        self.rows, self.closed = [], []
        live = [
            self._span(s, t, sh.last_msg_ms) for sh in self.shards for s, t in sh.started.items()
        ]
        return rows, closed, closed + live

    def restore(self, rows: list[tuple], closed: list[tuple]) -> None:
        """A failed flush puts its rows and frozen spans back in front of anything newer."""
        self.rows[:0] = rows
        self.closed[:0] = closed

    async def discover(self, session: aiohttp.ClientSession) -> list[_Shard]:
        """Sync with Bybit's current perp list: delisted symbols leave future resubscribes, new
        listings top up the last shard (live, no reconnect), overflow becomes new shards, which
        are returned for the caller to start."""
        names = await fetch_perps(session)
        new = sorted(set(names) - {s for sh in self.shards for s in sh.symbols})
        self.names.update(names)
        for sh in self.shards:
            sh.symbols = [s for s in sh.symbols if s in names]
        topped: tuple[_Shard, list[str]] | None = None
        if new and self.shards and (room := SHARD_SIZE - len(self.shards[-1].symbols)) > 0:
            last, top, new = self.shards[-1], new[:room], new[room:]
            last.symbols = last.symbols + top
            topped = (last, top)
        fresh = [_Shard(new[i : i + SHARD_SIZE]) for i in range(0, len(new), SHARD_SIZE)]
        self.shards += fresh
        if topped and topped[0].ws is not None and not topped[0].ws.closed:
            try:
                await _subscribe(topped[0].ws, topped[1])
            except Exception as exc:  # the shard's next reconnect subscribes them anyway
                log.warning("live subscribe of %d new listings failed: %r", len(topped[1]), exc)
        return fresh

    async def run_shard(self, session: aiohttp.ClientSession, shard: _Shard) -> None:
        """Keep one connection subscribed to the shard's topics; reconnect on any failure."""
        while True:
            try:
                async with session.ws_connect(WS_URL) as ws:
                    shard.ws = ws
                    await _subscribe(ws, list(shard.symbols))
                    pinger = asyncio.create_task(_ping(ws))
                    try:
                        while True:
                            msg = await ws.receive(timeout=STALE_S)
                            if msg.type is not aiohttp.WSMsgType.TEXT:
                                raise ConnectionError(f"websocket {msg.type.name}")
                            self.handle(shard, json.loads(msg.data), _now_ms())
                    finally:
                        pinger.cancel()
            except Exception as exc:  # any failure: close the spans, back off, resubscribe
                log.warning("shard %s.. dropped: %r", shard.symbols[:1], exc)
            finally:
                shard.ws = None
                self.end_coverage(shard)
            await asyncio.sleep(RECONNECT_S)


async def _flush(
    collector: LiquidationCollector, conn: psycopg.Connection | None
) -> tuple[psycopg.Connection | None, int]:
    """Write one snapshot; on failure keep it buffered and drop the (maybe broken) connection.
    Returns the connection to reuse (``None`` -> reconnect next time) and the rows written."""
    rows, closed, spans = collector.snapshot()
    try:
        if conn is None:
            conn = await asyncio.to_thread(db.connect)
        await asyncio.to_thread(db.write_liquidations, conn, rows, spans)
        return conn, len(rows)
    except Exception as exc:
        log.warning("db write failed, %d prints kept buffered: %r", len(rows), exc)
        collector.restore(rows, closed)
        if conn is not None:
            conn.close()
        return None, 0


async def collect(stop: asyncio.Event) -> None:
    """Subscribe every linear perp and flush to the DB until ``stop`` is set."""
    collector = LiquidationCollector()
    conn = await asyncio.to_thread(db.connect)
    await asyncio.to_thread(db.init_schema, conn)
    # The threaded (system) resolver: aiohttp's aiodns default fails on some hosts.
    connector = aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks: list[asyncio.Task] = []
        next_refresh = next_report = time.monotonic()
        stored = 0
        try:
            while not stop.is_set():
                if time.monotonic() >= next_refresh:
                    try:
                        fresh = await collector.discover(session)
                    except Exception as exc:
                        if not tasks:
                            raise  # nothing subscribed yet: fail loudly, let k8s restart us
                        log.warning("instrument refresh failed: %r", exc)
                        fresh = []
                    tasks += [asyncio.create_task(collector.run_shard(session, s)) for s in fresh]
                    log.info("%d perps over %d connections", len(collector.names), len(tasks))
                    next_refresh = time.monotonic() + REFRESH_S
                try:
                    await asyncio.wait_for(stop.wait(), FLUSH_S)
                except TimeoutError:
                    pass
                conn, n = await _flush(collector, conn)
                stored += n
                if time.monotonic() >= next_report:
                    covered = sum(len(s.started) for s in collector.shards)
                    log.info("%d prints stored; %d symbols covered now", stored, covered)
                    next_report = time.monotonic() + REPORT_S
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            conn, _ = await _flush(collector, conn)  # writes the spans the cancels just froze
            if conn is not None:
                conn.close()
            log.info("liquidation collector stopped")


async def _main() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop.set))
    await collect(stop)


def run() -> None:
    """Collect until SIGTERM/SIGINT; the final flush closes every open coverage span."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(_main())


if __name__ == "__main__":
    run()
