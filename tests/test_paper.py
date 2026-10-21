"""Paper venue + swarm: paper bots run the live LadderBot and fill like the F8 backtests."""

from __future__ import annotations

import numpy as np
import pytest
from test_bot import MemStore

from coinmon.live import ladder, paper, swarm
from coinmon.live.control import RUN, Trade, bot_on
from coinmon.live.ladder import F8, LadderBot, Rule
from coinmon.live.paper import CLOSE_GRACE_MS, MAKER, MIN, PAPER, TAKER, HLMarket, PaperVenue

T0 = 1_800_000_000_000 // MIN * MIN


class FakeX:
    """ccxt's hyperliquid, public calls only, serving 1m candles from arrays. Like the venue, a
    candle request also returns the candle still forming, with its final values here: a paper
    bot that read it would trade on the future."""

    def __init__(self, high, low, close, coins=("BTC",)) -> None:
        self.high, self.low, self.close = high, low, close
        self.now = T0
        self.markets = {f"{c}/USDC:USDC": {} for c in coins}
        self.hour_close: dict[tuple[str, int], float] = {}
        self.requests: list[dict] = []

    def load_markets(self):
        return self.markets

    def price_to_precision(self, symbol, px):
        return str(px)

    def publicPostInfo(self, body):
        self.requests.append(body)
        if body["type"] == "allMids":
            return {"BTC": str(self.close[(self.now - T0) // MIN - 1])}
        req = body["req"]
        if req["interval"] == "1h":
            c = self.hour_close.get((req["coin"], req["startTime"]))
            return [] if c is None else [{"t": req["startTime"], "c": str(c)}]
        forming = self.now // MIN * MIN
        k0 = max(0, (req["startTime"] - T0) // MIN)
        k1 = min(len(self.close) - 1, (max(req["endTime"], forming) - T0) // MIN)
        return [{"t": T0 + k * MIN, "h": str(self.high[k]), "l": str(self.low[k]),
                 "c": str(self.close[k])} for k in range(k0, k1 + 1)]


def synthetic(n: int, seed: int):
    """A 1m random walk with 60 crash wicks of 2.6-6%, some recovering and some not."""
    rng = np.random.default_rng(seed)
    r = rng.normal(0.0, 0.0015, n)
    crash = rng.choice(np.arange(5, n), size=60, replace=False)
    depth = rng.uniform(0.026, 0.06, crash.size)
    r[crash] += np.log1p(-depth * rng.uniform(0.0, 1.0, crash.size))
    close = 100.0 * np.exp(np.cumsum(r))
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.0008, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.0008, n)))
    low[crash] = np.minimum(low[crash], open_[crash] * (1 - depth))
    return high, low, close


def backtest(low, high, close, depth, target, hold):
    """``probes/f8_param_grid.py::simulate`` under live conventions, at Hyperliquid fees on each
    leg's own notional: (fill bar, exit reason, exit price, net) per round trip."""
    n = len(close)
    out, free = [], 1
    for i in np.flatnonzero(low[1:] <= close[:-1] * (1.0 - depth)) + 1:
        if i < free:
            continue
        bid = close[i - 1] * (1.0 - depth)
        end = min(i + hold, n - 1)
        hit = np.flatnonzero(high[i + 1:end + 1] >= bid * (1.0 + target))
        if hit.size:
            exit_bar, why, px, fee = i + 1 + int(hit[0]), "tp", bid * (1.0 + target), MAKER
        else:
            exit_bar, why, px, fee = end, "time", close[end], TAKER
        net = px / bid - 1.0 - MAKER - px / bid * fee
        out.append((int(i), why, px, net))
        free = exit_bar + 1
    return out


@pytest.mark.parametrize("rule", [F8, Rule(0.015, 0.020, 240 * MIN)])
def test_a_paper_bot_reproduces_the_backtest_trade_for_trade(monkeypatch, rule):
    monkeypatch.setattr(ladder, "REPEG_SHALLOW", 0.0)  # the backtest re-pegs every minute
    monkeypatch.setattr(ladder, "REPEG_DEEP", 0.0)
    monkeypatch.setattr(paper, "MIDS_TTL_S", 0.0)
    n, hold = 4000, rule.hold_ms // MIN
    high, low, close = synthetic(n, seed=7)
    x = FakeX(high, low, close)
    store = MemStore(RUN)
    bot = LadderBot(PaperVenue(HLMarket(x), [], clock=lambda: x.now), store, 12.0, ("BTC",), rule)
    for k in range(1, n):
        for off in (2_500, 20_000, 40_000):  # the first cycle after the prior candle settles
            x.now = T0 + k * MIN + off
            bot.cycle(x.now)

    # Round trips the replay can see end by its last closed candle, bar n-2.
    want = [e for e in backtest(low, high, close, rule.drop, rule.target, hold)
            if e[0] + hold <= n - 2]
    got = sorted(store.rows.values(), key=lambda t: t.fill_ms)
    got = [t for t in got if (t.fill_ms - CLOSE_GRACE_MS - T0) // MIN - 1 + hold <= n - 2]
    assert len(want) >= 10 and {e[1] for e in want} == {"tp", "time"}
    assert [((t.fill_ms - CLOSE_GRACE_MS - T0) // MIN - 1, t.exit_reason) for t in got] \
        == [(i, why) for i, why, _, _ in want]
    for t, (_, _, px, net) in zip(got, want, strict=True):
        assert t.exit_px == pytest.approx(px, rel=1e-12)
        got_net = (t.exit_px - t.fill_px) / t.fill_px - (t.entry_fee + t.exit_fee) / (
            t.fill_px * t.sz)
        assert got_net == pytest.approx(net, abs=1e-12)


def flat_market(n=200, coins=("BTC",)):
    x = FakeX(np.full(n, 100.5), np.full(n, 99.5), np.full(n, 100.0), coins)
    return x, HLMarket(x)


def open_trade(fill_bar: int, **kw) -> Trade:
    """A paper round trip whose bid filled in candle ``fill_bar``, take-profit resting at 101."""
    return Trade(bot="test", venue=PAPER, coin="BTC", entry_oid=1, anchor_close=102.0, sz=0.1,
                 fill_px=99.5, fill_ms=T0 + (fill_bar + 1) * MIN + CLOSE_GRACE_MS,
                 entry_fee=0.0015, leverage="paper", liq_px=None, tp_px=101.0, tp_oid=2, **kw)


def test_a_restart_settles_the_candles_missed_while_down():
    x, market = flat_market()
    x.high[15] = 101.2  # the take-profit was reached while the process was down
    x.now = T0 + 20 * MIN + 5_000
    store = MemStore(RUN)
    trade = open_trade(fill_bar=10)
    store.save_trade(trade)
    venue = PaperVenue(market, [trade], clock=lambda: x.now)
    bot = LadderBot(venue, store, 12.0, ("BTC",))
    bot.cycle(x.now)
    [row] = store.rows.values()
    assert (row.exit_reason, row.exit_px) == ("tp", pytest.approx(101.0))
    assert row.exit_ms == T0 + 16 * MIN + CLOSE_GRACE_MS
    assert row.exit_fee == pytest.approx(101.0 * 0.1 * MAKER)


def test_a_restart_never_fills_a_take_profit_on_its_own_fill_candle():
    x, market = flat_market()
    x.high[10] = 105.0  # the fill candle's high: the backtest only checks LATER candles
    x.now = T0 + 20 * MIN + 5_000
    venue = PaperVenue(market, [open_trade(fill_bar=10)], clock=lambda: x.now)
    assert venue.positions()["BTC"].szi == 0.1


def test_a_round_trip_whose_close_went_out_before_a_restart_is_not_revived():
    x, market = flat_market()
    x.now = T0 + 90 * MIN
    store = MemStore(RUN)
    trade = open_trade(fill_bar=10, time_oid=3)
    store.save_trade(trade)
    bot = LadderBot(PaperVenue(market, [trade], clock=lambda: x.now), store, 12.0, ("BTC",))
    bot.cycle(x.now)
    [row] = store.rows.values()
    assert (row.exit_reason, row.exit_dir, row.exit_px) == ("other", "no fill", None)


@pytest.mark.parametrize("then, rests", [(99.0, True), (100.0, True), (100.01, False),
                                         (None, False)])
def test_the_trend_gate_bids_only_while_the_coin_is_up(then, rests):
    x, market = flat_market()
    minute = T0 + 50 * MIN
    asked = []
    market.close_before = lambda coin, ts: asked.append(ts) or then
    x.now = minute + 5_000
    venue = PaperVenue(market, [], clock=lambda: x.now)
    rule = Rule(F8.drop, F8.target, F8.hold_ms, trend_ms=30 * swarm.DAY)
    LadderBot(venue, MemStore(RUN), 12.0, ("BTC",), rule).cycle(x.now)
    assert bool(venue.open_orders()) is rests
    assert asked == [minute - 30 * swarm.DAY]  # vs the prior close (100.0) of this minute's rung


def test_the_trend_gate_reads_the_hourly_close_once_an_hour():
    x, market = flat_market()
    hour = (T0 // paper.HOUR + 1) * paper.HOUR
    x.hour_close[("BTC", hour - paper.HOUR)] = 97.0
    for ts in (hour, hour + 30 * MIN, hour + paper.HOUR - 1):
        assert market.close_before("BTC", ts) == 97.0
    assert len([r for r in x.requests if r["req"]["interval"] == "1h"]) == 1


def test_paper_bots_share_one_candle_read_per_coin_per_minute():
    x, market = flat_market(coins=("BTC", "ETH"))
    bots = [LadderBot(PaperVenue(market, [], clock=lambda: x.now), MemStore(RUN), 12.0,
                      ("BTC", "ETH"), rule) for rule in (F8, Rule(0.015, 0.02, 240 * MIN))]
    for k in range(1, 6):
        for off in (2_500, 5_500, 30_000):
            x.now = T0 + k * MIN + off
            for b in bots:
                b.cycle(x.now)
    reads = [r["req"]["coin"] for r in x.requests if r["type"] == "candleSnapshot"]
    assert reads.count("BTC") == reads.count("ETH") == 5
    assert all(len(b.hl.open_orders()) == 2 for b in bots)


def test_the_candle_still_forming_is_never_settled():
    x, market = flat_market()
    x.low[10] = 90.0  # candle 10 crashes; at 10:30 it is still forming
    x.now = T0 + 10 * MIN + 3_000
    venue = PaperVenue(market, [], clock=lambda: x.now)
    venue.place("BTC", "buy", 0.1, 97.5, post_only=True)
    x.now = T0 + 10 * MIN + 30_000
    assert venue.positions() == {}
    x.now = T0 + 11 * MIN + 1_000  # closed, but inside the grace period
    assert venue.positions() == {}
    x.now = T0 + 11 * MIN + CLOSE_GRACE_MS
    assert venue.positions()["BTC"].entry_px == 97.5


def test_each_bot_has_its_own_id_and_paper_never_shares_the_live_row():
    ids = {bot_on(PAPER, b.name) for b in swarm.BOTS}
    assert len(ids) == len(swarm.BOTS)
    assert bot_on("hyperliquid") not in ids
    assert all(b.bar for b in swarm.BOTS)
