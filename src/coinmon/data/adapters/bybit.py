from __future__ import annotations

from coinmon.data.adapters.ccxt_spot import CCXTSpotAdapter


class BybitAdapter(CCXTSpotAdapter):
    """Bybit spot candle fetcher via ccxt — the worked reference for new adapters. Adds
    perp funding-rate history (Bybit-specific), which the shared spot base does not cover."""

    name = "bybit"
    _exchange_id = "bybit"
    _client_options = {"options": {"defaultType": "spot"}}

    def __init__(self) -> None:
        super().__init__()
        self._perp = None  # lazy ccxt client for the linear (USDC-settled) perp endpoints

    def _perp_client(self):
        if self._perp is None:
            import ccxt

            self._perp = ccxt.bybit(
                {"enableRateLimit": True, "options": {"defaultType": "linear"}}
            )
        return self._perp

    def fetch_funding_history(
        self, symbol: str, since: int | None = None
    ) -> list[tuple[int, float]]:
        """Funding-rate settlements for a perp (e.g. ``"BTC/USDC:USDC"``), oldest-first.

        Bybit rejects a far ``since`` — its endpoint serves the most recent window and pages
        backward — so we page via ``until`` (the H6-probe-proven approach), stopping once we
        reach ``since`` (incremental poll) or run out of history (full backfill). Returns
        ``(funding_time_ms, rate)`` tuples; the caller filters/upserts by ``funding_time``.
        """
        client = self._perp_client()
        rows: list[dict] = []
        until: int | None = None
        while True:
            params = {"until": until} if until else {}
            page = client.fetch_funding_rate_history(symbol, limit=200, params=params)
            if not page:
                break
            rows = page + rows
            oldest = page[0]["timestamp"]
            if since is not None and oldest <= since:
                break
            if until is not None and oldest >= until:
                break  # no older data served — avoid an infinite loop
            until = oldest - 1
        seen: dict[int, float] = {}
        for r in rows:
            seen[int(r["timestamp"])] = float(r["fundingRate"])
        return sorted(seen.items())
