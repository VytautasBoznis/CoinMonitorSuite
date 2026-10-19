"""Z2: every Binance USDT-M perp EVER listed, delisted ones included: 1d klines + funding.

WHY. The DB is a survivor universe: every series it holds still trades ([[b13-low-vol-fresh-lead]],
0 delistings), so any short-side or cross-sectional test is biased toward coins that made it.
Binance's public dumps keep the full history of delisted contracts (LUNA, FTT, SRM...), and the
fapi REST endpoints that F6/F11 used do not. Fable's batch named this ETL as the gate for idea 4
(token-unlock shorts) and for all future cross-sectional work ([[fable-batch-10-probe-queue]]).

WHAT. The symbol list comes from the dump bucket's own listing (every `<COIN>USDT` directory under
um/monthly/klines), so nothing depends on the live exchangeInfo. Per symbol, the monthly zips that
exist are listed and loaded:
  * candles 1d   -> candles (exchange 'binance', symbol '<COIN>/USDT:USDT', timeframe '1d')
  * funding      -> funding_rates (exchange 'binance', same symbol), funding_time = the dump's
                    calc_time. The 10 F8 perps already stored there came from these same dumps,
                    so their keys match exactly and a re-load overwrites rather than duplicates.
Only complete months are published. Idempotent upserts on the natural keys; months already stored
are skipped.

Run (`--limit N` loads only the first N symbols, for a timing check):
  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
  PYTHONPATH="src;." .venv/Scripts/python probes/z2_backfill_um_1d.py [--limit N]
"""
from __future__ import annotations

import io
import re
import sys
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

from coinmon.data import db

EXCHANGE = "binance"
BUCKET = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
FILES = "https://data.binance.vision"
KLINES = "data/futures/um/monthly/klines"
FUNDING = "data/futures/um/monthly/fundingRate"
WORKERS = 32
_KLINE_COLS = ["open_time", "open", "high", "low", "close", "volume", "close_time",
               "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore"]


_local = threading.local()


def _get(url: str) -> bytes:
    """GET on a per-thread keep-alive session (a TLS handshake per file doubled the time)."""
    if not hasattr(_local, "s"):
        _local.s = requests.Session()
    for attempt in range(4):
        try:
            r = _local.s.get(url, timeout=60)
            r.raise_for_status()
            return r.content
        except Exception:  # noqa: BLE001 - transient CDN errors; the last attempt re-raises
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)
    raise AssertionError


def _list(prefix: str, delimiter: bool = False) -> list[str]:
    """Keys (or sub-directory prefixes) under a bucket prefix, following pagination."""
    out, marker = [], ""
    tag = "Prefix" if delimiter else "Key"
    while True:
        url = f"{BUCKET}?prefix={prefix}&max-keys=1000&marker={marker}"
        xml = _get(url + ("&delimiter=/" if delimiter else "")).decode()
        found = re.findall(rf"<{tag}>([^<]*)</{tag}>", xml)
        if delimiter:
            found = [f for f in found if f != prefix]
        out += found
        if "<IsTruncated>true</IsTruncated>" not in xml:
            return out
        nxt = re.search(r"<NextMarker>([^<]*)</NextMarker>", xml)
        marker = nxt.group(1) if nxt else found[-1]


def _csv(blob: bytes, first_col: str) -> tuple[bytes, bool]:
    """The zip's CSV and whether it has a header row (older dumps are headerless)."""
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        raw = zf.read(zf.namelist()[0])
    return raw, raw[:32].split(b",", 1)[0].strip().lower() == first_col.encode()


