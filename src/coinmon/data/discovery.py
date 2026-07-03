from __future__ import annotations

from datetime import UTC, datetime

# Chunk T data-expansion helpers: pure functions so the ccxt/DB calls stay in the CLI and the
# filtering/aggregation logic is unit-testable without network or a database.


def rank_spot(
    markets: dict, tickers: dict, quote: str, limit: int = 30
) -> list[tuple[str, float]]:
    """Rank active ``*/QUOTE`` spot markets by recent 24h quote volume (liquidity proxy).

    ``markets`` and ``tickers`` are ccxt's ``load_markets()`` / ``fetch_tickers()`` payloads.
    Liquidity is the cheap, one-request proxy for "established coin with long history"; the
    true usable history is measured post-scrape by :func:`summarize_coverage`. Returns the top
    ``limit`` ``(symbol, quote_volume)`` pairs, highest volume first.
    """
    ranked: list[tuple[str, float]] = []
    for sym, m in markets.items():
        if m.get("spot") and m.get("active") and m.get("quote") == quote:
            vol = (tickers.get(sym) or {}).get("quoteVolume") or 0.0
            ranked.append((sym, float(vol)))
    ranked.sort(key=lambda sv: sv[1], reverse=True)
    return ranked[:limit]


def _fmt_day(open_time_ms: int) -> str:
    return datetime.fromtimestamp(open_time_ms / 1000, UTC).strftime("%Y-%m-%d")


def summarize_coverage(
    stats: list[tuple[str, str, str, int, int, int]],
    min_bars: int = 800,
) -> str:
    """Human-readable coverage report from ``db.series_stats`` rows.

    ``stats`` is ``(exchange, symbol, timeframe, bar_count, min_open_time, max_open_time)``.
    Per timeframe: each stored series (venue + bar count + date span), then per quote currency
    the distinct base coins that clear ``min_bars`` on any venue and the resulting auto-built
    universe size (``k`` bases yield ``k + C(k,2)`` search pairs — mirrors ``build_universe``).
    Reporting per quote makes the USDT training universe and the USDC validation universe
    ([[train-usdt-certify-usdc]]) legible side by side.
    """
    if not stats:
        return "no candles stored — run the scraper first"

    by_tf: dict[str, list[tuple[str, str, int, int, int]]] = {}
    for exchange, symbol, timeframe, count, lo, hi in stats:
        by_tf.setdefault(timeframe, []).append((exchange, symbol, count, lo, hi))

    lines: list[str] = []
    for timeframe in sorted(by_tf):
        rows = sorted(by_tf[timeframe], key=lambda r: r[2], reverse=True)
        lines.append(f"== {timeframe} ({len(rows)} series) ==")
        for exchange, symbol, count, lo, hi in rows:
            flag = "" if count >= min_bars else "  (short)"
            lines.append(
                f"  {exchange:<8} {symbol:<16} {count:>6} bars  "
                f"{_fmt_day(lo)} → {_fmt_day(hi)}{flag}"
            )
        # Distinct base coins per quote that clear min_bars on at least one venue.
        bases_by_quote: dict[str, set[str]] = {}
        for _exchange, symbol, count, _lo, _hi in rows:
            if count >= min_bars and "/" in symbol:
                base, quote = symbol.split("/", 1)
                bases_by_quote.setdefault(quote, set()).add(base)
        for quote in sorted(bases_by_quote):
            k = len(bases_by_quote[quote])
            ratios = k * (k - 1) // 2
            lines.append(
                f"  → {k} {quote} bases clear {min_bars} bars → {k + ratios} auto-built pairs "
                f"({k} direct + {ratios} ratios)"
            )
        lines.append("")
    return "\n".join(lines).rstrip()
