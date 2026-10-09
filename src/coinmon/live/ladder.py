"""F8 liquidation-cascade ladder, live on Hyperliquid perps.

The frozen F8 rule (``probes/f8_cascade_ladder_proxy.py``) run for real on six of its ten coins:
one resting post-only bid per coin at the prior 1m close -2.5%, a resting reduce-only take-profit
at +1.2% from the fill, and a market exit at 60 minutes. One position per coin at a time. Each
round trip lands in ``bot_trades`` with what the rule assumed next to what the venue did. Licensed
as micro-live data gathering only ([[cursed-100-eur-live-ladder]]), never a deployment.

Safety model:
  * The persisted mode is read every cycle. A new bot starts HALT and places nothing until
    ``coinmon bot resume``. PANIC and DRAIN (``live/stop.py``) work without this process.
  * Anything but RUN, including an unreachable DB, means no new risk: entry bids are cancelled.
    DRAIN and a DB outage still work the exits; HALT only keeps the ledger.
  * State lives on the venue and is re-read every cycle, so a restart loses only the anchor close
    of a fill that happened while the bot was down.

One deviation from the frozen rule, forced by the venue: a resting bid is re-pegged only once its
rung has moved >= DEADBAND. Hyperliquid budgets actions per address (10k, then 1 per USDC traded);
re-pegging three bids every minute would spend that in about two days.
"""

from __future__ import annotations

import logging
import signal
import time

import ccxt

from coinmon.live import stop
from coinmon.live.control import DRAIN, HALT, RUN, Store, Trade, now_ms
from coinmon.live.hyperliquid import Hyperliquid, Order, Position

log = logging.getLogger("coinmon.ladder")

# The owner's pick (2026-10-09) from the ten F8 was tested on: the majors plus the three alts that
# hit the rung most often. BTC alone touched it on 3 days in the 24 months to 2026-09.
COINS = ("BTC", "ETH", "SOL", "DOGE", "XRP", "ADA")
DROP = 0.025  # frozen F8 rung: 2.5% below the prior 1m close
TARGET = 0.012  # frozen F8 take-profit: +1.2% from the fill
HOLD_MS = 60 * 60_000  # frozen F8 time-stop: exit at market after 60 minutes
DEADBAND = 0.001  # re-peg a resting bid only once its rung moved >= 0.1%
POLL_S = 3.0  # a cycle costs ~22 of the venue's 1200/min IP request weight


