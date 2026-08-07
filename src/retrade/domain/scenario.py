"""Scenario building: multi-coin + diverse historical windows."""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass

from retrade.domain.candles import Candle, CandleSeries, ensure_non_empty
from retrade.domain.market_data import MarketDataPort
from retrade.domain.round_history import RoundHistory, RoundRecord
from retrade.domain.scenario_score import ScoredDecision, pick_best_decision_index
from retrade.infra.symbol_universe import SymbolUniverse

logger = logging.getLogger(__name__)

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

_DAY_MS = 24 * 60 * 60 * 1000


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
    window_start_ms: int = 0
    window_end_ms: int = 0

    @property
    def entry_price(self) -> float:
        return self.visible_execution.candles[-1].close

    @property
    def cursor_ms(self) -> int:
        return self.visible_execution.candles[-1].close_time

    def series_at_cursor(self, timeframe: str, cursor_ms: int) -> CandleSeries:
        series = self.series_by_tf[timeframe]
        return series.visible_until(cursor_ms)


def pick_symbol(
    universe: SymbolUniverse,
    history: RoundHistory,
    *,
    rng: random.Random | None = None,
) -> str:
    """Pick a random eligible symbol from the top-N universe."""
    rng = rng or random.Random()
    pool = universe.ensure_loaded()
    eligible = history.eligible_symbols(pool)
    return rng.choice(eligible)


def build_scenario(
    market: MarketDataPort,
    *,
    symbol: str,
    execution_timeframe: str,
    context_timeframes: tuple[str, ...],
    history: RoundHistory | None = None,
    limit: int = 1000,
    visible_bars: int = 180,
    hidden_bars: int = 80,
    history_lookback_days: int = 400,
    max_window_attempts: int = 10,
    rng: random.Random | None = None,
) -> RoundScenario:
    """
    Load multi-TF data from a random historical slice, pick an interesting
    decision point that does not overlap prior windows for this symbol.
    """
    rng = rng or random.Random()
    interval_ms = TIMEFRAME_MS[execution_timeframe]
    avoided = _avoided_ranges_for_symbol(history, symbol)

    last_error: Exception | None = None
    for attempt in range(max_window_attempts):
        try:
            end_time = _random_end_time(
                interval_ms=interval_ms,
                limit=limit,
                lookback_days=history_lookback_days,
                rng=rng,
            )
            scenario = _build_from_end_time(
                market,
                symbol=symbol,
                execution_timeframe=execution_timeframe,
                context_timeframes=context_timeframes,
                end_time=end_time,
                limit=limit,
                visible_bars=visible_bars,
                hidden_bars=hidden_bars,
                avoided=avoided,
                rng=rng,
            )
        except Exception as exc:  # noqa: BLE001 - try another window
            last_error = exc
            logger.info(
                "Scenario attempt %s failed for %s: %s",
                attempt + 1,
                symbol,
                exc,
            )
            continue

        if history is not None and history.overlaps_window(
            symbol,
            scenario.window_start_ms,
            scenario.window_end_ms,
        ):
            logger.info(
                "Skipping overlapping window for %s (%s–%s)",
                symbol,
                scenario.window_start_ms,
                scenario.window_end_ms,
            )
            continue

        if history is not None:
            history.record(
                RoundRecord(
                    symbol=symbol,
                    window_start_ms=scenario.window_start_ms,
                    window_end_ms=scenario.window_end_ms,
                    decision_time_ms=scenario.visible_execution.candles[-1].open_time,
                )
            )
        return scenario

    if last_error is not None:
        raise RuntimeError(
            f"Failed to build scenario for {symbol} after "
            f"{max_window_attempts} attempts"
        ) from last_error
    raise RuntimeError(f"Failed to build non-overlapping scenario for {symbol}")


def _build_from_end_time(
    market: MarketDataPort,
    *,
    symbol: str,
    execution_timeframe: str,
    context_timeframes: tuple[str, ...],
    end_time: int,
    limit: int,
    visible_bars: int,
    hidden_bars: int,
    avoided: tuple[tuple[int, int], ...],
    rng: random.Random,
) -> RoundScenario:
    all_tfs = (execution_timeframe, *context_timeframes)
    series_by_tf: dict[str, CandleSeries] = {}
    for tf in all_tfs:
        if tf == execution_timeframe:
            tf_limit = limit
        else:
            tf_limit = min(1000, max(200, limit // 4))
        series_by_tf[tf] = market.get_klines(
            symbol,
            tf,
            limit=tf_limit,
            end_time=end_time,
        )

    execution = series_by_tf[execution_timeframe]
    ensure_non_empty(execution.candles, context=f"{symbol} {execution_timeframe}")

    total = len(execution)
    local_visible = visible_bars
    local_hidden = hidden_bars
    if total < local_visible + 10:
        local_visible = max(50, total // 2)
    local_hidden = min(local_hidden, max(1, total - 40))

    picked: ScoredDecision = pick_best_decision_index(
        execution,
        visible_bars=local_visible,
        hidden_bars=local_hidden,
        avoided_ranges=avoided,
        rng=rng,
    )
    decision_index = picked.index
    decision_index = min(decision_index, total - 8)
    decision_index = max(decision_index, min(local_visible, total - 8))

    start = max(0, decision_index - local_visible)
    visible_slice = execution.candles[start:decision_index]
    hidden = execution.candles[decision_index : decision_index + local_hidden]
    if not hidden:
        hidden = execution.candles[decision_index:]

    ensure_non_empty(visible_slice, context="visible execution")
    ensure_non_empty(hidden, context="hidden execution")

    window_start_ms = visible_slice[0].open_time
    window_end_ms = hidden[-1].close_time
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
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
    )


def _random_end_time(
    *,
    interval_ms: int,
    limit: int,
    lookback_days: int,
    rng: random.Random,
) -> int:
    """
    Pick a random window end so the fetched `limit` bars sit somewhere in the
    past lookback horizon (not always the live tip).
    """
    now_ms = int(time.time() * 1000)
    window_ms = interval_ms * limit
    # Keep a small buffer from "now" so the whole window is closed history.
    latest_end = now_ms - interval_ms * 4
    earliest_end = now_ms - lookback_days * _DAY_MS
    # Ensure earliest still allows a full window of bars on the exchange.
    earliest_end = max(earliest_end, window_ms + _DAY_MS)
    if earliest_end >= latest_end:
        return latest_end
    return rng.randint(int(earliest_end), int(latest_end))


def _avoided_ranges_for_symbol(
    history: RoundHistory | None,
    symbol: str,
) -> tuple[tuple[int, int], ...]:
    if history is None:
        return ()
    symbol = symbol.upper()
    return tuple(
        (r.window_start_ms, r.window_end_ms)
        for r in history.rounds
        if r.symbol == symbol
    )
