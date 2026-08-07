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
        end_time: int | None = None,
    ) -> CandleSeries:
        """Return up to `limit` candles ending at end_time (or latest), oldest first."""
        ...
