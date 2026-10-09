"""Live F8 ladder bot, PANIC and DRAIN against an in-memory venue and control store."""

from __future__ import annotations

from dataclasses import replace

import ccxt
import pytest

from coinmon.live import stop
from coinmon.live.control import DRAIN, HALT, RUN, Control, Trade
from coinmon.live.hyperliquid import Fill, Order, Position
from coinmon.live.ladder import HOLD_MS, LadderBot

T0 = 1_800_000_000_000 // 60_000 * 60_000  # a minute boundary
MIN = 60_000


class FakeHL:
    """Resting orders, positions and fills; ``trade_at`` crosses resting orders like a print."""

    venue = "fake"

    def __init__(self) -> None:
        self.mid = {"BTC": 100.0}
        self.prior_close = {"BTC": 100.0}
        self.orders: dict[int, Order] = {}
        self.pos: dict[str, Position] = {}
        self.fill_log: list[Fill] = []
        self.lev = "isolated 5"
        self.calls: list[tuple] = []
        self.reject = False
        self.now = T0
        self._oid = 0

    def positions(self):
        return dict(self.pos)

    def open_orders(self):
        return list(self.orders.values())

    def fills(self):
        return list(self.fill_log)

    def mids(self):
        return dict(self.mid)

    def last_close(self, coin, minute_ms):
        return self.prior_close[coin]

    def leverage(self, coin):
        return self.lev

    def round_px(self, coin, px):
        return round(px, 2)

    def place(self, coin, side, sz, px, *, post_only=False, reduce_only=False):
        self.calls.append(("place", coin, side, post_only, reduce_only))
        if self.reject:
            raise ccxt.InvalidOrder("Post only order would have immediately matched, bbo was ...")
        self._oid += 1
        self.orders[self._oid] = Order(coin, self._oid, "B" if side == "buy" else "A", px, sz,
                                       reduce_only)
        return self._oid

    def modify(self, oid, coin, sz, px):
        self.calls.append(("modify", coin, px))
        self.orders[oid] = replace(self.orders[oid], px=px, sz=sz)

    def cancel(self, coin, oid):
        self.calls.append(("cancel", coin, oid))
        del self.orders[oid]

    def close(self, coin, szi, mid):
        self._oid += 1
        self._fill(coin, self._oid, "A", mid, abs(szi), crossed=True)
        return self._oid

    def trade_at(self, coin, px):
        for o in list(self.orders.values()):
            if o.coin == coin and o.side == "B" and not o.reduce_only and px <= o.px:
                self._fill(coin, o.oid, "B", o.px, o.sz, crossed=False)
            elif o.coin == coin and o.side == "A" and o.reduce_only and px >= o.px:
                self._fill(coin, o.oid, "A", o.px, o.sz, crossed=False)

    def _fill(self, coin, oid, side, px, sz, crossed):
        self.orders.pop(oid, None)
        fee = px * sz * (0.00045 if crossed else 0.00015)
        self.fill_log.insert(0, Fill(coin, oid, side, px, sz, self.now, fee, crossed,
                                     "Open Long" if side == "B" else "Close Long"))
        p = self.pos.get(coin)
        szi = (p.szi if p else 0.0) + (sz if side == "B" else -sz)
        if abs(szi) < 1e-12:
            self.pos.pop(coin, None)
        else:
            self.pos[coin] = Position(coin, szi, p.entry_px if p else px, self.lev, px * 0.8)


class MemStore:
    bot = "test"

    def __init__(self, mode: str) -> None:
        self.ctl = Control(mode, "test", None, 0, None)
        self.rows: dict[int, Trade] = {}
        self.fail = False

    def read(self):
        if self.fail:
            raise RuntimeError("db down")
        return self.ctl

    def set_mode(self, mode, reason, deadline_ms=None):
        self.ctl = Control(mode, reason, deadline_ms, 0, self.ctl.heartbeat_ms)

    def heartbeat(self, ts_ms):
        self.ctl = replace(self.ctl, heartbeat_ms=ts_ms)

    def save_trade(self, t):
        self.rows[t.entry_oid] = replace(t)

    def trades(self, venue, open_only=False, limit=1000):
        return [t for t in self.rows.values() if not open_only or t.exit_ms is None]


def make(mode=RUN):
    hl, store = FakeHL(), MemStore(mode)
    return hl, store, LadderBot(hl, store, rung_usd=12.0, coins=("BTC",))


def bids(hl):
    return [o for o in hl.open_orders() if not o.reduce_only]


def exits(hl):
    return [o for o in hl.open_orders() if o.reduce_only]


def fill_bid(hl, bot, at):
    """Rest a bid at T0, let a wick through it at ``at``, run the cycle that sees the position."""
    bot.cycle(T0)
    hl.now = at
    hl.trade_at("BTC", 97.0)
    bot.cycle(at)


def test_halt_places_nothing():
    hl, store, bot = make(HALT)
    bot.cycle(T0)
    assert hl.open_orders() == [] and store.ctl.heartbeat_ms == T0


def test_run_rests_one_post_only_bid_at_the_rung():
    hl, _, bot = make()
    bot.cycle(T0)
    bot.cycle(T0 + 3_000)
    [o] = hl.open_orders()
    assert (o.side, o.px, o.reduce_only) == ("B", 97.5, False)
    assert o.sz == pytest.approx(12.0 / 97.5)
    assert hl.calls == [("place", "BTC", "buy", True, False)]


