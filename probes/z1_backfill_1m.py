"""Z1 collector — bulk backfill of 1-MINUTE candles from the free Binance public data dumps.

WHY THIS EXISTS. Two queued probes are pre-registered as 1m-bar questions and neither can run on
stored data: idea 8's liquidation-cascade ladder proxy ("bars with low >= 2.5% below prior close ->
does mid recover >= 1.2% within 60min") and idea 7's funding-settlement clock scalp
([[fable-batch-10-probe-queue]]). Audited 2026-07-31: the DB's finest broad series is 1h; the only
sub-hour data is a 1000-bar 5m scratch pull. Idea 8 gates the live 100 EUR ladder book
([[cursed-100-eur-live-ladder]]), so this ETL is the long pole.

Running the idea-8 proxy on 1h bars was considered and REJECTED: an hourly low cannot tell you
whether a resting bid 3% under mid was filled and reverted inside twenty minutes. It would produce
a number with no meaning.

WHY DUMPS, NOT ccxt. The existing BinanceAdapter pages 1000 bars per REST call; 1m over 5 years is
~2.9M bars per symbol = ~2900 requests each. The public dumps serve one zip per symbol-month.
Same data, ~3 orders of magnitude fewer round trips. Venue note: Binance is BACKTEST-HISTORY-ONLY
and never a trade venue ([[train-usdt-certify-usdc]]); "Bybit only" is an EXECUTION constraint, not
a data constraint ([[bybit-only-leverage-doctrine]]).

SCOPE (deliberately narrow, widen only if the probe is event-starved): the three symbols the live
ladder actually rests bids on. If idea 8's N < 300 events, add high-beta names (DOGE/AVAX/NEAR/LINK
are already in the 1h universe) rather than reaching further back in time.

Idempotent: upsert on the natural key (exchange, symbol, timeframe, open_time), so re-running
resumes rather than duplicating. Months already complete in the DB are skipped without downloading.

PERP (added 2026-10-08): `--perp` loads the USDT-M perpetual dumps for the same coins instead,
stored under the unified linear-perp symbol ("BTC/USDT:USDT", same convention as funding and OI).
The live ladder rests bids on perps, and the spot F8 pass left SPOT -> PERP as its biggest
untested assumption ([[f8-cascade-ladder-result]]).

Run:
  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
  PYTHONPATH="src;." .venv/Scripts/python probes/z1_backfill_1m.py [--perp]
"""
from __future__ import annotations

import io
import sys
import urllib.error
import urllib.request
import zipfile
from datetime import date

import pandas as pd

from coinmon.data import db

EXCHANGE = "binance"
TIMEFRAME = "1m"
SYMBOLS = [
    # The three the live ladder actually rests bids on.
    "BTC/USDT", "ETH/USDT", "SOL/USDT",
    # High-beta names added 2026-07-31 after the first F8 smoke test: BTC alone yielded 31 events
    # against a pre-registered N >= 300. A 2.5% one-minute drop is rare on BTC and common on alts,
    # so the sample is widened by SYMBOL rather than by loosening the frozen 2.5% threshold.
    "DOGE/USDT", "AVAX/USDT", "NEAR/USDT", "LINK/USDT", "SHIB/USDT", "ADA/USDT", "XRP/USDT",
]
# USDT-M perp counterparts of SYMBOLS. SHIB trades there only as the 1000x contract; every consumer
# works on returns, so the price scale is irrelevant.
PERP_SYMBOLS = [
    "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT",
    "DOGE/USDT:USDT", "AVAX/USDT:USDT", "NEAR/USDT:USDT", "LINK/USDT:USDT", "1000SHIB/USDT:USDT",
    "ADA/USDT:USDT", "XRP/USDT:USDT",
]
START = date(2021, 1, 1)
BASE_URL = "https://data.binance.vision/data/spot/monthly/klines"
PERP_URL = "https://data.binance.vision/data/futures/um/monthly/klines"

# Binance kline CSV layout (headerless in older months, headered in newer ones).
_COLS = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore",
]


