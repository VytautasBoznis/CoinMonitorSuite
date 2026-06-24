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


settings = Settings()
