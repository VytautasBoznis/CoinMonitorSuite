from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Project configuration. Override via env vars prefixed ``COINMON_`` or a ``.env`` file."""

    model_config = SettingsConfigDict(env_prefix="COINMON_", env_file=".env", extra="ignore")

    exchange: str = "bybit"
    # Hard constraint: quote currency is USDC, never USDT (unavailable to EU users, MiCA).
    quote_currency: str = "USDC"
    default_timeframe: str = "1h"

    # Bybit spot fees as a fraction of notional. A spot rotation pays taker on BOTH legs.
    taker_fee: float = 0.001
    maker_fee: float = 0.001

    # Root of the local Parquet candle store.
    data_dir: Path = Path("data")

    # --- Scraper (TimescaleDB-backed candle ingest) ---
    # Postgres/Timescale DSN. Secret in k8s; override via COINMON_DB_DSN.
    db_dsn: str = "postgresql://coinmon:coinmon@localhost:5432/coinmon"
    # Series the scraper backfills + polls. JSON lists via env, e.g. COINMON_SYMBOLS='["BTC/USDC"]'.
    symbols: list[str] = ["BTC/USDC", "ETH/USDC"]
    timeframes: list[str] = ["1h"]
    # Seconds between poll cycles once backfill completes.
    poll_interval_seconds: int = 60
    # Earliest bar to backfill (ISO date) when a series has no stored history yet.
    backfill_start: str = "2020-01-01"
    # Chunk T: also scrape perp funding-rate history for the USDC legs in `symbols` (data-only,
    # feeds the W3 carry family). Off by default so existing candle-only deployments are unchanged.
    scrape_funding: bool = False


settings = Settings()
