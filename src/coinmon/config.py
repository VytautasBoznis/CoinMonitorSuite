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

    # --- Live bot (F8 cascade ladder on Hyperliquid perps) ---
    # Testnet until the owner flips it. hl_address is the master wallet that owns the funds and is
    # the only signer that can withdraw; hl_agent_key is an approved API wallet's private key, used
    # only to sign orders. Both go in .env, never in the repo.
    hl_testnet: bool = True
    hl_address: str = ""
    hl_agent_key: str = ""
    # USDC notional per ladder rung (Hyperliquid's minimum order is $10). Leverage is not set here:
    # the bot reads and logs whatever isolated leverage the owner set per coin on the venue.
    bot_rung_usd: float = 12.0

    # --- Live-bot dashboard (`coinmon dashboard`) ---
    # The built web frontend (`npm run build` in web/). The API runs without it.
    dashboard_dist: Path = Path("web/dist")


settings = Settings()
