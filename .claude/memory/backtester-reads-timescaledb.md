---
name: backtester-reads-timescaledb
description: Backtester loads candles from TimescaleDB (db.read_candles), not Parquet; the store.py Parquet path is retired
metadata:
  type: project
---

Decision (2026-06-25): the backtest CLI (`coinmon backtest`) loads candles from **TimescaleDB** via `db.read_candles(conn, exchange, symbol, timeframe)` — the same reader the scraper/viewer use. The `data/store.py` **Parquet** path (`read_candles`/`write_candles`, the old "build step 2") is **retired**, and the `fetch-data` CLI command is retired with it (ingestion is the scraper service writing to Timescale).

**Why:** PROJECT_BRIEF.md says candles "persist to Parquet", but the actually-built-and-committed scraper writes to TimescaleDB and already had a working `db.read_candles`. Real data lives in Timescale; building the Parquet store would duplicate ingestion to a second, empty format. User chose Timescale to make the backtester runnable on real data immediately and fits [[deployment-target-k8s]].

**How to apply:**
- `cli._load_candles(read, symbol)` takes a `symbol -> frame` loader (so it's unit-testable without a DB); the CLI passes a lambda over `db.read_candles`. USDC pair → direct read; other pair → two USDC legs through `build_ratio` (the [[feature-store-seam]] / ratio thesis path).
- A real end-to-end run needs the scraper stack up (`docker-compose up`) to populate Timescale — the `coinmon`/`coinmon` role+db must exist. Otherwise the CLI exits with "no candles stored … run the scraper first".
- `store.py` is now orphaned/dead code — fine to delete when convenient; left in place for now (surgical-changes rule).
