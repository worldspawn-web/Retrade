"""Scenario building: visible history + hidden playback tail."""

from __future__ import annotations

from dataclasses import dataclass

from retrade.domain.candles import Candle, CandleSeries, ensure_non_empty
from retrade.domain.market_data import MarketDataPort
from retrade.domain.scenario_score import ScoredDecision, pick_best_decision_index

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
    score: float = 0.0
    score_reasons: tuple[str, ...] = ()

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
    Load multi-TF data, pick an interesting decision point, split visible/hidden.
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
    hidden_bars = min(hidden_bars, max(1, total - 40))

    picked: ScoredDecision = pick_best_decision_index(
        execution,
        visible_bars=visible_bars,
        hidden_bars=hidden_bars,
    )
    decision_index = picked.index

    # Clamp so both visible lookback and hidden tail stay usable.
    decision_index = min(decision_index, total - 8)
    decision_index = max(decision_index, min(visible_bars, total - 8))
    # Re-anchor visible window ending at decision.
    start = max(0, decision_index - visible_bars)
    visible_slice = execution.candles[start:decision_index]
    hidden = execution.candles[decision_index : decision_index + hidden_bars]
    if not hidden:
        hidden = execution.candles[decision_index:]

    ensure_non_empty(visible_slice, context="visible execution")
    ensure_non_empty(hidden, context="hidden execution")

    # Trim series_by_tf not required; full history kept for HTF cursor sync.
    visible = CandleSeries(symbol, execution_timeframe, visible_slice)

    return RoundScenario(
        symbol=symbol,
        execution_timeframe=execution_timeframe,
        series_by_tf=series_by_tf,
        decision_index=decision_index,
        visible_execution=visible,
        hidden_execution=hidden,
        score=picked.score,
        score_reasons=picked.reasons,
    )
