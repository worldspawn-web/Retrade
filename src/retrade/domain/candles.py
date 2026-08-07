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


def floor_open_time(timestamp_ms: int, interval_ms: int) -> int:
    """Align timestamp down to timeframe bucket start."""
    return (timestamp_ms // interval_ms) * interval_ms


def htf_series_with_partial(
    htf: CandleSeries,
    execution: Sequence[Candle],
    *,
    cursor_ms: int,
    interval_ms: int,
) -> CandleSeries:
    """
    Closed HTF candles up to cursor, plus an in-progress HTF bar aggregated
    from execution TF so the last close matches the decision/entry price.
    """
    period_start = floor_open_time(
        execution[-1].open_time if execution else cursor_ms,
        interval_ms,
    )
    closed = tuple(
        c
        for c in htf.candles
        if c.close_time <= cursor_ms and c.open_time < period_start
    )
    partial_src = [
        c
        for c in execution
        if c.open_time >= period_start and c.close_time <= cursor_ms
    ]
    if not partial_src:
        return CandleSeries(htf.symbol, htf.timeframe, closed)

    partial = Candle(
        open_time=period_start,
        open=partial_src[0].open,
        high=max(c.high for c in partial_src),
        low=min(c.low for c in partial_src),
        close=partial_src[-1].close,
        volume=sum(c.volume for c in partial_src),
        close_time=partial_src[-1].close_time,
    )
    return CandleSeries(htf.symbol, htf.timeframe, closed + (partial,))
