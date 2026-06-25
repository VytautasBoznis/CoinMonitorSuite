# Viewer — historic candle inspection

A small Streamlit + Plotly app to eyeball the scraped OHLCV history in TimescaleDB.
Symbol + timeframe dropdowns, an interactive candlestick (zoom/pan), and a bar-count /
date-range caption. A dev/inspection tool — **not** the eventual control-plane UI.

---

## What's built

| Piece | File | Role |
|-------|------|------|
| App | [src/coinmon/viewer/app.py](../src/coinmon/viewer/app.py) | Streamlit UI: dropdowns from `list_series`, Plotly candlestick from `read_candles`. |
| DB reads | [src/coinmon/data/db.py](../src/coinmon/data/db.py) | `list_series` (distinct exchange/symbol/timeframe) + `read_candles` (one series → OHLCV frame). |
| Image | [Dockerfile.viewer](../Dockerfile.viewer) | Multi-stage slim image (mirrors the scraper), installs the `viewer` extras, serves Streamlit on `0.0.0.0:8501`. |
| Local stack | [docker-compose.yml](../docker-compose.yml) | `viewer` service, publishes 8501, in-network DSN. |
| Deps | [pyproject.toml](../pyproject.toml) | `viewer` optional group: `streamlit`, `plotly`. |

**Config** (env, `COINMON_` prefix): `db_dsn`. See [config.py](../src/coinmon/config.py).

## How to run

```bash
# Full stack (DB + viewer), then open http://localhost:8501
docker compose up -d --build viewer

# Code on host, DB in a container — NOTE the 5433 host port (see below):
pip install -e ".[viewer]"
COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
  streamlit run src/coinmon/viewer/app.py
```

---

## Key notes / limitations

- **Host runs need port 5433, compose runs use 5432.** The compose TimescaleDB is published
  on host **5433** (a native Postgres holds 5432 on this machine — see
  [docker-compose.yml](../docker-compose.yml)). A host-side `streamlit run` must point its DSN
  at `localhost:5433`; the `viewer` *container* reaches the DB over the compose network at
  `timescaledb:5432`, so the remap doesn't apply there. (In k8s, neither applies — use the
  in-cluster Service DSN.)

- **Loads the full series into one frame.** Fine for the current 1h history. Years of 1m bars
  would make it heavy — add a date-range filter then, not before.

- **No auth.** Published on 8501 with no access control — acceptable for local dev only. For the
  cluster, put it behind the ingress/auth rather than exposing the port directly.

- **Unverified end-to-end in CI.** No tests cover the UI; confirm via `docker compose up`.
