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

One deviation from the frozen rule, forced by the venue: a resting bid is re-pegged only once it
sits >= REPEG_SHALLOW above its rung or >= REPEG_DEEP below it. Hyperliquid budgets actions per
address (10k, then 1 per USDC traded, then one per 10s); a 0.1% band both ways spent ~2,000 a day
on six coins. ``probes/f8_repeg_deadband.py`` priced the asymmetric band on 2021-2026 perp 1m: 85%
fewer actions, F8 per-event net unchanged. Once the budget is spent, writes wait for the venue's
next slot (``Hyperliquid.write_wait_s``), exits ahead of bids.
"""

from __future__ import annotations

import logging
import signal
import time
from dataclasses import dataclass

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
# Re-peg a resting bid once it sits 0.1% above its rung (price fell: it would buy a smaller drop
# than the rule) or 1% below it (price rose: it only misses fills).
REPEG_SHALLOW = 0.001
REPEG_DEEP = 0.01
POLL_S = 3.0  # a cycle costs ~22 of the venue's 1200/min IP request weight
# The venue's open-orders read lags its writes by seconds (seen live: a fresh take-profit missing
# from the read, so it was placed three times; a modified bid's old, cancelled order still listed).
# After writing an order, the bot trusts no read that contradicts it for this long.
SETTLE_MS = 10_000
STARTUP_RETRY_MAX_S = 60.0


@dataclass(frozen=True)
class Rule:
    """A ladder's knobs: the rung below the prior 1m close, the take-profit from the fill, the
    time-stop, and an optional trend gate: bid only while the prior close is at or above the
    close ``trend_ms`` earlier (``close_before`` on the venue)."""

    drop: float
    target: float
    hold_ms: int
    trend_ms: int | None = None


F8 = Rule(DROP, TARGET, HOLD_MS)


class LadderBot:
    def __init__(self, hl: Hyperliquid, store: Store, rung_usd: float,
                 coins: tuple[str, ...] = COINS, rule: Rule = F8) -> None:
        self.hl = hl
        self.store = store
        self.rung_usd = rung_usd
        self.coins = coins
        self.rule = rule
        self.log = logging.getLogger(f"{log.name}.{store.bot}")
        self.trades: dict[str, Trade] = {t.coin: t for t in store.trades(hl.venue, open_only=True)}
        self.anchor: dict[str, tuple[int, float]] = {}  # coin -> (minute, prior 1m close)
        self.pegged: dict[str, float] = {}  # coin -> close its resting bid was pegged from
        self.failed: dict[str, int] = {}  # coin -> minute its bid was rejected (retry next minute)
        self.bid_wrote: dict[str, int] = {}  # coin -> when its bid was last placed or modified
        self.exit_wrote: dict[str, int] = {}  # coin -> when its take-profit or close was last sent

    def check(self) -> dict[str, str]:
        """Each coin's leverage as set on the venue. Refuses to run on a setup that cannot work or
        is unsafe, saying which: an account this network has never seen, an API wallet's address
        given as the account, the main wallet's own key, or any coin on cross margin."""
        hl = self.hl
        role = hl.role()
        if role == "missing":
            raise SystemExit(
                f"{hl.address} has no account on {hl.venue} (testnet and mainnet are separate)."
                " Set it up there: fund it (testnet: claim the faucet), create an API wallet,"
                " set isolated margin"
            )
        if role == "agent":
            raise SystemExit(
                f"{hl.address} is an API wallet; COINMON_HL_ADDRESS must be your main wallet"
            )
        if hl.agent == hl.address.lower():
            raise SystemExit(
                "COINMON_HL_AGENT_KEY is your main wallet's key, which can withdraw:"
                " use an API wallet's key"
            )
        if hl.agent not in hl.approved_agents():
            self.log.warning("API wallet %s is not among the named API wallets of %s on %s;"
                             " orders will be rejected unless it is approved there",
                             hl.agent, hl.address, hl.venue)
        if hl.account_value() <= 0:
            self.log.warning("%s has no USDC margin on %s, so bids will be rejected (testnet:"
                             " claim the faucet; a non-unified account: move USDC from Spot to"
                             " Perps)", hl.address, hl.venue)
        lev = {c: self.hl.leverage(c) for c in self.coins}
        cross = {c: v for c, v in lev.items() if not v.startswith("isolated")}
        if cross:
            raise SystemExit(f"isolated margin required; set it per coin on the venue: {cross}")
        return lev

    def cycle(self, ts_ms: int) -> None:
        try:
            ctl = self.store.read()
        except Exception:
            self.log.exception("control store unreachable: no new risk this cycle")
            ctl = None
        mode = ctl.mode if ctl else None
        positions = self.hl.positions()
        orders = self.hl.open_orders()
        # Who gets a throttled venue's next write: exits first, then the longest-unmoved bid.
        for coin in sorted(self.coins, key=lambda c: (c not in positions,
                                                      self.bid_wrote.get(c, -SETTLE_MS))):
            try:
                self._manage(coin, ts_ms, mode, positions.get(coin),
                             [o for o in orders if o.coin == coin])
            except Exception:
                self.log.exception("%s: step failed", coin)
        if mode == DRAIN:
            stop.drain_step(self.hl, self.store, ctl.deadline_ms, ts_ms)
        if ctl is not None:
            self.store.heartbeat(ts_ms)

    def _manage(self, coin: str, ts_ms: int, mode: str | None, pos: Position | None,
                orders: list[Order]) -> None:
        bids = [o for o in orders if o.side == "B" and not o.reduce_only]
        exits = [o for o in orders if o.side == "A" and o.reduce_only]
        if pos is not None and pos.szi < 0:
            self.log.warning("%s: short %s on the venue is not this bot's, left alone", coin,
                             pos.szi)
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
        if ts_ms - self.exit_wrote.get(coin, -SETTLE_MS) < SETTLE_MS:
            return  # the read may not show the exit order just sent
        due = ts_ms >= trade.fill_ms + self.rule.hold_ms
        if (exits and not due) or self.hl.write_wait_s() > 0:
            return
        if due:
            for o in exits:
                self.hl.cancel(coin, o.oid)
            trade.time_oid = self.hl.close(coin, pos.szi, self.hl.mids()[coin])
            self.exit_wrote[coin] = ts_ms
            self.store.save_trade(trade)
        else:
            trade.tp_px = self.hl.round_px(coin, trade.fill_px * (1 + self.rule.target))
            trade.tp_oid = self.hl.place(coin, "sell", pos.szi, trade.tp_px, reduce_only=True)
            self.exit_wrote[coin] = ts_ms
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
        self.log.info("%s: filled %s @ %s (%s, liq %s)", coin, sz, trade.fill_px, pos.leverage,
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
        self.log.info("%s: exit %s @ %s", coin, trade.exit_reason, trade.exit_px)

    def _trend_up(self, coin: str, minute: int, close: float) -> bool:
        """The rule's trend gate (always open without one). No reference close means no bid."""
        if self.rule.trend_ms is None:
            return True
        then = self.hl.close_before(coin, minute - self.rule.trend_ms)
        return then is not None and close >= then

    def _peg(self, coin: str, ts_ms: int, bids: list[Order]) -> None:
        """Rest one post-only bid at the prior 1m close -drop, re-pegged past the REPEG bands,
        while the trend gate is open."""
        minute = ts_ms // 60_000 * 60_000
        if self.failed.get(coin) == minute:
            return
        if ts_ms - self.bid_wrote.get(coin, -SETTLE_MS) < SETTLE_MS:
            return  # the read may not show the bid just placed or modified
        if self.anchor.get(coin, (None,))[0] != minute:
            close = self.hl.last_close(coin, minute)
            if close is None:
                return
            self.anchor[coin] = (minute, close)
        close = self.anchor[coin][1]
        if not self._trend_up(coin, minute, close):
            for b in bids:
                self.hl.cancel(coin, b.oid)
            return
        rung = self.hl.round_px(coin, close * (1 - self.rule.drop))
        sz = self.rung_usd / rung
        for b in bids[1:]:
            self.hl.cancel(coin, b.oid)
        if bids and -REPEG_DEEP < bids[0].px / rung - 1 < REPEG_SHALLOW:
            return
        if self.hl.write_wait_s() > 0:
            return
        try:
            if not bids:
                self.hl.place(coin, "buy", sz, rung, post_only=True)
            else:
                self.hl.modify(bids[0].oid, coin, sz, rung)
        except ccxt.ExchangeError as e:
            self.failed[coin] = minute
            self.log.warning("%s: bid at %s rejected, retrying next minute: %s", coin, rung, e)
            return
        self.bid_wrote[coin] = ts_ms
        self.pegged[coin] = close


def until_reachable(what: str, fn):
    """``fn()``, retried with backoff while the venue is unreachable (DNS, timeouts), so a network
    blip at startup does not crash-loop the pod. Anything else, e.g. bad config, still raises."""
    delay = 5.0
    while True:
        try:
            return fn()
        except ccxt.NetworkError as e:
            log.warning("%s: venue unreachable, retrying in %.0fs: %s", what, delay, e)
            time.sleep(delay)
            delay = min(delay * 2, STARTUP_RETRY_MAX_S)


def _sigterm(*_) -> None:
    raise SystemExit(0)


def run(hl: Hyperliquid, store: Store, rung_usd: float) -> None:
    """Run the ladder until stopped. On exit, entry bids are cancelled; exits stay resting."""
    store.init()
    coins = hl.listed(COINS)
    if skipped := [c for c in COINS if c not in coins]:
        log.warning("not listed on %s, skipped: %s", hl.venue, skipped)  # testnet lacks XRP
    bot = LadderBot(hl, store, rung_usd, coins)
    log.info("%s %s: leverage %s, %s USDC per rung, mode %s", hl.venue, hl.address,
             until_reachable("leverage check", bot.check), rung_usd, store.read().mode)
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
