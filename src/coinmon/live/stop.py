"""PANIC and DRAIN, the two manual stops ([[live-bot-dashboard-plan]]).

Neither needs the bot process: ``coinmon stop`` (and later the dashboard buttons) call these same
functions with just a venue client and the control store. Flatness is always the venue's answer,
re-queried, never anyone's memory.
"""

from __future__ import annotations

import logging
import time

from coinmon.live.control import HALT, Store
from coinmon.live.hyperliquid import Hyperliquid

log = logging.getLogger("coinmon.stop")


def panic(hl: Hyperliquid, store: Store, reason: str, tries: int = 5, wait_s: float = 2.0) -> bool:
    """Persist HALT, cancel every order, close every position at market, and repeat until the
    venue reports flat. True once it does. HALT is written first so a running bot stops placing;
    if the DB is down the flattening still happens."""
    try:
        store.set_mode(HALT, reason)
    except Exception:
        log.exception("could not persist HALT; flattening anyway")
    for _ in range(tries):
        for o in hl.open_orders():
            hl.cancel(o.coin, o.oid)
        positions = hl.positions()
        if positions:
            mids = hl.mids()
            for p in positions.values():
                hl.close(p.coin, p.szi, mids[p.coin])
        time.sleep(wait_s)
        if not hl.positions() and not hl.open_orders():
            return True
    return False


def drain_step(hl: Hyperliquid, store: Store, deadline_ms: int | None, ts_ms: int,
               wait_s: float = 2.0) -> bool:
    """One DRAIN pass: cancel entry bids and leave exits working, HALT once flat, PANIC once past
    the deadline (again on every pass until flat). True when the drain is finished (flat)."""
    for o in hl.open_orders():
        if o.side == "B" and not o.reduce_only:
            hl.cancel(o.coin, o.oid)
    if not hl.positions():
        store.set_mode(HALT, "drained")
        return True
    if deadline_ms is not None and ts_ms >= deadline_ms:
        return panic(hl, store, "drain deadline", wait_s=wait_s)
    return False
