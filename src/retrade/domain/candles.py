"""Candle and multi-timeframe series models."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Candle:
    """Single OHLCV bar. Timestamps are Unix milliseconds (UTC)."""

    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: int

    def to_chart_dict(self) -> dict[str, float | int]:
        """Payload for Lightweight Charts candlestick series."""
        return {
            "time": self.open_time // 1000,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
        }


@dataclass(frozen=True, slots=True)
class CandleSeries:
    """Ordered OHLC series for one symbol and timeframe."""

    symbol: str
    timeframe: str
    candles: tuple[Candle, ...]

    def __len__(self) -> int:
        return len(self.candles)

    def visible_until(self, cursor_ms: int) -> CandleSeries:
        """Return only fully closed candles with close_time <= cursor_ms."""
        closed = tuple(c for c in self.candles if c.close_time <= cursor_ms)
        return CandleSeries(self.symbol, self.timeframe, closed)

    def to_chart_payload(self) -> list[dict[str, float | int]]:
        return [c.to_chart_dict() for c in self.candles]


def merge_unique_by_open_time(candles: Iterable[Candle]) -> tuple[Candle, ...]:
    """Deduplicate by open_time, keep last, sort ascending."""
    by_time: dict[int, Candle] = {c.open_time: c for c in candles}
    return tuple(sorted(by_time.values(), key=lambda c: c.open_time))


def slice_from_index(series: CandleSeries, start: int) -> CandleSeries:
    """Return series starting at index (inclusive)."""
    return CandleSeries(series.symbol, series.timeframe, series.candles[start:])


def slice_until_index(series: CandleSeries, end_exclusive: int) -> CandleSeries:
    """Return series ending before index."""
    return CandleSeries(
        series.symbol,
        series.timeframe,
        series.candles[:end_exclusive],
    )


def ensure_non_empty(candles: Sequence[Candle], *, context: str) -> None:
    if not candles:
        raise ValueError(f"Empty candle series: {context}")
