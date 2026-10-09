"""Dashboard backend: pure views, the public-market reader, and the API's stop endpoints."""

from __future__ import annotations

import json

import httpx
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from coinmon.config import settings
from coinmon.dashboard import views
from coinmon.dashboard.api import create_app
from coinmon.dashboard.market import Market
from coinmon.live import stop
from coinmon.live.control import DRAIN, HALT, RUN, Control, Trade, now_ms

MIN = 60_000


# --- views ---


def test_heartbeat_state():
    now = 1_000_000_000
    assert views.heartbeat_state(None, now) == "never"
    assert views.heartbeat_state(now - 5_000, now) == "alive"
    assert views.heartbeat_state(now - (views.STALE_S + 1) * 1000, now) == "stale"


def _trade(**kw) -> Trade:
    base = dict(bot="f8-ladder", venue="fake", coin="BTC", entry_oid=1, anchor_close=102.5, sz=0.5,
                fill_px=100.0, fill_ms=0, entry_fee=0.01, leverage="isolated 5", liq_px=None)
    return Trade(**(base | kw))


def test_ledger_nets_fees_and_leaves_open_trades_open():
    closed = _trade(exit_px=101.2, exit_ms=30 * MIN, exit_fee=0.02, exit_reason="tp")
    still = _trade(entry_oid=2, anchor_close=None)
    rows = views.ledger_rows([closed, still])
    assert rows[0]["net_usd"] == pytest.approx(0.6 - 0.03)
    assert rows[0]["net"] == pytest.approx(0.012 - 0.03 / 50)
    assert rows[0]["drop"] == pytest.approx(100 / 102.5 - 1)
    assert rows[1]["net"] is None and rows[1]["drop"] is None
    s = views.ledger_summary(rows)
    assert (s["open"], s["closed"], s["wins"]) == (1, 1, 1)
    assert s["realized_usd"] == pytest.approx(0.57)
    assert s["fees_usd"] == pytest.approx(0.04)


def test_coverage_gaps_is_the_uncovered_rest_of_the_window():
    assert views.coverage_gaps([], 0, 10 * MIN) == [(0, 10 * MIN)]
    assert views.coverage_gaps([(0, 10 * MIN)], 0, 10 * MIN) == []
    spans = [(0, 3 * MIN), (2 * MIN, 4 * MIN), (6 * MIN, 8 * MIN)]
    assert views.coverage_gaps(spans, 0, 10 * MIN) == [(4 * MIN, 6 * MIN), (8 * MIN, 10 * MIN)]
    # a 30s hole (span edges are fuzzy) is not a gap; a span past the window clips
    assert views.coverage_gaps([(-MIN, 2 * MIN), (2 * MIN + 30_000, 20 * MIN)], 0, 10 * MIN) == []
    assert views.coverage_gaps([(12 * MIN, 20 * MIN)], 0, 10 * MIN) == [(0, 10 * MIN)]


def test_liquidation_buckets_split_forced_selling_from_buying():
    prints = pd.DataFrame({
        "ts": [MIN + 1, MIN + 59_999, MIN + 5, 5 * MIN],
        "side": [views.LONGS, views.LONGS, views.SHORTS, views.LONGS],
        "price": [100.0, 90.0, 100.0, 80.0],
        "size": [1.0, 2.0, 0.5, 1.0],
    })
    assert views.liquidation_buckets(prints, MIN) == [
        {"time": MIN, "sell": 280.0, "buy": 50.0},
        {"time": 5 * MIN, "sell": 80.0, "buy": 0.0},
    ]
    assert views.liquidation_buckets(prints.iloc[:0], MIN) == []


# --- market ---


META = {"universe": [{"name": "BTC"}, {"name": "DOGE"}]}
CTXS = [
    {"markPx": "100.0", "midPx": "100.5", "prevDayPx": "90.0", "funding": "0.0001",
     "openInterest": "2.0", "dayNtlVlm": "5000.0"},
    {"markPx": "0.1", "midPx": None, "prevDayPx": "0.1", "funding": "0", "openInterest": "1",
     "dayNtlVlm": "1"},
]
STATE = {
    "marginSummary": {"accountValue": "98.5", "totalMarginUsed": "2.4", "totalNtlPos": "12.0"},
    "withdrawable": "96.1",
    "assetPositions": [
        {"position": {"coin": "BTC", "szi": "0.00015", "entryPx": "80000", "positionValue": "12",
                      "unrealizedPnl": "-0.1", "liquidationPx": "64500", "marginUsed": "2.4",
                      "leverage": {"type": "isolated", "value": 5}}},
        {"position": {"coin": "ETH", "szi": "0", "entryPx": "1", "positionValue": "0",
                      "unrealizedPnl": "0", "liquidationPx": None, "marginUsed": "0",
                      "leverage": {"type": "isolated", "value": 5}}},
    ],
}
ORDERS = [{"coin": "BTC", "oid": 7, "side": "A", "limitPx": "80960", "sz": "0.00015",
           "reduceOnly": True, "timestamp": 1}]


def _market() -> tuple[Market, list[dict]]:
    sent: list[dict] = []

    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        sent.append(body)
        data = {"metaAndAssetCtxs": [META, CTXS], "clearinghouseState": STATE,
                "frontendOpenOrders": ORDERS,
                "candleSnapshot": [{"t": 0, "o": "1", "h": "2", "l": "0.5", "c": "1.5",
                                    "v": "3"}]}[body["type"]]
        return httpx.Response(200, json=data)

    return Market(True, httpx.Client(transport=httpx.MockTransport(handle))), sent


