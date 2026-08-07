"""Application configuration."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings. Symbol pool is top-N USDT; fallback symbol for tests."""

    model_config = SettingsConfigDict(
        env_prefix="RETRADE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    symbol: str = "BTCUSDT"  # fallback / tests only
    top_symbols: int = 200
    min_quote_volume_usd: float = 5_000_000.0
    symbol_cooldown: int = 10
    history_lookback_days: int = 400
    execution_timeframe: str = "15m"
    context_timeframes: tuple[str, ...] = ("1h", "4h")
    data_dir: Path = Field(default_factory=lambda: Path("data"))
    binance_base_url: str = "https://api.binance.com"
    playback_interval_ms: int = 400


def get_settings() -> Settings:
    """Return application settings instance."""
    return Settings()
