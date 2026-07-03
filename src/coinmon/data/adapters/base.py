from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd

from coinmon.data.models import CANDLE_COLUMNS

# Bar duration in epoch-ms per timeframe. Used for paging cursors and gap validation.
_TIMEFRAME_MS: dict[str, int] = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
    "1w": 604_800_000,
}


def timeframe_to_ms(timeframe: str) -> int:
    """Bar duration in milliseconds for a timeframe string (e.g. ``"1h"`` -> 3_600_000)."""
    try:
        return _TIMEFRAME_MS[timeframe]
    except KeyError:
        raise ValueError(
            f"Unsupported timeframe {timeframe!r}; known: {sorted(_TIMEFRAME_MS)}"
        ) from None


def validate_continuity(df: pd.DataFrame, timeframe: str) -> None:
    """Raise if a sorted candle frame has gaps or duplicate timestamps.

    No-lookahead and backtest honesty both depend on contiguous bars; bad/incomplete
    data is rejected loudly rather than silently stored.
    """
    if len(df) < 2:
        return
    step = timeframe_to_ms(timeframe)
    diffs = df["open_time"].diff().iloc[1:]
    bad = diffs[diffs != step]
    if not bad.empty:
        raise ValueError(
            f"Non-contiguous {timeframe} candles: expected step {step}ms, "
            f"found steps {sorted(set(bad.astype(int)))[:5]} near "
            f"open_time {int(df['open_time'].iloc[int(bad.index[0]) - 1])}"
        )


@dataclass(frozen=True, slots=True)
class RawBatch:
    """One page of candle rows exactly as the exchange returned them, plus provenance.

    ``rows`` is the untouched payload (ccxt returns ``list[[ts, o, h, l, c, v], ...]``)
    and is persisted verbatim for archival — never normalize before storing it.
    ``fetched_at`` (epoch ms, UTC) doubles as the "now" used to drop an in-progress bar.
    """

    exchange: str
    symbol: str
    timeframe: str
    rows: list
    fetched_at: int


class ExchangeAdapter(ABC):
    """Exchange-agnostic candle contract — fetch raw, convert to the common model.

    This is the SAME seam a live adapter implements, so the backtest engine, scraper,
    and a future live feed are interchangeable behind it. Adding a venue = one new
    subclass; nothing downstream changes. See ``adapters/README.md`` to author one.
    """

    #: Short exchange id, e.g. ``"bybit"``. Stored alongside every candle.
    name: str

    @abstractmethod
    def market_symbol(self, symbol: str) -> str:
        """Map a common ``BASE/QUOTE`` symbol to this exchange's native symbol."""
        raise NotImplementedError

    @abstractmethod
    def fetch_raw(
        self,
        symbol: str,
        timeframe: str,
        since: int | None = None,
        until: int | None = None,
    ) -> RawBatch:
        """Fetch ONE page of raw candles (oldest-first), starting at ``since`` (epoch ms)."""
        raise NotImplementedError

    @abstractmethod
    def to_candles(self, raw: RawBatch) -> pd.DataFrame:
        """Normalize a raw page to the common ``CANDLE_COLUMNS`` frame (closed bars only)."""
        raise NotImplementedError

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: int | None = None,
        until: int | None = None,
    ) -> pd.DataFrame:
        """Page over ``fetch_raw`` to return a gap-validated frame for ``[since, until]``.

        Convenience for single-call consumers (e.g. the backtester). The scraper drives
        ``fetch_raw``/``to_candles`` directly so it can archive each raw page.
        """
        step = timeframe_to_ms(timeframe)
        frames: list[pd.DataFrame] = []
        cursor = since
        while True:
            raw = self.fetch_raw(symbol, timeframe, since=cursor, until=until)
            if not raw.rows:
                break
            df = self.to_candles(raw)
            if df.empty:
                break
            frames.append(df)
            cursor = int(df["open_time"].iloc[-1]) + step
            if until is not None and cursor > until:
                break
        if not frames:
            return pd.DataFrame(columns=list(CANDLE_COLUMNS))
        out = (
            pd.concat(frames, ignore_index=True)
            .drop_duplicates("open_time")
            .sort_values("open_time")
            .reset_index(drop=True)
        )
        validate_continuity(out, timeframe)
        return out