def _klines(key: str) -> pd.DataFrame:
    raw, header = _csv(_get(f"{FILES}/{key}"), "open_time")
    df = pd.read_csv(io.BytesIO(raw), header=0 if header else None, names=_KLINE_COLS,
                     usecols=range(len(_KLINE_COLS)))
    ts = df["open_time"].astype("int64")
    df["open_time"] = (ts // 1000).where(ts > 10**14, ts)  # some dumps switched to microseconds
    return df[["open_time", "open", "high", "low", "close", "volume"]]


def _funding(key: str) -> list[tuple[int, float]]:
    raw, header = _csv(_get(f"{FILES}/{key}"), "calc_time")
    df = pd.read_csv(io.BytesIO(raw), header=0 if header else None,
                     names=["calc_time", "funding_interval_hours", "last_funding_rate"])
    return list(zip(df["calc_time"].astype("int64").tolist(),
                    df["last_funding_rate"].astype(float).tolist(), strict=True))


def _ym(key: str) -> tuple[int, int]:
    y, m = re.search(r"-(\d{4})-(\d{2})\.zip$", key).groups()
    return int(y), int(m)


def _stored(conn) -> tuple[set, set]:
    c = conn.execute(
        "SELECT DISTINCT symbol, EXTRACT(YEAR FROM to_timestamp(open_time / 1000))::int,"
        " EXTRACT(MONTH FROM to_timestamp(open_time / 1000))::int FROM candles"
        " WHERE exchange = %s AND timeframe = '1d' AND symbol LIKE '%%:USDT'",
        (EXCHANGE,)).fetchall()
    f = conn.execute(
        "SELECT DISTINCT symbol, EXTRACT(YEAR FROM to_timestamp(funding_time / 1000))::int,"
        " EXTRACT(MONTH FROM to_timestamp(funding_time / 1000))::int FROM funding_rates"
        " WHERE exchange = %s", (EXCHANGE,)).fetchall()
    return {tuple(r) for r in c}, {tuple(r) for r in f}


def _copy_upsert(conn, sym: str, candles: pd.DataFrame, funding: list) -> None:
    """COPY into temp staging tables, then upsert on the natural keys (executemany was the
    second bottleneck: ~5k rows/s against ~3M funding rows)."""
    with conn.cursor() as cur:
        cur.execute("CREATE TEMP TABLE IF NOT EXISTS stage_c (open_time bigint, open float8,"
                    " high float8, low float8, close float8, volume float8)")
        cur.execute("CREATE TEMP TABLE IF NOT EXISTS stage_f (funding_time bigint, rate float8)")
        cur.execute("TRUNCATE stage_c; TRUNCATE stage_f")
        with cur.copy("COPY stage_c FROM STDIN") as cp:
            for row in candles.itertuples(index=False):
                cp.write_row(row)
        with cur.copy("COPY stage_f FROM STDIN") as cp:
            for row in funding:
                cp.write_row(row)
        cur.execute(
            "INSERT INTO candles (exchange, symbol, timeframe, open_time, open, high, low, close,"
            " volume) SELECT %s, %s, '1d', open_time, open, high, low, close, volume FROM stage_c"
            " ON CONFLICT (exchange, symbol, timeframe, open_time) DO UPDATE SET"
            " open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,"
            " close = EXCLUDED.close, volume = EXCLUDED.volume", (EXCHANGE, sym))
        cur.execute(
            "INSERT INTO funding_rates (exchange, symbol, funding_time, rate)"
            " SELECT %s, %s, funding_time, rate FROM stage_f"
            " ON CONFLICT (exchange, symbol, funding_time) DO UPDATE SET rate = EXCLUDED.rate",
            (EXCHANGE, sym))
    conn.commit()


def _load_symbol(native: str, have_c: set, have_f: set):
    """Download one symbol's missing months (runs in a worker thread; no DB access)."""
    sym = f"{native[:-4]}/USDT:USDT"
    ck = [k for k in _list(f"{KLINES}/{native}/1d/") if k.endswith(".zip")]
    fk = [k for k in _list(f"{FUNDING}/{native}/") if k.endswith(".zip")]
    ck = [k for k in ck if (sym, *_ym(k)) not in have_c]
    fk = [k for k in fk if (sym, *_ym(k)) not in have_f]
    candles = pd.concat([_klines(k) for k in ck]) if ck else pd.DataFrame()
    funding = [row for k in fk for row in _funding(k)]
    return sym, candles, funding


def main() -> None:
    t0 = time.time()
    natives = sorted(p.rstrip("/").rsplit("/", 1)[1]
                     for p in _list(f"{KLINES}/", delimiter=True))
    natives = [s for s in natives if s.endswith("USDT")]
    if "--limit" in sys.argv:
        natives = natives[: int(sys.argv[sys.argv.index("--limit") + 1])]
    conn = db.connect()
    db.init_schema(conn)
    have_c, have_f = _stored(conn)
    print(f"Z2: {len(natives)} USDT-M perps in the dump bucket ({time.time() - t0:.0f}s to list)")

    n_c = n_f = 0
    with ThreadPoolExecutor(WORKERS) as pool:
        futures = [pool.submit(_load_symbol, s, have_c, have_f) for s in natives]
        for i, fut in enumerate(futures, 1):
            sym, candles, funding = fut.result()
            _copy_upsert(conn, sym, candles, funding)
            n_c, n_f = n_c + len(candles), n_f + len(funding)
            if i % 50 == 0 or i == len(futures):
                print(f"  {i:>4}/{len(futures)}  {n_c:,} candles  {n_f:,} funding"
                      f"  {time.time() - t0:.0f}s", flush=True)
    print(f"Done: {n_c:,} daily candles, {n_f:,} funding settlements, {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
