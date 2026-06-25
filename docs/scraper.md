# Scraper — what's built + lessons learned

A standalone, containerized service that pulls OHLCV candles from an exchange and stores
both the **raw** exchange payload and the **preprocessed** candles into PostgreSQL/TimescaleDB.
Exchange-agnostic via an adapter seam; Bybit is the implemented venue.

---

## What's built

```
fetch_raw (one page) ──► insert_raw   (raw_candles, JSONB archive, verbatim)
        │
        └─► to_candles ──► upsert_candles (candles hypertable, normalized, idempotent)
```

| Piece | File | Role |
|-------|------|------|
| Adapter seam | [src/coinmon/data/adapters/base.py](../src/coinmon/data/adapters/base.py) | `ExchangeAdapter` ABC: `market_symbol` / `fetch_raw` → `RawBatch` / `to_candles`; base `fetch_ohlcv` pages over `fetch_raw`. Shared `timeframe_to_ms`, `validate_continuity`. |
| Bybit impl | [src/coinmon/data/adapters/bybit.py](../src/coinmon/data/adapters/bybit.py) | ccxt spot fetch, normalization, drops in-progress bar, gap-rejects. |
| Schema | [src/coinmon/data/schema.sql](../src/coinmon/data/schema.sql) | `candles` hypertable (PK `exchange,symbol,timeframe,open_time`) + append-only `raw_candles` JSONB. Idempotent. |
| DB layer | [src/coinmon/data/db.py](../src/coinmon/data/db.py) | `connect`, `init_schema`, `insert_raw`, `upsert_candles`, `last_open_time`. Raw `psycopg`, no ORM. |
| Service | [src/coinmon/scraper/service.py](../src/coinmon/scraper/service.py) | `ingest_series` (cursor-driven), `poll_once`, `run` (SIGTERM-aware loop). |
| Entrypoint | [src/coinmon/scraper/__main__.py](../src/coinmon/scraper/__main__.py) | `python -m coinmon.scraper`. |
| Image | [Dockerfile.scraper](../Dockerfile.scraper) | Multi-stage slim image, env-driven config. |
| Local stack | [docker-compose.yml](../docker-compose.yml) | TimescaleDB + scraper for end-to-end runs. |
| Adapter guide | [src/coinmon/data/adapters/README.md](../src/coinmon/data/adapters/README.md) | How to bootstrap a new venue from the contract alone. |
| Tests | [tests/test_scraper.py](../tests/test_scraper.py) | Normalization, gap rejection, paged backfill + idempotent re-poll. Offline. |

**Config** (env, `COINMON_` prefix → k8s ConfigMap/Secret): `db_dsn`, `symbols`,
`timeframes`, `poll_interval_seconds`, `backfill_start`. See
[config.py](../src/coinmon/config.py).

## How to run

```bash
# Full end-to-end (DB + scraper):
docker compose up --build

# Code on host, DB in a container (day-to-day loop):
docker compose up -d timescaledb
COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5432/coinmon \
  .venv/Scripts/python -m coinmon.scraper

# Verify:
#   SELECT count(*) FROM candles;       -- grows
#   SELECT count(*) FROM raw_candles;   -- matching payloads
```

Tests + lint (offline, no DB/network): `pytest -q` and `ruff check .`.

---

## Lessons learned / key decisions

- **Raw + preprocessed are separate tables, on purpose.** `raw_candles` archives the exchange
  payload *verbatim* (provenance/replay); `candles` is the clean query surface. Carried over
  from the .NET prototype's `SaveRawTickerData` / `SaveSanitizedDate` split.

- **Backfill and polling are one code path.** `ingest_series` pulls from the last stored bar
  (or `backfill_start` if empty) up to now. Empty series → it backfills; current series → it
  adds the few new bars. No separate "backfill mode" to drift out of sync with "poll mode".

- **`BACKFILL_START` only bites on an empty series.** Once a symbol has rows, the cursor
  resumes from the last stored bar and `BACKFILL_START` is ignored — changing it later does
  **not** retroactively fetch older history. Set it (low) *before* the first run for full
  history; it's also floored by what the exchange actually has.

- **Closed bars only.** `to_candles` drops the in-progress bar using `RawBatch.fetched_at`
  (`open_time + step <= fetched_at`). Storing a forming bar would poison no-lookahead
  discipline downstream. Upsert means a corrected bar would overwrite cleanly anyway.

- **Idempotency end to end.** `upsert_candles` is `ON CONFLICT DO UPDATE`; re-polling the same
  range produces no dupes. `init_schema` is `IF NOT EXISTS` everywhere — safe on every boot.

- **No migration system — by choice (a stopgap).** Schema is one idempotent `schema.sql` run at
  startup. It does *first-time creation only*: it will **not** alter an existing table (add a
  column, change a type). Fine while the schema is one churning table pair; when it evolves
  against data we care about, add a lightweight numbered-SQL runner + `schema_migrations` table
  (preferred over Alembic, to stay ORM-free).

- **Use the Timescale container, not a bare local Postgres.** The schema needs the `timescaledb`
  extension + `create_hypertable`; a stock Postgres install won't have it. The compose image
  ships it and matches the k8s deployment target.

- **The seam is the whole point.** Adding a venue = one `ExchangeAdapter` subclass; `db.py`,
  `service.py`, `schema.sql` need zero changes. Same contract a live feed will implement, so the
  scraper and a future live executor stay interchangeable.

## Known limitations / follow-ups

- **Backtester still reads Parquet** ([data/store.py](../src/coinmon/data/store.py)); wiring its
  reads to the `candles` table is a deliberate later step.
- **Sequential, single-threaded** symbol/timeframe ingest; no rate-limit backoff beyond ccxt's
  built-in. Revisit if poll latency grows with many series.
- **No migrations / no retention policy** on `raw_candles` (it grows unbounded) — add when needed.
- **Live fetch + real-DB integration are unverified in CI** (gated/offline tests only); confirm
  via `docker compose up`.
