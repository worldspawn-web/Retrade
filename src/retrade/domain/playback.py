"""15M-driven playback cursor and higher-TF sync."""

from __future__ import annotations

from dataclasses import dataclass, field

from retrade.domain.candles import Candle, CandleSeries, htf_series_with_partial
from retrade.domain.scenario import TIMEFRAME_MS, RoundScenario
from retrade.domain.trading import TradeOutcome, TradePlan, TradeResult, evaluate_candle


@dataclass
class PlaybackState:
    """Mutable playback progress for an open (or skipped) round."""

    scenario: RoundScenario
    plan: TradePlan | None
    shown_hidden: int = 0
    outcome: TradeOutcome = TradeOutcome.OPEN
    result_candle: Candle | None = None
    finished: bool = False

    @property
    def cursor_ms(self) -> int:
        if self.shown_hidden == 0:
            return self.scenario.cursor_ms
        return self.scenario.hidden_execution[self.shown_hidden - 1].close_time

    @property
    def execution_candles(self) -> tuple[Candle, ...]:
        visible = self.scenario.visible_execution.candles
        revealed = self.scenario.hidden_execution[: self.shown_hidden]
        return visible + revealed

    def series_for(self, timeframe: str) -> CandleSeries:
        if timeframe == self.scenario.execution_timeframe:
            return CandleSeries(
                self.scenario.symbol,
                timeframe,
                self.execution_candles,
            )
        # Rebuild HTF with partial bar from revealed execution candles.
        htf = self.scenario.series_by_tf[timeframe]
        return htf_series_with_partial(
            htf,
            self.execution_candles,
            cursor_ms=self.cursor_ms,
            interval_ms=TIMEFRAME_MS[timeframe],
        )

    def step(self) -> TradeResult | None:
        """Reveal next execution candle; return result when trade resolves."""
        if self.finished:
            return TradeResult(self.outcome, self.result_candle)

        if self.plan is None:
            self.finished = True
            self.outcome = TradeOutcome.SKIP
            return TradeResult(TradeOutcome.SKIP)

        if self.shown_hidden >= len(self.scenario.hidden_execution):
            self.finished = True
            self.outcome = TradeOutcome.OPEN
            return TradeResult(TradeOutcome.OPEN)

        candle = self.scenario.hidden_execution[self.shown_hidden]
        self.shown_hidden += 1
        outcome = evaluate_candle(self.plan, candle)
        if outcome is TradeOutcome.OPEN:
            return None

        self.finished = True
        self.outcome = outcome
        self.result_candle = candle
        return TradeResult(outcome, candle)


@dataclass
class RoundSession:
    """Owns scenario + optional playback after confirm."""

    scenario: RoundScenario
    playback: PlaybackState | None = field(default=None)

    def start_trade(self, plan: TradePlan) -> PlaybackState:
        plan.validate()
        self.playback = PlaybackState(scenario=self.scenario, plan=plan)
        return self.playback

    def start_skip(self) -> PlaybackState:
        self.playback = PlaybackState(scenario=self.scenario, plan=None)
        self.playback.finished = True
        self.playback.outcome = TradeOutcome.SKIP
        return self.playback
