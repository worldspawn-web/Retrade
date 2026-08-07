"""Smoke tests for project bootstrap."""

from __future__ import annotations

from retrade import __version__
from retrade.config import Settings, get_settings


def test_version() -> None:
    assert __version__ == "0.1.0"


def test_default_settings() -> None:
    settings = get_settings()
    assert isinstance(settings, Settings)
    assert settings.symbol == "BTCUSDT"
    assert settings.execution_timeframe == "15m"
    assert settings.context_timeframes == ("1h", "4h")
