from __future__ import annotations

import logging
import signal
import threading
from datetime import UTC, datetime

import psycopg

from coinmon.config import settings
from coinmon.data import db
from coinmon.data.adapters.base import ExchangeAdapter, timeframe_to_ms
from coinmon.data.adapters.bybit import BybitAdapter

log = logging.getLogger("coinmon.scraper")


def _start_ms(iso_date: str) -> int:
    """Epoch ms (UTC) for the configured backfill start date (e.g. ``"2025-01-01"``)."""
    dt = datetime.fromisoformat(iso_date).replace(tzinfo=UTC)
    return int(dt.timestamp() * 1000)


def ingest_series(
    adapter: ExchangeAdapter,
    conn: psycopg.Connection,
    symbol: str,
    timeframe: str,
) -> int:
    """Pull every closed bar from the last stored one (or backfill start) up to now.

    The single ingest path used for BOTH initial backfill and each poll cycle: when the
    series is empty it backfills from ``backfill_start``; once current, each call adds only
    the few new bars. Archives each raw page and upserts the normalized candles.
    """
    step = timeframe_to_ms(timeframe)
    last = db.last_open_time(conn, adapter.name, symbol, timeframe)
    cursor = last + step if last is not None else _start_ms(settings.backfill_start)

    stored = 0
    while True:
        raw = adapter.fetch_raw(symbol, timeframe, since=cursor)
        if not raw.rows:
            break
        candles = adapter.to_candles(raw)
        if candles.empty:
            break  # only the in-progress bar remained — nothing closed to store yet
        db.insert_raw(conn, raw)
        stored += db.upsert_candles(conn, candles, adapter.name, symbol, timeframe)
        cursor = int(candles["open_time"].iloc[-1]) + step
    return stored


def poll_once(adapter: ExchangeAdapter, conn: psycopg.Connection) -> int:
    """Ingest every configured (symbol, timeframe) series once."""
    total = 0
    for symbol in settings.symbols:
        for timeframe in settings.timeframes:
            n = ingest_series(adapter, conn, symbol, timeframe)
            if n:
                log.info("stored %d candles for %s %s", n, symbol, timeframe)
            total += n
    return total


def run() -> None:
    """Backfill configured series, then poll on a schedule until SIGTERM/SIGINT."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())

    adapter = BybitAdapter()
    conn = db.connect()
    try:
        db.init_schema(conn)
        log.info("backfilling %s @ %s", settings.symbols, settings.timeframes)
        poll_once(adapter, conn)  # first pass backfills from the configured start
        log.info("backfill done; polling every %ds", settings.poll_interval_seconds)

        while not stop.wait(settings.poll_interval_seconds):
            poll_once(adapter, conn)
    finally:
        conn.close()
        log.info("scraper stopped")
