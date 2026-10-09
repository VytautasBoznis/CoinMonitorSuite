"""Persisted live-bot state: the RUN / DRAIN / HALT mode, the heartbeat, and the trade ledger
(tables ``bot_control`` and ``bot_trades`` in ``data/schema.sql``)."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, fields

from coinmon.data import db

RUN, DRAIN, HALT = "RUN", "DRAIN", "HALT"
BOT = "f8-ladder"


def now_ms() -> int:
    return time.time_ns() // 1_000_000


@dataclass(frozen=True)
class Control:
    mode: str
    reason: str
    deadline_ms: int | None
    updated_ms: int
    heartbeat_ms: int | None


@dataclass
class Trade:
    bot: str
    venue: str
    coin: str
    entry_oid: int
    anchor_close: float | None
    sz: float
    fill_px: float
    fill_ms: int
    entry_fee: float
    leverage: str
    liq_px: float | None
    tp_px: float | None = None
    tp_oid: int | None = None
    time_oid: int | None = None
    exit_px: float | None = None
    exit_ms: int | None = None
    exit_fee: float | None = None
    exit_reason: str | None = None
    exit_dir: str | None = None


_COLS = [f.name for f in fields(Trade)]


class Store:
    """One bot's rows. A fresh connection per call, so a DB restart heals on the next cycle."""

    def __init__(self, bot: str = BOT, dsn: str | None = None) -> None:
        self.bot = bot
        self._dsn = dsn

    def init(self) -> None:
        with db.connect(self._dsn) as conn:
            db.init_schema(conn)

    def read(self) -> Control:
        """The current mode; a bot with no row yet is created HALT."""
        with db.connect(self._dsn) as conn:
            conn.execute(
                "INSERT INTO bot_control (bot, mode, reason, updated_ms) VALUES (%s, %s, %s, %s)"
                " ON CONFLICT (bot) DO NOTHING",
                (self.bot, HALT, "initial", now_ms()),
            )
            row = conn.execute(
                "SELECT mode, reason, deadline_ms, updated_ms, heartbeat_ms FROM bot_control"
                " WHERE bot = %s",
                (self.bot,),
            ).fetchone()
        return Control(*row)

    def set_mode(self, mode: str, reason: str, deadline_ms: int | None = None) -> None:
        with db.connect(self._dsn) as conn:
            conn.execute(
                "INSERT INTO bot_control (bot, mode, reason, deadline_ms, updated_ms)"
                " VALUES (%s, %s, %s, %s, %s) ON CONFLICT (bot) DO UPDATE SET mode = EXCLUDED.mode,"
                " reason = EXCLUDED.reason, deadline_ms = EXCLUDED.deadline_ms,"
                " updated_ms = EXCLUDED.updated_ms",
                (self.bot, mode, reason, deadline_ms, now_ms()),
            )

    def heartbeat(self, ts_ms: int) -> None:
        with db.connect(self._dsn) as conn:
            conn.execute(
                "UPDATE bot_control SET heartbeat_ms = %s WHERE bot = %s", (ts_ms, self.bot)
            )

    def save_trade(self, t: Trade) -> None:
        cols = ", ".join(_COLS)
        marks = ", ".join(["%s"] * len(_COLS))
        updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in _COLS[4:])
        with db.connect(self._dsn) as conn:
            conn.execute(
                f"INSERT INTO bot_trades ({cols}) VALUES ({marks})"
                f" ON CONFLICT (bot, venue, entry_oid) DO UPDATE SET {updates}",
                tuple(asdict(t).values()),
            )

    def trades(self, venue: str, open_only: bool = False, limit: int = 1000) -> list[Trade]:
        """Newest first."""
        where = " AND exit_ms IS NULL" if open_only else ""
        with db.connect(self._dsn) as conn:
            rows = conn.execute(
                f"SELECT {', '.join(_COLS)} FROM bot_trades WHERE bot = %s AND venue = %s{where}"
                " ORDER BY fill_ms DESC LIMIT %s",
                (self.bot, venue, limit),
            ).fetchall()
        return [Trade(*r) for r in rows]
