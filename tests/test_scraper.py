from __future__ import annotations

import pytest

from coinmon.data.adapters.base import RawBatch
from coinmon.data.adapters.bybit import BybitAdapter
from coinmon.data.models import CANDLE_COLUMNS
from coinmon.scraper import service

STEP = 3_600_000  # 1h in ms
START = 1_750_000_000_000  # arbitrary epoch-ms anchor


def _rows(n: int, start: int = START, step: int = STEP) -> list[list[float]]:
    return [[start + i * step, 1.0, 2.0, 0.5, 1.5, 10.0] for i in range(n)]


# --- adapter normalization (pure, no network) ---


def test_to_candles_normalizes_to_contract():
    # 3 closed bars + 1 in-progress; fetched_at lands inside the 4th bar.
    raw = RawBatch("bybit", "BTC/USDC", "1h", _rows(4), fetched_at=START + 3 * STEP + 1)
    df = BybitAdapter().to_candles(raw)

    assert list(df.columns) == list(CANDLE_COLUMNS)
    assert len(df) == 3  # the unclosed 4th bar is dropped
    assert df["open_time"].dtype == "int64"
    assert df["open_time"].is_monotonic_increasing
    assert df["close"].dtype == "float64"


def test_to_candles_rejects_gaps():
    rows = _rows(3) + [[START + 5 * STEP, 1.0, 2.0, 0.5, 1.5, 10.0]]  # missing bar 3,4
    raw = RawBatch("bybit", "BTC/USDC", "1h", rows, fetched_at=START + 10 * STEP)
    with pytest.raises(ValueError, match="Non-contiguous"):
        BybitAdapter().to_candles(raw)


# --- scraper ingest loop (fake adapter + in-memory store, no network/DB) ---


class FakeAdapter(BybitAdapter):
    """Real to_candles/market_symbol; fetch_raw serves a canned series one page at a time."""

    name = "fake"

    def __init__(self, n_bars: int, now: int, page: int = 3):
        self._all = _rows(n_bars)
        self._now = now
        self._page = page

    def fetch_raw(self, symbol, timeframe, since=None, until=None):
        rows = [r for r in self._all if since is None or r[0] >= since][: self._page]
        return RawBatch(self.name, symbol, timeframe, rows, fetched_at=self._now)


class FakeStore:
    def __init__(self):
        self.candles: dict = {}
        self.raw: list = []

    def last_open_time(self, conn, exchange, symbol, timeframe):
        times = [ot for (e, s, t, ot) in self.candles if (e, s, t) == (exchange, symbol, timeframe)]
        return max(times) if times else None

    def insert_raw(self, conn, batch):
        self.raw.append(batch)

    def upsert_candles(self, conn, df, exchange, symbol, timeframe):
        for row in df.itertuples(index=False):
            self.candles[(exchange, symbol, timeframe, int(row.open_time))] = tuple(row)
        return len(df)


@pytest.fixture
def store(monkeypatch):
    s = FakeStore()
    monkeypatch.setattr(service.db, "last_open_time", s.last_open_time)
    monkeypatch.setattr(service.db, "insert_raw", s.insert_raw)
    monkeypatch.setattr(service.db, "upsert_candles", s.upsert_candles)
    monkeypatch.setattr(service, "_start_ms", lambda _iso: START)
    return s


def test_ingest_pages_through_full_backfill(store):
    adapter = FakeAdapter(n_bars=7, now=START + 7 * STEP, page=3)
    stored = service.ingest_series(adapter, conn=None, symbol="BTC/USDC", timeframe="1h")

    assert stored == 7
    assert len(store.candles) == 7
    assert len(store.raw) == 3  # 3 + 3 + 1 across three pages


def test_ingest_is_idempotent_when_current(store):
    adapter = FakeAdapter(n_bars=7, now=START + 7 * STEP, page=3)
    service.ingest_series(adapter, conn=None, symbol="BTC/USDC", timeframe="1h")

    # Second pass: cursor is past the newest stored bar -> nothing new, no dupes.
    again = service.ingest_series(adapter, conn=None, symbol="BTC/USDC", timeframe="1h")
    assert again == 0
    assert len(store.candles) == 7
