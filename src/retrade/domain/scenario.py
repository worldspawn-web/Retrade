"""Scenario building: visible history + hidden playback tail."""

from __future__ import annotations

from dataclasses import dataclass

from retrade.domain.candles import Candle, CandleSeries, ensure_non_empty
from retrade.domain.market_data import MarketDataPort

TIMEFRAME_MS: dict[str, int] = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}


@dataclass(frozen=True, slots=True)
class RoundScenario:
    """One training round for a single symbol across multiple timeframes."""

    symbol: str
    execution_timeframe: str
    series_by_tf: dict[str, CandleSeries]
    decision_index: int
    visible_execution: CandleSeries
    hidden_execution: tuple[Candle, ...]

    @property
    def entry_price(self) -> float:
        return self.visible_execution.candles[-1].close

    @property
    def cursor_ms(self) -> int:
        return self.visible_execution.candles[-1].close_time

    def series_at_cursor(self, timeframe: str, cursor_ms: int) -> CandleSeries:
        series = self.series_by_tf[timeframe]
        return series.visible_until(cursor_ms)


def build_scenario(
    market: MarketDataPort,
    *,
    symbol: str,
    execution_timeframe: str,
    context_timeframes: tuple[str, ...],
    limit: int = 500,
    visible_bars: int = 180,
    hidden_bars: int = 80,
) -> RoundScenario:
    """
    Load multi-TF data and split execution series into visible / hidden.

    Decision point is placed so that there is a playback tail of `hidden_bars`.
    """
    all_tfs = (execution_timeframe, *context_timeframes)
    series_by_tf: dict[str, CandleSeries] = {
        tf: market.get_klines(symbol, tf, limit=limit) for tf in all_tfs
    }
    execution = series_by_tf[execution_timeframe]
    ensure_non_empty(execution.candles, context=f"{symbol} {execution_timeframe}")

    total = len(execution)
    if total < visible_bars + 10:
        visible_bars = max(50, total // 2)
    hidden_bars = min(hidden_bars, max(1, total - visible_bars))
    decision_index = total - hidden_bars
    if decision_index < 30:
        decision_index = max(30, total // 2)
        hidden_bars = total - decision_index

    visible = CandleSeries(
        symbol,
        execution_timeframe,
        execution.candles[:decision_index],
    )
    hidden = execution.candles[decision_index:]
    ensure_non_empty(visible.candles, context="visible execution")

    return RoundScenario(
        symbol=symbol,
        execution_timeframe=execution_timeframe,
        series_by_tf=series_by_tf,
        decision_index=decision_index,
        visible_execution=visible,
        hidden_execution=hidden,
    )
