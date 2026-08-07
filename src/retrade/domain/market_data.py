"""Market data port (exchange-agnostic)."""

from __future__ import annotations

from typing import Protocol

from retrade.domain.candles import CandleSeries


class MarketDataPort(Protocol):
    """Fetch OHLCV for a symbol/timeframe. Symbol is parameterized for multi-coin."""

    def get_klines(
        self,
        symbol: str,
        timeframe: str,
        *,
        limit: int = 1000,
    ) -> CandleSeries:
        """Return up to `limit` most recent candles, oldest first."""
        ...
