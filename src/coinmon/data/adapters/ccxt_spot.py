from __future__ import annotations

import pandas as pd

from coinmon.data.adapters.base import (
    ExchangeAdapter,
    RawBatch,
    timeframe_to_ms,
    validate_continuity,
)
from coinmon.data.models import CANDLE_COLUMNS

# ccxt serves at most 1000 klines per request on the venues we use.
_PAGE_LIMIT = 1000


class CCXTSpotAdapter(ExchangeAdapter):
    """Generic ccxt spot candle fetcher — the shared body every ccxt venue reuses.

    A concrete venue is one small subclass that sets ``name``, ``_exchange_id`` (the ccxt id),
    and optional ``_client_options``. The fetch/normalize logic is identical across venues
    because ccxt already returns the unified ``BASE/QUOTE`` symbol and the same OHLCV shape.
    """

    #: ccxt exchange id used to construct the client, e.g. ``"bybit"`` / ``"binance"``.
    _exchange_id: str
    #: extra ccxt constructor options merged over ``enableRateLimit`` (e.g. defaultType).
    _client_options: dict = {}
    #: reject non-contiguous pages (the live scraper's clean-data guarantee). Set False only
    #: for a history backfill of a venue with genuine downtime gaps (stores real bars as-is,
    #: never fabricated) — see the ``backfill --allow-gaps`` CLI.
    require_contiguous: bool = True

    def __init__(self) -> None:
        self._exchange = None  # lazy ccxt client (avoids import/network cost at construction)

    def _client(self):
        if self._exchange is None:
            import ccxt

            self._exchange = getattr(ccxt, self._exchange_id)(
                {"enableRateLimit": True} | self._client_options
            )
        return self._exchange

    def market_symbol(self, symbol: str) -> str:
        # ccxt already uses the unified BASE/QUOTE form, so this is identity. It stays the
        # single place a venue with odd symbol naming would remap.
        return symbol

    def fetch_raw(
        self,
        symbol: str,
        timeframe: str,
        since: int | None = None,
        until: int | None = None,
    ) -> RawBatch:
        client = self._client()
        rows = client.fetch_ohlcv(
            self.market_symbol(symbol), timeframe, since=since, limit=_PAGE_LIMIT
        )
        if until is not None:
            rows = [r for r in rows if r[0] <= until]
        return RawBatch(
            exchange=self.name,
            symbol=symbol,
            timeframe=timeframe,
            rows=rows,
            fetched_at=client.milliseconds(),
        )

    def to_candles(self, raw: RawBatch) -> pd.DataFrame:
        df = pd.DataFrame(raw.rows, columns=list(CANDLE_COLUMNS))
        if df.empty:
            return df.astype({c: "float64" for c in CANDLE_COLUMNS[1:]} | {"open_time": "int64"})

        df["open_time"] = df["open_time"].astype("int64")
        for col in CANDLE_COLUMNS[1:]:
            df[col] = df[col].astype("float64")

        # Drop the in-progress (unclosed) trailing bar: keep bars whose close time <= now.
        step = timeframe_to_ms(raw.timeframe)
        df = df[df["open_time"] + step <= raw.fetched_at]

        df = df.drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)
        if self.require_contiguous:
            validate_continuity(df, raw.timeframe)
        return df
