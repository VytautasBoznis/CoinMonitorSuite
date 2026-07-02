from __future__ import annotations

from coinmon.data.discovery import rank_spot, summarize_coverage

DAY = 86_400_000
START = 1_600_000_000_000


def test_rank_spot_filters_and_orders_by_volume():
    markets = {
        "BTC/USDT": {"spot": True, "active": True, "quote": "USDT"},
        "ETH/USDT": {"spot": True, "active": True, "quote": "USDT"},
        "SOL/USDT": {"spot": True, "active": True, "quote": "USDT"},
        "DOGE/USDC": {"spot": True, "active": True, "quote": "USDC"},  # wrong quote
        "OLD/USDT": {"spot": True, "active": False, "quote": "USDT"},  # inactive
        "BTC/USDT:USDT": {"swap": True, "active": True, "quote": "USDT"},  # not spot
    }
    tickers = {
        "BTC/USDT": {"quoteVolume": 900.0},
        "ETH/USDT": {"quoteVolume": 500.0},
        "SOL/USDT": {},  # missing volume -> treated as 0
    }
    ranked = rank_spot(markets, tickers, "USDT", limit=10)

    assert [sym for sym, _ in ranked] == ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
    assert ranked[0] == ("BTC/USDT", 900.0)
    assert ranked[-1][1] == 0.0


def test_rank_spot_honors_limit():
    markets = {f"C{i}/USDT": {"spot": True, "active": True, "quote": "USDT"} for i in range(5)}
    tickers = {f"C{i}/USDT": {"quoteVolume": float(i)} for i in range(5)}
    ranked = rank_spot(markets, tickers, "USDT", limit=2)

    assert len(ranked) == 2
    assert [sym for sym, _ in ranked] == ["C4/USDT", "C3/USDT"]  # highest volume first


def test_summarize_coverage_reports_universe_per_quote():
    # USDT training universe (3 bases -> 6 pairs) and USDC validation universe (2 bases -> 3),
    # counting distinct bases across venues; a short series is excluded and flagged.
    stats = [
        ("binance", "BTC/USDT", "1d", 2000, START, START + 2000 * DAY),
        ("bybit", "BTC/USDT", "1d", 900, START, START + 900 * DAY),  # same base, other venue
        ("binance", "ETH/USDT", "1d", 1500, START, START + 1500 * DAY),
        ("binance", "SOL/USDT", "1d", 850, START, START + 850 * DAY),
        ("bybit", "BTC/USDC", "1d", 900, START, START + 900 * DAY),
        ("bybit", "ETH/USDC", "1d", 850, START, START + 850 * DAY),
        ("bybit", "NEW/USDC", "1d", 100, START, START + 100 * DAY),  # short
    ]
    out = summarize_coverage(stats, min_bars=800)

    assert "== 1d (7 series) ==" in out
    assert "(short)" in out
    # 3 distinct USDT bases (BTC counted once across venues) -> 3 + C(3,2) = 6
    assert "3 USDT bases clear 800 bars → 6 auto-built pairs (3 direct + 3 ratios)" in out
    # 2 USDC bases -> 2 + C(2,2)=1 -> 3
    assert "2 USDC bases clear 800 bars → 3 auto-built pairs (2 direct + 1 ratios)" in out


def test_summarize_coverage_empty():
    assert "run the scraper first" in summarize_coverage([])
