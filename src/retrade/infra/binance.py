"""Binance public klines client (no API key)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from retrade.domain.candles import Candle, CandleSeries
from retrade.infra.cache import KlineCache

logger = logging.getLogger(__name__)

# Binance interval strings match our timeframe keys.
_SUPPORTED = frozenset(
    {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d"}
)


class BinanceMarketData:
    """MarketDataPort implementation using Binance spot REST + local cache."""

    def __init__(
        self,
        *,
        base_url: str,
        cache: KlineCache,
        timeout_s: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._cache = cache
        self._timeout = timeout_s

    def get_klines(
        self,
        symbol: str,
        timeframe: str,
        *,
        limit: int = 1000,
        end_time: int | None = None,
    ) -> CandleSeries:
        symbol = symbol.upper()
        if timeframe not in _SUPPORTED:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        limit = max(1, min(limit, 1000))

        try:
            remote = self._fetch(
                symbol,
                timeframe,
                limit=limit,
                end_time=end_time,
            )
            # Only merge into rolling cache when fetching the live tip.
            if end_time is None:
                return self._cache.merge_and_save(symbol, timeframe, remote)
            return remote
        except (httpx.HTTPError, OSError, ValueError) as exc:
            logger.warning("Binance fetch failed (%s); trying cache", exc)
            cached = self._cache.load(symbol, timeframe)
            if cached is None or len(cached) == 0:
                raise RuntimeError(
                    f"No market data for {symbol} {timeframe}: {exc}"
                ) from exc
            if end_time is not None:
                candles = tuple(
                    c for c in cached.candles if c.open_time <= end_time
                )[-limit:]
            else:
                candles = cached.candles[-limit:]
            if not candles:
                raise RuntimeError(
                    f"No cached candles for {symbol} {timeframe} at {end_time}"
                ) from exc
            return CandleSeries(symbol, timeframe, candles)

    def _fetch(
        self,
        symbol: str,
        timeframe: str,
        *,
        limit: int,
        end_time: int | None,
    ) -> CandleSeries:
        url = f"{self._base_url}/api/v3/klines"
        params: dict[str, int | str] = {
            "symbol": symbol,
            "interval": timeframe,
            "limit": limit,
        }
        if end_time is not None:
            params["endTime"] = int(end_time)

        with httpx.Client(timeout=self._timeout) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            payload: list[list[Any]] = response.json()

        candles = tuple(_parse_kline(row) for row in payload)
        return CandleSeries(symbol, timeframe, candles)


def _parse_kline(row: list[Any]) -> Candle:
    return Candle(
        open_time=int(row[0]),
        open=float(row[1]),
        high=float(row[2]),
        low=float(row[3]),
        close=float(row[4]),
        volume=float(row[5]),
        close_time=int(row[6]),
    )
