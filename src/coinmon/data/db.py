from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import psycopg

from coinmon.config import settings
from coinmon.data.adapters.base import RawBatch
from coinmon.data.models import CANDLE_COLUMNS

_SCHEMA_SQL = Path(__file__).with_name("schema.sql")


def connect(dsn: str | None = None) -> psycopg.Connection:
    """Open a Postgres/Timescale connection. Defaults to the configured DSN."""
    return psycopg.connect(dsn or settings.db_dsn)


def init_schema(conn: psycopg.Connection) -> None:
    """Create tables + hypertable if absent. Idempotent — safe on every startup."""
    conn.execute(_SCHEMA_SQL.read_text(encoding="utf-8"))
    conn.commit()


def insert_raw(conn: psycopg.Connection, batch: RawBatch) -> None:
    """Archive one raw exchange payload verbatim (skips empty pages)."""
    if not batch.rows:
        return
    open_times = [r[0] for r in batch.rows]
    conn.execute(
        """
        INSERT INTO raw_candles
            (exchange, symbol, timeframe, fetched_at, open_time_start, open_time_end, payload)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            batch.exchange,
            batch.symbol,
            batch.timeframe,
            batch.fetched_at,
            min(open_times),
            max(open_times),
            json.dumps(batch.rows),
        ),
    )
    conn.commit()


def upsert_candles(
    conn: psycopg.Connection,
    df: pd.DataFrame,
    exchange: str,
    symbol: str,
    timeframe: str,
) -> int:
    """Upsert preprocessed candles. Idempotent: re-polling the same bars overwrites, no dupes."""
    if df.empty:
        return 0
    records = [
        (
            exchange,
            symbol,
            timeframe,
            int(row.open_time),
            float(row.open),
            float(row.high),
            float(row.low),
            float(row.close),
            float(row.volume),
        )
        for row in df.itertuples(index=False)
    ]
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO candles
                (exchange, symbol, timeframe, open_time, open, high, low, close, volume)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (exchange, symbol, timeframe, open_time) DO UPDATE SET
                open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
                close = EXCLUDED.close, volume = EXCLUDED.volume
            """,
            records,
        )
    conn.commit()
    return len(records)


def list_series(conn: psycopg.Connection) -> list[tuple[str, str, str]]:
    """Every stored (exchange, symbol, timeframe) series — drives the viewer's dropdowns."""
    rows = conn.execute(
        "SELECT DISTINCT exchange, symbol, timeframe FROM candles "
        "ORDER BY exchange, symbol, timeframe"
    ).fetchall()
    return [(r[0], r[1], r[2]) for r in rows]


def read_candles(
    conn: psycopg.Connection, exchange: str, symbol: str, timeframe: str
) -> pd.DataFrame:
    """Load one candle series as an OHLCV frame (``CANDLE_COLUMNS``), ordered oldest-first."""
    rows = conn.execute(
        "SELECT open_time, open, high, low, close, volume FROM candles "
        "WHERE exchange = %s AND symbol = %s AND timeframe = %s ORDER BY open_time",
        (exchange, symbol, timeframe),
    ).fetchall()
    return pd.DataFrame(rows, columns=list(CANDLE_COLUMNS))


def series_stats(
    conn: psycopg.Connection,
) -> list[tuple[str, str, str, int, int, int]]:
    """Per-series ``(exchange, symbol, timeframe, bar_count, min_open_time, max_open_time)``.

    One GROUP BY pass over ``candles`` — drives the ``coverage`` report (how many bars and
    what date span each stored series has), without loading any candle bodies.
    """
    rows = conn.execute(
        "SELECT exchange, symbol, timeframe, count(*), min(open_time), max(open_time) "
        "FROM candles GROUP BY exchange, symbol, timeframe "
        "ORDER BY exchange, timeframe, symbol"
    ).fetchall()
    return [(r[0], r[1], r[2], int(r[3]), int(r[4]), int(r[5])) for r in rows]


def insert_funding(
    conn: psycopg.Connection,
    exchange: str,
    symbol: str,
    rows: list[tuple[int, float]],
) -> int:
    """Upsert ``(funding_time, rate)`` settlements for a perp. Idempotent: re-fetching an
    already-stored window overwrites, no dupes. Returns the number of rows written."""
    if not rows:
        return 0
    records = [(exchange, symbol, int(t), float(r)) for t, r in rows]
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO funding_rates (exchange, symbol, funding_time, rate)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (exchange, symbol, funding_time) DO UPDATE SET rate = EXCLUDED.rate
            """,
            records,
        )
    conn.commit()
    return len(records)


def last_funding_time(
    conn: psycopg.Connection, exchange: str, symbol: str
) -> int | None:
    """Newest stored ``funding_time`` for a perp, or ``None`` if it has no history yet."""
    row = conn.execute(
        "SELECT max(funding_time) FROM funding_rates WHERE exchange = %s AND symbol = %s",
        (exchange, symbol),
    ).fetchone()
    return row[0] if row else None


def read_funding(
    conn: psycopg.Connection, exchange: str, symbol: str
) -> pd.DataFrame:
    """Load a perp's funding history as a ``(funding_time, rate)`` frame, oldest-first."""
    rows = conn.execute(
        "SELECT funding_time, rate FROM funding_rates "
        "WHERE exchange = %s AND symbol = %s ORDER BY funding_time",
        (exchange, symbol),
    ).fetchall()
    return pd.DataFrame(rows, columns=["funding_time", "rate"])


