from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from coinmon.data.candles import load_candles
from coinmon.data.models import Candle


def frame_to_candles(frame: pd.DataFrame) -> list[Candle]:
    """Materialize an OHLCV frame into ``Candle`` objects (oldest-first), the unit the engine
    core consumes. The same field coercion the engine applies row-by-row."""
    return [
        Candle(
            open_time=int(row.open_time),
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            volume=float(row.volume),
        )
        for row in frame.itertuples(index=False)
    ]


class LiveFeed:
    """Incremental reader over the scraper's growing DB. Each ``poll`` re-resolves the pair
    (USDC-direct, or a synthetic ratio from its two USDC legs via ``load_candles``) and returns
    only the bars newer than the last one already seen, so a strategy is driven exactly once per
    closed bar across many polls. The scraper only ever stores CLOSED bars, so every bar returned
    is final — there is no in-progress bar to guard against."""

    def __init__(self, read: Callable[[str], pd.DataFrame], pair: str) -> None:
        self._read = read
        self._pair = pair
        self._last_open_time: int | None = None

    @property
    def last_open_time(self) -> int | None:
        return self._last_open_time

    def poll(self) -> list[Candle]:
        """Return closed bars with ``open_time`` greater than the newest already returned,
        advancing the watermark. Empty when no new bar has closed (or the pair has no data)."""
        frame = load_candles(self._read, self._pair)
        if self._last_open_time is not None:
            frame = frame[frame["open_time"] > self._last_open_time]
        candles = frame_to_candles(frame)
        if candles:
            self._last_open_time = candles[-1].open_time
        return candles