def test_market_parses_contexts_and_serves_repeats_from_cache():
    m, sent = _market()
    ctx = m.contexts(("BTC", "ETH"))
    assert ctx == {"BTC": {"mark": 100.0, "mid": 100.5, "prev_day": 90.0, "funding": 0.0001,
                           "open_interest_usd": 200.0, "day_volume_usd": 5000.0}}
    m.contexts(("BTC",))
    assert len(sent) == 1


def test_market_account_skips_flat_positions():
    m, _ = _market()
    acct = m.account("0xmaster")
    assert acct["equity"] == 98.5 and acct["withdrawable"] == 96.1
    assert [p["coin"] for p in acct["positions"]] == ["BTC"]
    assert acct["positions"][0]["leverage"] == "isolated 5"
    assert acct["orders"][0] == {"coin": "BTC", "oid": 7, "side": "A", "px": 80960.0,
                                 "sz": 0.00015, "reduce_only": True, "time": 1}


def test_market_candle_requests_within_10s_share_the_cache():
    m, sent = _market()
    t = 1_800_000_000_000
    assert m.candles("BTC", "1m", 10, t)[0]["close"] == 1.5
    m.candles("BTC", "1m", 10, t + 5_000)
    assert len(sent) == 1


# --- api ---


class FakeStore:
    def __init__(self, ctl: Control | None) -> None:
        self.ctl = ctl
        self.modes: list[tuple] = []

    def read(self) -> Control:
        if self.ctl is None:
            raise ConnectionError("db down")
        return self.ctl

    def set_mode(self, mode, reason, deadline_ms=None) -> None:
        self.modes.append((mode, reason, deadline_ms))
        if self.ctl is not None:
            self.ctl = Control(mode, reason, deadline_ms, now_ms(), self.ctl.heartbeat_ms)

    def trades(self, venue, open_only=False, limit=1000):
        return [_trade(exit_px=101.2, exit_ms=30 * MIN, exit_fee=0.02, exit_reason="tp")]


@pytest.fixture
def api(monkeypatch, tmp_path):
    store = FakeStore(Control(RUN, "resume", None, 0, now_ms()))
    panics: list[str] = []

    def fake_panic(hl, st, reason):
        panics.append(reason)
        st.set_mode(HALT, reason)
        return True

    monkeypatch.setattr(stop, "panic", fake_panic)
    monkeypatch.setattr(settings, "hl_address", "0xmaster")
    monkeypatch.setattr(settings, "hl_agent_key", "0xagent")
    client = TestClient(create_app(store=store, market=_market()[0], venue_client=object,
                                   dist=tmp_path / "no-dist"))
    client.store, client.panics = store, panics
    return client


def test_state_reports_heartbeat_and_survives_the_db_down(api):
    body = api.get("/api/state").json()
    assert (body["db"], body["mode"], body["heartbeat"]) == (True, RUN, "alive")
    api.store.ctl = None
    body = api.get("/api/state").json()
    assert body["db"] is False and "db down" in body["error"]


def test_panic_needs_json_confirm_and_a_key(api, monkeypatch):
    # a cross-site form or script posts text/plain: rejected before anything runs
    r = api.post("/api/panic", content='{"confirm": true}', headers={"content-type": "text/plain"})
    assert r.status_code == 422
    assert api.post("/api/panic", json={}).status_code == 422
    assert api.panics == []

    r = api.post("/api/panic", json={"confirm": True})
    assert r.json() == {"flat": True}
    assert api.panics == ["dashboard panic"] and api.store.ctl.mode == HALT

    monkeypatch.setattr(settings, "hl_agent_key", "")
    assert api.post("/api/panic", json={"confirm": True}).status_code == 409
    assert api.get("/api/config").json()["keyed"] is False


def test_panic_works_with_the_db_down(api):
    api.store.ctl = None
    assert api.post("/api/panic", json={"confirm": True}).json() == {"flat": True}


def test_drain_sets_a_deadline_and_only_from_run(api):
    before = now_ms()
    r = api.post("/api/drain", json={"minutes": 30})
    assert r.status_code == 200
    mode, reason, deadline = api.store.modes[-1]
    assert (mode, reason) == (DRAIN, "dashboard drain")
    assert before + 30 * MIN <= deadline <= now_ms() + 30 * MIN
    assert api.post("/api/drain", json={"minutes": 30}).status_code == 409  # already draining
    assert api.post("/api/drain", json={"minutes": 0}).status_code == 422
    api.store.ctl = None
    assert api.post("/api/drain", json={"minutes": 30}).status_code == 503


def test_reads(api, monkeypatch):
    assert api.get("/api/candles", params={"coin": "DOGE"}).status_code == 422
    assert api.get("/api/candles", params={"coin": "BTC"}).json()[0]["close"] == 1.5
    assert api.get("/api/account").json()["equity"] == 98.5
    assert api.get("/api/trades").json()["summary"]["wins"] == 1
    monkeypatch.setattr(settings, "hl_address", "")
    assert api.get("/api/account").json() == {"configured": False}


def test_serves_the_built_frontend_beside_the_api(tmp_path):
    (tmp_path / "index.html").write_text("<html>terminal</html>")
    client = TestClient(create_app(store=FakeStore(None), market=_market()[0], dist=tmp_path))
    assert "terminal" in client.get("/").text
    assert client.get("/api/config").json()["coins"] == ["BTC", "ETH", "SOL"]
