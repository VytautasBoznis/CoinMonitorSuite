"""Public Hyperliquid reads for the dashboard: market data, and the account's positions and orders
by master address. No key, so nothing here can trade.

The venue meters REST per IP (1200 weight/min) and the bot shares that IP, at ~440/min. Every
read is cached server-side, so any number of open tabs costs a fixed budget: about 200/min with
the TTLs below. Live prices reach the browser over the public websocket instead (``WS``).
"""

from __future__ import annotations

import json
import threading
import time

import httpx

INFO = {True: "https://api.hyperliquid-testnet.xyz/info", False: "https://api.hyperliquid.xyz/info"}
WS = {True: "wss://api.hyperliquid-testnet.xyz/ws", False: "wss://api.hyperliquid.xyz/ws"}
INTERVAL_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}


class Market:
    def __init__(self, testnet: bool, client: httpx.Client | None = None) -> None:
        self.url = INFO[testnet]
        self._client = client or httpx.Client(timeout=10.0)
        self._cache: dict[str, tuple[float, object]] = {}
        self._lock = threading.Lock()

    def _info(self, body: dict, ttl_s: float):
        key = json.dumps(body, sort_keys=True)
        with self._lock:
            hit = self._cache.get(key)
            if hit and hit[0] > time.monotonic():
                return hit[1]
        resp = self._client.post(self.url, json=body)
        resp.raise_for_status()
        data = resp.json()
        now = time.monotonic()
        with self._lock:
            self._cache = {k: v for k, v in self._cache.items() if v[0] > now}
            self._cache[key] = (now + ttl_s, data)
        return data

    def contexts(self, coins: tuple[str, ...]) -> dict[str, dict]:
        """Per coin: mark, mid, previous-day price, hourly funding, open interest, day volume."""
        meta, ctxs = self._info({"type": "metaAndAssetCtxs"}, ttl_s=30)
        out = {}
        for asset, ctx in zip(meta["universe"], ctxs, strict=True):
            if asset["name"] in coins:
                mark = float(ctx["markPx"])
                out[asset["name"]] = {
                    "mark": mark,
                    "mid": float(ctx["midPx"]) if ctx.get("midPx") else mark,
                    "prev_day": float(ctx["prevDayPx"]),
                    "funding": float(ctx["funding"]),
                    "open_interest_usd": float(ctx["openInterest"]) * mark,
                    "day_volume_usd": float(ctx["dayNtlVlm"]),
                }
        return out

    def candles(self, coin: str, interval: str, limit: int, now_ms: int) -> list[dict]:
        """The last ``limit`` candles (``time`` = open, ms). The websocket keeps them live."""
        step = INTERVAL_MS[interval]
        end = now_ms // 10_000 * 10_000  # rounded, so requests within 10s share the cache
        req = {"coin": coin, "interval": interval,
               "startTime": (end - limit * step) // step * step, "endTime": end}
        rows = self._info({"type": "candleSnapshot", "req": req}, ttl_s=10)
        return [
            {"time": int(c["t"]), "open": float(c["o"]), "high": float(c["h"]),
             "low": float(c["l"]), "close": float(c["c"]), "volume": float(c["v"])}
            for c in rows
        ]

    def account(self, address: str) -> dict:
        """Equity, margin, positions and resting orders of ``address`` as the venue reports them."""
        state = self._info({"type": "clearinghouseState", "user": address}, ttl_s=3)
        orders = self._info({"type": "frontendOpenOrders", "user": address}, ttl_s=10)
        summary = state["marginSummary"]
        positions = []
        for ap in state["assetPositions"]:
            p = ap["position"]
            if float(p["szi"]) == 0:
                continue
            positions.append({
                "coin": p["coin"], "szi": float(p["szi"]), "entry_px": float(p["entryPx"]),
                "value": float(p["positionValue"]), "upnl": float(p["unrealizedPnl"]),
                "liq_px": float(p["liquidationPx"]) if p.get("liquidationPx") else None,
                "leverage": f"{p['leverage']['type']} {p['leverage']['value']}",
                "margin": float(p["marginUsed"]),
            })
        return {
            "equity": float(summary["accountValue"]),
            "margin_used": float(summary["totalMarginUsed"]),
            "notional": float(summary["totalNtlPos"]),
            "withdrawable": float(state["withdrawable"]),
            "positions": positions,
            "orders": [
                {"coin": o["coin"], "oid": int(o["oid"]), "side": o["side"],
                 "px": float(o["limitPx"]), "sz": float(o["sz"]),
                 "reduce_only": bool(o["reduceOnly"]), "time": int(o["timestamp"])}
                for o in orders
            ],
        }