def test_bid_repegs_only_past_the_deadband():
    hl, _, bot = make()
    bot.cycle(T0)
    hl.prior_close["BTC"] = 100.05  # rung 97.55: moved 0.05%
    bot.cycle(T0 + MIN)
    assert not [c for c in hl.calls if c[0] == "modify"]
    hl.prior_close["BTC"] = 100.2  # rung 97.70: moved 0.2%
    bot.cycle(T0 + 2 * MIN)
    assert [c for c in hl.calls if c[0] == "modify"] == [("modify", "BTC", 97.7)]


def test_fill_rests_a_take_profit_and_records_the_entry():
    hl, store, bot = make()
    fill_bid(hl, bot, T0 + 5_000)
    [trade] = store.rows.values()
    assert (trade.fill_px, trade.fill_ms, trade.anchor_close) == (97.5, T0 + 5_000, 100.0)
    assert trade.leverage == "isolated 5" and trade.entry_fee > 0 and trade.exit_ms is None
    [tp] = exits(hl)
    assert (tp.side, tp.px, tp.sz) == ("A", 98.67, trade.sz) and trade.tp_oid == tp.oid
    assert bids(hl) == []  # one position per coin


def test_take_profit_exit_closes_the_row_and_rearms_the_bid():
    hl, store, bot = make()
    fill_bid(hl, bot, T0 + 5_000)
    hl.now = T0 + 20 * MIN
    hl.trade_at("BTC", 99.0)
    bot.cycle(T0 + 20 * MIN)
    [trade] = store.rows.values()
    assert (trade.exit_reason, trade.exit_px, trade.exit_ms) == ("tp", 98.67, T0 + 20 * MIN)
    assert trade.exit_dir == "Close Long" and trade.exit_fee > 0
    assert len(bids(hl)) == 1 and exits(hl) == []


def test_time_stop_swaps_the_take_profit_for_a_market_close():
    hl, store, bot = make()
    fill_bid(hl, bot, T0 + 5_000)
    hl.mid["BTC"] = 97.0
    hl.now = T0 + 5_000 + HOLD_MS
    bot.cycle(hl.now)
    assert hl.positions() == {} and exits(hl) == []
    bot.cycle(hl.now + 3_000)
    [trade] = store.rows.values()
    assert (trade.exit_reason, trade.exit_px) == ("time", 97.0)


def test_db_outage_is_no_new_risk():
    hl, store, bot = make()
    bot.cycle(T0)
    store.fail = True
    bot.cycle(T0 + 3_000)
    assert hl.open_orders() == [] and store.ctl.heartbeat_ms == T0


def test_db_outage_still_works_the_exits():
    hl, store, bot = make()
    fill_bid(hl, bot, T0 + 5_000)
    store.fail = True
    hl.now = T0 + 5_000 + HOLD_MS
    bot.cycle(hl.now)
    assert hl.positions() == {}


def test_halt_keeps_the_ledger_but_works_no_exits():
    hl, store, bot = make()
    bot.cycle(T0)
    store.set_mode(HALT, "test")
    hl.now = T0 + 5_000
    hl.trade_at("BTC", 97.0)  # the bid filled before the bot saw HALT and cancelled it
    bot.cycle(hl.now)
    assert len(store.rows) == 1 and exits(hl) == []


def test_rejected_bid_retries_next_minute_not_next_cycle():
    hl, _, bot = make()
    hl.reject = True
    bot.cycle(T0)
    bot.cycle(T0 + 3_000)
    assert len(hl.calls) == 1
    bot.cycle(T0 + MIN)
    assert len(hl.calls) == 2


def test_refuses_cross_margin():
    hl, _, bot = make()
    hl.lev = "cross 5"
    with pytest.raises(SystemExit, match="isolated"):
        bot.check()


def test_panic_flattens_everything_and_persists_halt():
    hl, store, bot = make()
    fill_bid(hl, bot, T0 + 5_000)
    hl.place("BTC", "buy", 0.1, 90.0, post_only=True)  # a stray bid too
    assert stop.panic(hl, store, "manual panic", wait_s=0)
    assert hl.positions() == {} and hl.open_orders() == []
    assert (store.ctl.mode, store.ctl.reason) == (HALT, "manual panic")
    bot.cycle(T0 + 2 * MIN)
    assert hl.open_orders() == []
    [trade] = store.rows.values()
    assert trade.exit_reason == "other"


def test_drain_keeps_exits_then_panics_at_the_deadline():
    hl, store, bot = make()
    fill_bid(hl, bot, T0 + 5_000)
    hl.place("BTC", "buy", 0.1, 90.0, post_only=True)
    deadline = T0 + 30 * MIN
    store.set_mode(DRAIN, "manual drain", deadline)
    assert not stop.drain_step(hl, store, deadline, T0 + 10 * MIN, wait_s=0)
    assert bids(hl) == [] and len(exits(hl)) == 1 and store.ctl.mode == DRAIN
    assert stop.drain_step(hl, store, deadline, deadline, wait_s=0)
    assert hl.positions() == {} and store.ctl.mode == HALT


def test_drain_halts_as_soon_as_flat():
    hl, store, bot = make()
    bot.cycle(T0)
    store.set_mode(DRAIN, "manual drain", T0 + 90 * MIN)
    bot.cycle(T0 + 3_000)
    assert hl.open_orders() == [] and (store.ctl.mode, store.ctl.reason) == (HALT, "drained")