class LadderBot:
    def __init__(self, hl: Hyperliquid, store: Store, rung_usd: float,
                 coins: tuple[str, ...] = COINS) -> None:
        self.hl = hl
        self.store = store
        self.rung_usd = rung_usd
        self.coins = coins
        self.trades: dict[str, Trade] = {t.coin: t for t in store.trades(hl.venue, open_only=True)}
        self.anchor: dict[str, tuple[int, float]] = {}  # coin -> (minute, prior 1m close)
        self.pegged: dict[str, float] = {}  # coin -> close its resting bid was pegged from
        self.failed: dict[str, int] = {}  # coin -> minute its bid was rejected (retry next minute)

    def check(self) -> dict[str, str]:
        """Each coin's leverage as set on the venue. Refuses to run unless all are isolated."""
        lev = {c: self.hl.leverage(c) for c in self.coins}
        cross = {c: v for c, v in lev.items() if not v.startswith("isolated")}
        if cross:
            raise SystemExit(f"isolated margin required; set it per coin on the venue: {cross}")
        return lev

    def cycle(self, ts_ms: int) -> None:
        try:
            ctl = self.store.read()
        except Exception:
            log.exception("control store unreachable: no new risk this cycle")
            ctl = None
        mode = ctl.mode if ctl else None
        positions = self.hl.positions()
        orders = self.hl.open_orders()
        for coin in self.coins:
            try:
                self._manage(coin, ts_ms, mode, positions.get(coin),
                             [o for o in orders if o.coin == coin])
            except Exception:
                log.exception("%s: step failed", coin)
        if mode == DRAIN:
            stop.drain_step(self.hl, self.store, ctl.deadline_ms, ts_ms)
        if ctl is not None:
            self.store.heartbeat(ts_ms)

    def _manage(self, coin: str, ts_ms: int, mode: str | None, pos: Position | None,
                orders: list[Order]) -> None:
        bids = [o for o in orders if o.side == "B" and not o.reduce_only]
        exits = [o for o in orders if o.side == "A" and o.reduce_only]
        if pos is not None and pos.szi < 0:
            log.warning("%s: short %s on the venue is not this bot's, left alone", coin, pos.szi)
            return
        if pos is not None:
            for b in bids:  # one position per coin; also drops the rest of a partial fill
                self.hl.cancel(coin, b.oid)
            trade = self.trades.get(coin) or self._entry(coin, pos)
            if mode != HALT:
                self._work_exit(coin, ts_ms, pos, trade, exits)
            return
        if coin in self.trades:
            self._exit(coin, ts_ms)
        for o in exits:  # orphaned by the closed position
            self.hl.cancel(coin, o.oid)
        if mode != RUN:
            for b in bids:
                self.hl.cancel(coin, b.oid)
            return
        self._peg(coin, ts_ms, bids)

    def _work_exit(self, coin: str, ts_ms: int, pos: Position, trade: Trade,
                   exits: list[Order]) -> None:
        """Keep a take-profit resting; at the time-stop, swap it for a market close."""
        if ts_ms >= trade.fill_ms + HOLD_MS:
            for o in exits:
                self.hl.cancel(coin, o.oid)
            trade.time_oid = self.hl.close(coin, pos.szi, self.hl.mids()[coin])
            self.store.save_trade(trade)
        elif not exits:
            trade.tp_px = self.hl.round_px(coin, trade.fill_px * (1 + TARGET))
            trade.tp_oid = self.hl.place(coin, "sell", pos.szi, trade.tp_px, reduce_only=True)
            self.store.save_trade(trade)

    def _entry(self, coin: str, pos: Position) -> Trade:
        """Ledger row for a position that just appeared, built from the venue's fills."""
        buys = [f for f in self.hl.fills() if f.coin == coin and f.side == "B"]
        oid = max(buys, key=lambda f: f.time).oid  # the newest opening order is this position's
        legs = [f for f in buys if f.oid == oid]
        sz = sum(f.sz for f in legs)
        trade = Trade(
            bot=self.store.bot, venue=self.hl.venue, coin=coin, entry_oid=oid,
            anchor_close=self.pegged.pop(coin, None), sz=sz,
            fill_px=sum(f.px * f.sz for f in legs) / sz, fill_ms=min(f.time for f in legs),
            entry_fee=sum(f.fee for f in legs), leverage=pos.leverage, liq_px=pos.liq_px,
        )
        self.trades[coin] = trade
        self.store.save_trade(trade)
        log.info("%s: filled %s @ %s (%s, liq %s)", coin, sz, trade.fill_px, pos.leverage,
                 pos.liq_px)
        return trade

    def _exit(self, coin: str, ts_ms: int) -> None:
        """Close the ledger row of a position the venue no longer shows."""
        trade = self.trades[coin]
        sells = sorted((f for f in self.hl.fills()
                        if f.coin == coin and f.side == "A" and f.time >= trade.fill_ms),
                       key=lambda f: f.time)
        if sells:
            sz = sum(f.sz for f in sells)
            last = sells[-1]
            trade.exit_px = sum(f.px * f.sz for f in sells) / sz
            trade.exit_ms = last.time
            trade.exit_fee = sum(f.fee for f in sells)
            if last.oid == trade.tp_oid:
                trade.exit_reason = "tp"
            elif last.oid == trade.time_oid:
                trade.exit_reason = "time"
            else:
                trade.exit_reason = "other"
            trade.exit_dir = last.dir
        else:
            trade.exit_ms, trade.exit_reason, trade.exit_dir = ts_ms, "other", "no fill"
        self.store.save_trade(trade)
        del self.trades[coin]
        log.info("%s: exit %s @ %s", coin, trade.exit_reason, trade.exit_px)

    def _peg(self, coin: str, ts_ms: int, bids: list[Order]) -> None:
        """Rest one post-only bid at the prior 1m close -DROP, re-pegged past DEADBAND."""
        minute = ts_ms // 60_000 * 60_000
        if self.failed.get(coin) == minute:
            return
        if self.anchor.get(coin, (None,))[0] != minute:
            close = self.hl.last_close(coin, minute)
            if close is None:
                return
            self.anchor[coin] = (minute, close)
        close = self.anchor[coin][1]
        rung = self.hl.round_px(coin, close * (1 - DROP))
        sz = self.rung_usd / rung
        for b in bids[1:]:
            self.hl.cancel(coin, b.oid)
        try:
            if not bids:
                self.hl.place(coin, "buy", sz, rung, post_only=True)
            elif abs(bids[0].px / rung - 1) >= DEADBAND:
                self.hl.modify(bids[0].oid, coin, sz, rung)
            else:
                return
        except ccxt.ExchangeError as e:
            self.failed[coin] = minute
            log.warning("%s: bid at %s rejected, retrying next minute: %s", coin, rung, e)
            return
        self.pegged[coin] = close


def _sigterm(*_) -> None:
    raise SystemExit(0)


def run(hl: Hyperliquid, store: Store, rung_usd: float) -> None:
    """Run the ladder until stopped. On exit, entry bids are cancelled; exits stay resting."""
    store.init()
    coins = hl.listed(COINS)
    if skipped := [c for c in COINS if c not in coins]:
        log.warning("not listed on %s, skipped: %s", hl.venue, skipped)  # testnet lacks XRP
    bot = LadderBot(hl, store, rung_usd, coins)
    log.info("%s %s: leverage %s, %s USDC per rung, mode %s", hl.venue, hl.address, bot.check(),
             rung_usd, store.read().mode)
    signal.signal(signal.SIGTERM, _sigterm)  # docker stop -> SystemExit -> the finally below
    try:
        while True:
            started = time.monotonic()
            try:
                bot.cycle(now_ms())
            except Exception:
                log.exception("cycle failed")
            time.sleep(max(0.0, POLL_S - (time.monotonic() - started)))
    finally:
        for o in hl.open_orders():
            if o.coin in bot.coins and o.side == "B" and not o.reduce_only:
                hl.cancel(o.coin, o.oid)
        log.info("stopped: entry bids cancelled, exits left resting")
