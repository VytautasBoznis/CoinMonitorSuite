"""Hyperliquid perp client for the live bot.

ccxt does the signing and transport. Reads go to the raw ``info`` endpoint, so every field is
Hyperliquid's own. The agent key (an approved API wallet) signs orders; ``address`` is the master
wallet that owns the funds and the only signer that can withdraw.
"""

from __future__ import annotations

from dataclasses import dataclass

import ccxt

SLIPPAGE = "0.05"  # IOC closes: limit 5% through the mid (Hyperliquid has no true market order)


@dataclass(frozen=True)
class Position:
    coin: str
    szi: float  # signed size, > 0 = long
    entry_px: float
    leverage: str  # as set on the venue, e.g. "isolated 5"
    liq_px: float | None


@dataclass(frozen=True)
class Order:
    coin: str
    oid: int
    side: str  # "B" buy, "A" sell
    px: float
    sz: float
    reduce_only: bool


@dataclass(frozen=True)
class Fill:
    coin: str
    oid: int
    side: str
    px: float
    sz: float
    time: int
    fee: float
    crossed: bool  # True = taker
    dir: str  # venue's direction text, e.g. "Open Long", "Close Long"


def venue_name(testnet: bool) -> str:
    """The ``venue`` the ledger files this account's trades under."""
    return "hyperliquid-testnet" if testnet else "hyperliquid"


class Hyperliquid:
    def __init__(self, address: str, agent_key: str, testnet: bool = True) -> None:
        self.address = address
        self.venue = venue_name(testnet)
        self._x = ccxt.hyperliquid(
            {"walletAddress": address, "privateKey": agent_key, "enableRateLimit": True}
        )
        if testnet:
            self._x.set_sandbox_mode(True)
        self._x.load_markets()

    def _info(self, body: dict):
        return self._x.publicPostInfo(body)

    @staticmethod
    def _symbol(coin: str) -> str:
        return f"{coin}/USDC:USDC"

    # --- reads ---

    def positions(self) -> dict[str, Position]:
        state = self._info({"type": "clearinghouseState", "user": self.address})
        out: dict[str, Position] = {}
        for ap in state["assetPositions"]:
            p = ap["position"]
            if float(p["szi"]) == 0:
                continue
            lev = p["leverage"]
            liq = p.get("liquidationPx")
            out[p["coin"]] = Position(
                coin=p["coin"],
                szi=float(p["szi"]),
                entry_px=float(p["entryPx"]),
                leverage=f"{lev['type']} {lev['value']}",
                liq_px=float(liq) if liq is not None else None,
            )
        return out

    def open_orders(self) -> list[Order]:
        rows = self._info({"type": "frontendOpenOrders", "user": self.address})
        return [
            Order(r["coin"], int(r["oid"]), r["side"], float(r["limitPx"]), float(r["sz"]),
                  bool(r["reduceOnly"]))
            for r in rows
        ]

    def fills(self) -> list[Fill]:
        """The account's most recent fills (the venue serves up to 2000)."""
        rows = self._info({"type": "userFills", "user": self.address})
        return [
            Fill(r["coin"], int(r["oid"]), r["side"], float(r["px"]), float(r["sz"]),
                 int(r["time"]), float(r["fee"]), bool(r["crossed"]), r["dir"])
            for r in rows
        ]

    def mids(self) -> dict[str, float]:
        return {k: float(v) for k, v in self._info({"type": "allMids"}).items()}

    def last_close(self, coin: str, minute_ms: int) -> float | None:
        """Close of the newest 1m candle that opened before ``minute_ms`` (the prior close)."""
        req = {"coin": coin, "interval": "1m", "startTime": minute_ms - 600_000,
               "endTime": minute_ms - 1}
        candles = [c for c in self._info({"type": "candleSnapshot", "req": req})
                   if int(c["t"]) < minute_ms]
        return float(max(candles, key=lambda c: int(c["t"]))["c"]) if candles else None

    def leverage(self, coin: str) -> str:
        """The coin's leverage setting on the venue, e.g. ``"isolated 5"``."""
        data = self._info({"type": "activeAssetData", "user": self.address, "coin": coin})
        lev = data["leverage"]
        return f"{lev['type']} {lev['value']}"

    def rate_limit(self) -> dict:
        """Address action budget: ``nRequestsUsed`` of ``nRequestsCap`` (cap grows with volume)."""
        return self._info({"type": "userRateLimit", "user": self.address})

    def listed(self, coins: tuple[str, ...]) -> tuple[str, ...]:
        """The subset of ``coins`` this venue lists as perps (testnet lists fewer than mainnet)."""
        return tuple(c for c in coins if self._symbol(c) in self._x.markets)

    def round_px(self, coin: str, px: float) -> float:
        return float(self._x.price_to_precision(self._symbol(coin), px))

    # --- writes ---

    def place(self, coin: str, side: str, sz: float, px: float, *, post_only: bool = False,
              reduce_only: bool = False) -> int:
        """Limit order (``side`` "buy"/"sell"); ``post_only`` = ALO, else GTC. Returns the oid."""
        params = {"postOnly": post_only, "reduceOnly": reduce_only}
        o = self._x.create_order(self._symbol(coin), "limit", side, sz, px, params)
        return int(o["id"])

    def modify(self, oid: int, coin: str, sz: float, px: float) -> None:
        """Re-price a resting post-only bid."""
        self._x.edit_order(str(oid), self._symbol(coin), "limit", "buy", sz, px, {"postOnly": True})

    def cancel(self, coin: str, oid: int) -> None:
        self._x.cancel_order(str(oid), self._symbol(coin))

    def close(self, coin: str, szi: float, mid: float) -> int:
        """Reduce-only IOC that flattens a position of signed size ``szi``. Returns the oid."""
        side = "sell" if szi > 0 else "buy"
        params = {"reduceOnly": True, "slippage": SLIPPAGE}
        o = self._x.create_order(self._symbol(coin), "market", side, abs(szi), mid, params)
        return int(o["id"])
