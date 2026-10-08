from __future__ import annotations

import asyncio

from coinmon.scraper import liquidations as liq

NAMES = {"BTCUSDT": "BTC/USDT:USDT", "BTCPERP": "BTC/USDC:USDC"}


def _ack(symbol: str, success: bool = True) -> dict:
    return {"success": success, "ret_msg": "" if success else "error:handler not found",
            "req_id": symbol, "op": "subscribe"}


def _print(symbol: str, t: int) -> dict:
    return {"topic": f"allLiquidation.{symbol}", "type": "snapshot", "ts": t + 50,
            "data": [{"T": t, "s": symbol, "S": "Buy", "v": "0.002", "p": "80408.90"}]}


# --- message parsing (pure) ---


def test_parse_message_maps_symbol_and_keeps_side_verbatim():
    rows = liq.parse_message(_print("BTCUSDT", 1_000), NAMES, recv_ms=1_400)
    assert rows == [("bybit", "BTC/USDT:USDT", 1_000, "Buy", 80408.9, 0.002, 1_400)]


def test_parse_message_ignores_acks_pongs_and_unknown_topics():
    pong = {"success": True, "ret_msg": "pong", "req_id": "", "op": "ping"}
    other = {"topic": "publicTrade.BTCUSDT", "data": [{"T": 1}]}
    for msg in (_ack("BTCUSDT"), pong, other):
        assert liq.parse_message(msg, NAMES, 0) == []


def test_parse_message_falls_back_to_bybit_id_for_unmapped_symbol():
    rows = liq.parse_message(_print("NEWUSDT", 5), NAMES, 6)
    assert rows[0][1] == "NEWUSDT"


# --- coverage state machine ---


def _collector_with_shard(symbols):
    c = liq.LiquidationCollector()
    c.names = dict(NAMES)
    shard = liq._Shard(list(symbols))
    c.shards.append(shard)
    return c, shard


def test_coverage_starts_at_successful_ack_only():
    c, shard = _collector_with_shard(["BTCUSDT", "GONEUSDT"])
    c.handle(shard, _ack("BTCUSDT"), 100)
    c.handle(shard, _ack("GONEUSDT", success=False), 101)
    assert shard.started == {"BTCUSDT": 100}


def test_live_span_ends_at_last_message_heard_on_the_connection():
    c, shard = _collector_with_shard(["BTCUSDT"])
    c.handle(shard, _ack("BTCUSDT"), 100)
    c.handle(shard, {"op": "ping", "ret_msg": "pong", "success": True}, 900)  # pong = liveness
    rows, closed, spans = c.snapshot()
    assert rows == [] and closed == []
    assert spans == [("bybit", "BTC/USDT:USDT", 100, 900)]


def test_dropped_connection_freezes_span_and_next_ack_opens_a_new_one():
    c, shard = _collector_with_shard(["BTCUSDT"])
    c.handle(shard, _ack("BTCUSDT"), 100)
    c.handle(shard, _print("BTCUSDT", 450), 500)
    c.end_coverage(shard)  # connection lost
    c.handle(shard, _ack("BTCUSDT"), 2_000)  # reconnected
    rows, closed, spans = c.snapshot()
    assert len(rows) == 1
    assert closed == [("bybit", "BTC/USDT:USDT", 100, 500)]
    assert spans == closed + [("bybit", "BTC/USDT:USDT", 2_000, 2_000)]


def test_failed_flush_restores_rows_and_frozen_spans_ahead_of_newer_ones():
    c, shard = _collector_with_shard(["BTCUSDT"])
    c.handle(shard, _ack("BTCUSDT"), 100)
    c.handle(shard, _print("BTCUSDT", 150), 200)
    c.end_coverage(shard)
    rows, closed, _ = c.snapshot()
    c.handle(shard, _print("BTCUSDT", 250), 300)  # arrives while the write is failing
    c.restore(rows, closed)
    assert [r[2] for r in c.rows] == [150, 250]
    assert c.closed == [("bybit", "BTC/USDT:USDT", 100, 200)]


# --- instrument refresh / sharding ---


def test_discover_shards_then_tops_up_and_prunes(monkeypatch):
    listing = {f"S{i:03d}USDT": f"S{i:03d}/USDT:USDT" for i in range(liq.SHARD_SIZE + 5)}

    async def fake_fetch(_session):
        return dict(listing)

    monkeypatch.setattr(liq, "fetch_perps", fake_fetch)
    c = liq.LiquidationCollector()

    fresh = asyncio.run(c.discover(None))
    assert [len(s.symbols) for s in fresh] == [liq.SHARD_SIZE, 5]

    # Next refresh: one delisting, a few new listings -> pruned, last shard topped up, no new conn.
    del listing["S000USDT"]
    listing.update({"NEW1USDT": "NEW1/USDT:USDT", "NEW2USDT": "NEW2/USDT:USDT"})
    fresh = asyncio.run(c.discover(None))
    assert fresh == []
    assert "S000USDT" not in c.shards[0].symbols
    assert c.shards[1].symbols[-2:] == ["NEW1USDT", "NEW2USDT"]
    assert c.names["NEW1USDT"] == "NEW1/USDT:USDT"