def insert_open_interest(
    conn: psycopg.Connection,
    exchange: str,
    symbol: str,
    timeframe: str,
    rows: list[tuple[int, float]],
) -> int:
    """Upsert ``(ts, oi_amount)`` open-interest points for a perp. Idempotent: re-fetching an
    already-stored window overwrites, no dupes. Returns the number of rows written."""
    if not rows:
        return 0
    records = [(exchange, symbol, timeframe, int(t), float(v)) for t, v in rows]
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO open_interest (exchange, symbol, timeframe, ts, oi_amount)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (exchange, symbol, timeframe, ts) DO UPDATE SET
                oi_amount = EXCLUDED.oi_amount
            """,
            records,
        )
    conn.commit()
    return len(records)


def read_open_interest(
    conn: psycopg.Connection, exchange: str, symbol: str, timeframe: str
) -> pd.DataFrame:
    """Load a perp's open-interest history as a ``(ts, oi_amount)`` frame, oldest-first."""
    rows = conn.execute(
        "SELECT ts, oi_amount FROM open_interest "
        "WHERE exchange = %s AND symbol = %s AND timeframe = %s ORDER BY ts",
        (exchange, symbol, timeframe),
    ).fetchall()
    return pd.DataFrame(rows, columns=["ts", "oi_amount"])


def write_liquidations(
    conn: psycopg.Connection,
    rows: list[tuple],
    coverage: list[tuple[str, str, int, int]],
) -> None:
    """Store liquidation prints ``(exchange, symbol, ts, side, price, size, recv_ms)`` and refresh
    coverage spans ``(exchange, symbol, start_ms, end_ms)`` in ONE transaction, so a stored span
    never claims a window whose prints were lost. Idempotent: prints are natural-keyed (re-writes
    are no-ops) and a span keeps the furthest end any collector reported for it."""
    with conn.cursor() as cur:
        if rows:
            cur.executemany(
                """
                INSERT INTO liquidations (exchange, symbol, ts, side, price, size, recv_ms)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (exchange, symbol, ts, side, price, size) DO NOTHING
                """,
                rows,
            )
        if coverage:
            cur.executemany(
                """
                INSERT INTO liquidation_coverage (exchange, symbol, start_ms, end_ms)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (exchange, symbol, start_ms) DO UPDATE SET
                    end_ms = GREATEST(liquidation_coverage.end_ms, EXCLUDED.end_ms)
                """,
                coverage,
            )
    conn.commit()


def read_liquidations(
    conn: psycopg.Connection, exchange: str, symbol: str, start_ms: int, end_ms: int
) -> pd.DataFrame:
    """One symbol's liquidation prints with ``start_ms <= ts < end_ms`` as a
    ``(ts, side, price, size)`` frame, oldest-first. Read with ``read_liquidation_coverage``."""
    rows = conn.execute(
        "SELECT ts, side, price, size FROM liquidations "
        "WHERE exchange = %s AND symbol = %s AND ts >= %s AND ts < %s ORDER BY ts",
        (exchange, symbol, start_ms, end_ms),
    ).fetchall()
    return pd.DataFrame(rows, columns=["ts", "side", "price", "size"])


def read_liquidation_coverage(
    conn: psycopg.Connection, exchange: str, symbol: str, start_ms: int, end_ms: int
) -> list[tuple[int, int]]:
    """``(start_ms, end_ms)`` coverage spans of one symbol overlapping ``[start_ms, end_ms)``."""
    rows = conn.execute(
        "SELECT start_ms, end_ms FROM liquidation_coverage "
        "WHERE exchange = %s AND symbol = %s AND end_ms > %s AND start_ms < %s "
        "ORDER BY start_ms",
        (exchange, symbol, start_ms, end_ms),
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


def last_open_time(
    conn: psycopg.Connection, exchange: str, symbol: str, timeframe: str
) -> int | None:
    """Newest stored ``open_time`` for a series, or ``None`` if it has no history yet."""
    row = conn.execute(
        """
        SELECT max(open_time) FROM candles
        WHERE exchange = %s AND symbol = %s AND timeframe = %s
        """,
        (exchange, symbol, timeframe),
    ).fetchone()
    return row[0] if row else None


# Keep the candle column contract importable next to the writers that depend on it.
__all__ = [
    "CANDLE_COLUMNS",
    "connect",
    "init_schema",
    "insert_funding",
    "insert_open_interest",
    "insert_raw",
    "last_funding_time",
    "last_open_time",
    "list_series",
    "read_candles",
    "read_funding",
    "read_liquidation_coverage",
    "read_liquidations",
    "read_open_interest",
    "series_stats",
    "upsert_candles",
    "write_liquidations",
]
