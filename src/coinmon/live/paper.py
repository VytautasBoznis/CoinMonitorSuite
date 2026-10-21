"""Paper trading for the swarm: a simulated Hyperliquid account that fills like the F8 backtests.

Swarm bots trade on paper by default ([[swarm-and-cross-market-ideas]]). ``PaperVenue`` offers
``LadderBot`` the same calls as the real venue, so a paper bot runs the live bot's exact code path.
Its orders fill against Hyperliquid MAINNET 1m candles the way ``probes/f8_param_grid.py`` fills
them:
  * a resting bid fills in full at its price when a closed candle's low touches it;
  * a take-profit fills at its price, maker, on a LATER candle whose high reaches it;
  * a market close fills at the mid it is given, taker (the backtest: the close of minute HOLD).
Candles are settled before the bot reads the account, once closed plus CLOSE_GRACE_MS, and their
fills are stamped then: the time-stop thus comes after the candle at minute HOLD has been checked
for the take-profit, as in the backtest.

Paper leaves out what the live twin measures: queue position (a touch is not a fill), post-only
rejects, partial fills, a take-profit placed through the market, the spread on closes, funding.
It is the backtest run forward, an upper bound on what the venue would pay.

State is the ledger. On restart, open rows come back as positions with their take-profits, and
the candles missed while down are settled against them (the venue serves the last 5000). A
time-stop that fell inside the downtime exits late, at the mid of the first cycle back.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass

import ccxt

from coinmon.live.control import Trade, now_ms
from coinmon.live.hyperliquid import Fill, Order, Position

PAPER = "hyperliquid-paper"  # the ledger's venue for paper rows
LEVERAGE = "paper"
MAKER, TAKER = 0.00015, 0.00045  # Hyperliquid tier-0 perps ([[hl-venue-limits-multibot]])
MIN = 60_000
HOUR = 60 * MIN
CLOSE_GRACE_MS = 2_000  # a candle's last trades are in this long after its minute ends
KEEP_MS = 6 * HOUR  # cached candles: the longest hold (240m) plus slack
MIDS_TTL_S = 2.0


@dataclass(frozen=True)
class Bar:
    t: int  # open, ms
    high: float
    low: float
    close: float


class HLMarket:
    """Public Hyperliquid mainnet reads, shared by every paper bot in the process: one candle
    request per coin per minute however many bots read it (~120 of the IP's 1200 weight a minute
    for six coins; mids are read only at time-stops). No key, so nothing here can trade."""

    def __init__(self, x: ccxt.hyperliquid | None = None) -> None:
        self._x = x or ccxt.hyperliquid({"enableRateLimit": True})
        self._x.load_markets()
        self._bars: dict[str, dict[int, Bar]] = {}
        self._span: dict[str, tuple[float, float]] = {}  # coin -> first, last minute fetched
        self._hour: dict[str, tuple[int, float | None]] = {}  # coin -> newest 1h close read
        self._mids: tuple[float, dict[str, float]] = (-math.inf, {})

    def _candles(self, coin: str, interval: str, start_ms: int, end_ms: int) -> list[dict]:
        req = {"coin": coin, "interval": interval, "startTime": start_ms, "endTime": end_ms}
        return self._x.publicPostInfo({"type": "candleSnapshot", "req": req})

    def mids(self) -> dict[str, float]:
        at, mids = self._mids
        if time.monotonic() - at >= MIDS_TTL_S:
            mids = {k: float(v) for k, v in self._x.publicPostInfo({"type": "allMids"}).items()}
            self._mids = (time.monotonic(), mids)
        return mids

    def bars(self, coin: str, start_ms: int, now_ms: int) -> list[Bar]:
        """Closed 1m candles that opened at or after ``start_ms``, oldest first."""
        last = (now_ms - CLOSE_GRACE_MS) // MIN * MIN - MIN
        have = self._bars.setdefault(coin, {})
        cut = now_ms - KEEP_MS
        for t in [t for t in have if t < cut]:
            del have[t]
        first, through = self._span.get(coin, (math.inf, -math.inf))
        first = max(first, cut)
        if start_ms <= last and (start_ms < first or last > through):
            begin = start_ms if start_ms < first else int(through) + MIN
            for c in self._candles(coin, "1m", begin, last + MIN - 1):
                if int(c["t"]) <= last:
                    have[int(c["t"])] = Bar(int(c["t"]), float(c["h"]), float(c["l"]),
                                            float(c["c"]))
            first, through = min(first, start_ms), last
        self._span[coin] = (first, through)
        return [have[t] for t in sorted(have) if start_ms <= t <= last]

    def close_before(self, coin: str, ts_ms: int) -> float | None:
        """Close of the newest 1h candle that closed at or before ``ts_ms``; one read per coin
        per hour."""
        t = ts_ms // HOUR * HOUR - HOUR
        if self._hour.get(coin, (None,))[0] != t:
            rows = [c for c in self._candles(coin, "1h", t, t + HOUR - 1) if int(c["t"]) == t]
            self._hour[coin] = (t, float(rows[0]["c"]) if rows else None)
        return self._hour[coin][1]

    def round_px(self, coin: str, px: float) -> float:
        return float(self._x.price_to_precision(f"{coin}/USDC:USDC", px))

    def listed(self, coins: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(c for c in coins if f"{c}/USDC:USDC" in self._x.markets)


class PaperVenue:
    """One paper bot's simulated account (see the module docstring)."""

    address = "paper"

    def __init__(self, market: HLMarket, open_trades: list[Trade],
                 clock: Callable[[], int] = now_ms, venue: str = PAPER) -> None:
        self.venue = venue
        self.market = market
        self._clock = clock
        self._orders: dict[int, Order] = {}
        self._rests: dict[int, int] = {}  # oid -> open of the first candle that can fill it
        self._pos: dict[str, Position] = {}
        self._fills: list[Fill] = []  # newest first, as the venue serves them
        self._settled: dict[str, int] = {}  # coin -> open of the newest candle settled
        self._last_oid = clock() * 1000  # unique across restarts: the ledger is keyed by oid
        for t in open_trades:
            if t.time_oid is not None:
                continue  # its market close went out before the restart: flat, fill lost
            self._pos[t.coin] = Position(t.coin, t.sz, t.fill_px, LEVERAGE, None)
            if t.tp_oid is not None:
                self._orders[t.tp_oid] = Order(t.coin, t.tp_oid, "A", t.tp_px, t.sz, True)
                self._rests[t.tp_oid] = t.fill_ms // MIN * MIN  # the candle after the fill's

    # --- the simulation ---

    def _oid(self) -> int:
        self._last_oid += 1
        return self._last_oid

    def _settle(self) -> None:
        """Fill resting orders against every candle closed since the last settle."""
        now = self._clock()
        for coin in {o.coin for o in self._orders.values()}:
            first = min(self._rests[o.oid] for o in self._orders.values() if o.coin == coin)
            start = max(first, self._settled.get(coin, first - MIN) + MIN)
            for bar in self.market.bars(coin, start, now):
                known = bar.t + MIN + CLOSE_GRACE_MS
                for o in [o for o in self._orders.values()
                          if o.coin == coin and self._rests[o.oid] <= bar.t]:
                    if o.side == "B" and not o.reduce_only and bar.low <= o.px:
                        self._fill(coin, o.oid, "B", o.px, o.sz, known, crossed=False)
                    elif (o.side == "A" and o.reduce_only and coin in self._pos
                          and bar.high >= o.px):
                        self._fill(coin, o.oid, "A", o.px, o.sz, known, crossed=False)
                self._settled[coin] = bar.t

    def _fill(self, coin: str, oid: int, side: str, px: float, sz: float, ts: int,
              crossed: bool) -> None:
        self._orders.pop(oid, None)
        self._rests.pop(oid, None)
        fee = px * sz * (TAKER if crossed else MAKER)
        self._fills.insert(0, Fill(coin, oid, side, px, sz, ts, fee, crossed,
                                   "Open Long" if side == "B" else "Close Long"))
        del self._fills[2000:]
        p = self._pos.get(coin)
        szi = (p.szi if p else 0.0) + (sz if side == "B" else -sz)
        if abs(szi) < 1e-12:
            self._pos.pop(coin, None)
        else:
            self._pos[coin] = Position(coin, szi, p.entry_px if p else px, LEVERAGE, None)

    # --- the venue's reads ---

    def positions(self) -> dict[str, Position]:
        self._settle()
        return dict(self._pos)

    def open_orders(self) -> list[Order]:
        self._settle()
        return list(self._orders.values())

    def fills(self) -> list[Fill]:
        return list(self._fills)

    def mids(self) -> dict[str, float]:
        return self.market.mids()

    def last_close(self, coin: str, minute_ms: int) -> float | None:
        """Close of the newest candle that opened before ``minute_ms`` (within 10 minutes), once
        the one just before it has settled."""
        now = self._clock()
        if now < minute_ms + CLOSE_GRACE_MS:
            return None
        bars = [b for b in self.market.bars(coin, minute_ms - 10 * MIN, now) if b.t < minute_ms]
        return bars[-1].close if bars else None

    def close_before(self, coin: str, ts_ms: int) -> float | None:
        return self.market.close_before(coin, ts_ms)

    def round_px(self, coin: str, px: float) -> float:
        return self.market.round_px(coin, px)

    def write_wait_s(self) -> float:
        return 0.0  # paper spends no venue actions

    # --- the venue's writes ---

    def place(self, coin: str, side: str, sz: float, px: float, *, post_only: bool = False,
              reduce_only: bool = False) -> int:
        oid = self._oid()
        self._orders[oid] = Order(coin, oid, "B" if side == "buy" else "A", px, sz, reduce_only)
        self._rests[oid] = self._clock() // MIN * MIN
        return oid

    def modify(self, oid: int, coin: str, sz: float, px: float) -> None:
        """Re-price a resting bid; like the venue, it comes back under a new oid."""
        self.cancel(coin, oid)
        self.place(coin, "buy", sz, px, post_only=True)

    def cancel(self, coin: str, oid: int) -> None:
        self._orders.pop(oid, None)
        self._rests.pop(oid, None)

    def close(self, coin: str, szi: float, mid: float) -> int:
        """Market close of signed size ``szi``: fills now, at ``mid``, taker."""
        oid = self._oid()
        self._fill(coin, oid, "A" if szi > 0 else "B", mid, abs(szi), self._clock(), crossed=True)
        return oid
