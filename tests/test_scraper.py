from __future__ import annotations

import pytest

from coinmon.data.adapters.base import RawBatch
from coinmon.data.adapters.binance import BinanceAdapter
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


def test_binance_adapter_shares_the_ccxt_spot_body():
    # Backtest-history venue: same generic normalization as Bybit, only the venue name differs.
    adapter = BinanceAdapter()
    assert adapter.name == "binance"
    raw = RawBatch("binance", "BTC/USDT", "1h", _rows(4), fetched_at=START + 3 * STEP + 1)
    df = adapter.to_candles(raw)
    assert list(df.columns) == list(CANDLE_COLUMNS)
    assert len(df) == 3  # the unclosed 4th bar is dropped, same as Bybit


def test_allow_gaps_stores_real_bars_across_downtime():
    # A genuine downtime gap (bar 3,4 missing) is rejected by default but tolerated when
    # require_contiguous is off — storing the REAL bars, never fabricating the missing ones.
    rows = _rows(3) + [[START + 5 * STEP, 1.0, 2.0, 0.5, 1.5, 10.0]]  # gap after bar 2
    raw = RawBatch("binance", "BTC/USDT", "1h", rows, fetched_at=START + 10 * STEP)

    with pytest.raises(ValueError, match="Non-contiguous"):
        BinanceAdapter().to_candles(raw)

    adapter = BinanceAdapter()
    adapter.require_contiguous = False
    df = adapter.to_candles(raw)
    assert len(df) == 4  # the 4 real bars kept; no synthetic bar invented for the gap
    assert df["open_time"].tolist() == [START + i * STEP for i in (0, 1, 2, 5)]


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


# --- funding-rate history (backward paging + incremental ingest, no network/DB) ---

FUNDING_STEP = 8 * STEP  # settlements every 8h


class FakePerpClient:
    """Serves canned funding settlements newest-window-first, paging backward via ``until`` —
    the exact contract the real Bybit endpoint has (H6 probe)."""

    def __init__(self, settlements: list[tuple[int, float]]):
        self._all = sorted(settlements)  # ascending by timestamp

    def fetch_funding_rate_history(self, symbol, limit=200, params=None):
        until = (params or {}).get("until")
        pool = [s for s in self._all if until is None or s[0] <= until]
        window = pool[-limit:]  # most-recent `limit`, returned oldest-first within the page
        return [{"timestamp": ts, "fundingRate": r} for ts, r in window]


class FundingAdapter(BybitAdapter):
    name = "fake"

    def __init__(self, settlements):
        super().__init__()
        self._fake = FakePerpClient(settlements)

    def _perp_client(self):
        return self._fake


def _settlements(n: int) -> list[tuple[int, float]]:
    return [(START + i * FUNDING_STEP, 0.0001 * (i % 3)) for i in range(n)]


def test_fetch_funding_pages_full_history_backward():
    # 500 settlements, 200/page -> three pages, all recovered oldest-first with no dupes.
    adapter = FundingAdapter(_settlements(500))
    rows = adapter.fetch_funding_history("BTC/USDC:USDC")

    assert len(rows) == 500
    assert [t for t, _ in rows] == sorted(t for t, _ in rows)
    assert rows[0][0] == START


def test_fetch_funding_stops_at_since():
    # Incremental: with `since` set, paging stops once a page reaches it (covers > since).
    adapter = FundingAdapter(_settlements(500))
    since = START + 450 * FUNDING_STEP
    rows = adapter.fetch_funding_history("BTC/USDC:USDC", since=since)

    assert rows  # served the recent window
    assert min(t for t, _ in rows) <= since  # reached back past `since`
    assert max(t for t, _ in rows) == START + 499 * FUNDING_STEP


def test_perp_symbol_appends_settle_currency():
    assert service.perp_symbol("BTC/USDC") == "BTC/USDC:USDC"


def test_ingest_funding_is_incremental(monkeypatch):
    stored: dict[int, float] = {}
    monkeypatch.setattr(
        service.db, "last_funding_time", lambda c, e, s: max(stored) if stored else None
    )

    def _insert(conn, exchange, symbol, rows):
        stored.update(dict(rows))
        return len(rows)

    monkeypatch.setattr(service.db, "insert_funding", _insert)

    adapter = FundingAdapter(_settlements(300))
    first = service.ingest_funding(adapter, conn=None, spot_symbol="BTC/USDC")
    assert first == 300

    # Second pass: nothing newer than the last stored settlement -> no new rows.
    again = service.ingest_funding(adapter, conn=None, spot_symbol="BTC/USDC")
    assert again == 0
    assert len(stored) == 300