def _months(start: date, end: date) -> list[tuple[int, int]]:
    """Every (year, month) from ``start`` through ``end`` inclusive."""
    out, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _fetch_month(symbol: str, year: int, month: int, base_url: str) -> pd.DataFrame | None:
    """Download and normalize one symbol-month zip. Returns None if Binance has no such file."""
    native = symbol.split(":")[0].replace("/", "")
    name = f"{native}-{TIMEFRAME}-{year:04d}-{month:02d}"
    url = f"{base_url}/{native}/{TIMEFRAME}/{name}.zip"
    try:
        with urllib.request.urlopen(url, timeout=120) as resp:
            blob = resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise

    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        raw = zf.read(f"{name}.csv")

    # Older dumps are headerless; newer ones carry a header row. Sniff the first field.
    first = raw[:32].split(b",", 1)[0]
    header = 0 if first.strip().lower() == b"open_time" else None
    df = pd.read_csv(io.BytesIO(raw), header=header, names=_COLS, usecols=range(len(_COLS)))

    # Binance switched dump timestamps from ms to microseconds partway through 2025.
    ts = df["open_time"].astype("int64")
    df["open_time"] = (ts // 1000).where(ts > 10**14, ts)
    return df[["open_time", "open", "high", "low", "close", "volume"]].astype(
        {"open_time": "int64", "open": float, "high": float,
         "low": float, "close": float, "volume": float}
    )


def _stored_counts(conn) -> dict[tuple[str, int, int], int]:
    """Bars already stored per (symbol, year, month) — lets a re-run skip complete months."""
    rows = conn.execute(
        """
        SELECT symbol,
               EXTRACT(YEAR  FROM to_timestamp(open_time / 1000))::int,
               EXTRACT(MONTH FROM to_timestamp(open_time / 1000))::int,
               count(*)
        FROM candles WHERE exchange = %s AND timeframe = %s
        GROUP BY 1, 2, 3
        """,
        (EXCHANGE, TIMEFRAME),
    ).fetchall()
    return {(r[0], r[1], r[2]): r[3] for r in rows}


def _copy_upsert(conn, df: pd.DataFrame, symbol: str) -> int:
    """Bulk-load one month via COPY into a staging table, then upsert. executemany at 8M rows
    is the difference between minutes and hours; the natural-key conflict rule is unchanged."""
    with conn.cursor() as cur:
        cur.execute(
            "CREATE TEMP TABLE IF NOT EXISTS stage_1m ("
            "open_time bigint, open float8, high float8, low float8, close float8, volume float8)"
        )
        cur.execute("TRUNCATE stage_1m")
        with cur.copy("COPY stage_1m FROM STDIN") as cp:
            for row in df.itertuples(index=False):
                cp.write_row(row)
        cur.execute(
            """
            INSERT INTO candles
                (exchange, symbol, timeframe, open_time, open, high, low, close, volume)
            SELECT %s, %s, %s, open_time, open, high, low, close, volume FROM stage_1m
            ON CONFLICT (exchange, symbol, timeframe, open_time) DO UPDATE SET
                open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
                close = EXCLUDED.close, volume = EXCLUDED.volume
            """,
            (EXCHANGE, symbol, TIMEFRAME),
        )
    conn.commit()
    return len(df)


def main() -> None:
    today = date.today()
    # Only complete months are published as monthly zips.
    end = date(today.year, today.month, 1) - pd.Timedelta(days=1).to_pytimedelta()
    conn = db.connect()
    db.init_schema(conn)
    stored = _stored_counts(conn)
    perp = "--perp" in sys.argv
    symbols, base_url = (PERP_SYMBOLS, PERP_URL) if perp else (SYMBOLS, BASE_URL)

    print(f"Z1 1m backfill — {EXCHANGE} {symbols} {START:%Y-%m} .. {end:%Y-%m}\n")
    total = 0
    for symbol in symbols:
        for year, month in _months(START, end):
            # A full month is 28*1440=40320 bars at minimum; anything less may be a partial load.
            if stored.get((symbol, year, month), 0) >= 40320:
                continue
            df = _fetch_month(symbol, year, month, base_url)
            if df is None:
                print(f"  {symbol} {year}-{month:02d}  no dump (404)")
                continue
            n = _copy_upsert(conn, df, symbol)
            total += n
            print(f"  {symbol} {year}-{month:02d}  {n:>7,} bars")
    print(f"\nDone — {total:,} bars written.")


if __name__ == "__main__":
    main()
