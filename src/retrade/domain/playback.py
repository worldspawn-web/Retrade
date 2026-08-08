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
    hold_anchor: int = 0
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

    @property
    def can_reveal_more(self) -> bool:
        return self.shown_hidden < len(self.scenario.hidden_execution)

    def series_for(self, timeframe: str) -> CandleSeries:
        if timeframe == self.scenario.execution_timeframe:
            return CandleSeries(
                self.scenario.symbol,
                timeframe,
                self.execution_candles,
            )
        htf = self.scenario.series_by_tf[timeframe]
        return htf_series_with_partial(
            htf,
            self.execution_candles,
            cursor_ms=self.cursor_ms,
            interval_ms=TIMEFRAME_MS[timeframe],
        )

    def step(self, *, hold_check_bars: int = 32) -> TradeResult | None:
        """Reveal next execution candle; return result when trade resolves or HOLD."""
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
        if outcome is not TradeOutcome.OPEN:
            self.finished = True
            self.outcome = outcome
            self.result_candle = candle
            return TradeResult(outcome, candle)

        progress = self.shown_hidden - self.hold_anchor
        if hold_check_bars > 0 and progress > 0 and progress % hold_check_bars == 0:
            return TradeResult(TradeOutcome.OPEN, candle, hold=True)
        return None

    def exit_at_market(self) -> TradeResult:
        """Close at the last revealed candle close (manual EXIT)."""
        if self.finished:
            return TradeResult(self.outcome, self.result_candle)
        if self.plan is None or self.shown_hidden <= 0:
            self.finished = True
            self.outcome = TradeOutcome.EXIT
            return TradeResult(TradeOutcome.EXIT)

        candle = self.scenario.hidden_execution[self.shown_hidden - 1]
        self.finished = True
        self.outcome = TradeOutcome.EXIT
        self.result_candle = candle
        return TradeResult(TradeOutcome.EXIT, candle)

    def continue_after_hold(self) -> None:
        """Resume after KEEP — no state change; next step continues the tail."""

    def reveal_only(self) -> Candle | None:
        """Post-result: reveal one more bar without re-scoring TP/SL."""
        if not self.can_reveal_more:
            return None
        candle = self.scenario.hidden_execution[self.shown_hidden]
        self.shown_hidden += 1
        return candle


@dataclass
class RoundSession:
    """Owns scenario + shared reveal cursor (pre-trade and playback)."""

    scenario: RoundScenario
    playback: PlaybackState | None = field(default=None)
    revealed: int = 0

    @property
    def can_advance(self) -> bool:
        return self.revealed < len(self.scenario.hidden_execution)

    @property
    def entry_price(self) -> float:
        return self.execution_candles[-1].close

    @property
    def cursor_ms(self) -> int:
        if self.revealed == 0:
            return self.scenario.cursor_ms
        return self.scenario.hidden_execution[self.revealed - 1].close_time

    @property
    def execution_candles(self) -> tuple[Candle, ...]:
        return (
            self.scenario.visible_execution.candles
            + self.scenario.hidden_execution[: self.revealed]
        )

    def series_for(self, timeframe: str) -> CandleSeries:
        if timeframe == self.scenario.execution_timeframe:
            return CandleSeries(
                self.scenario.symbol,
                timeframe,
                self.execution_candles,
            )
        htf = self.scenario.series_by_tf[timeframe]
        return htf_series_with_partial(
            htf,
            self.execution_candles,
            cursor_ms=self.cursor_ms,
            interval_ms=TIMEFRAME_MS[timeframe],
        )

    def advance_one(self) -> Candle | None:
        """Pre-trade: reveal one more execution candle."""
        if not self.can_advance:
            return None
        candle = self.scenario.hidden_execution[self.revealed]
        self.revealed += 1
        return candle

    def start_trade(self, plan: TradePlan) -> PlaybackState:
        plan.validate()
        self.playback = PlaybackState(
            scenario=self.scenario,
            plan=plan,
            shown_hidden=self.revealed,
            hold_anchor=self.revealed,
        )
        return self.playback

    def start_skip(self) -> PlaybackState:
        self.playback = PlaybackState(
            scenario=self.scenario,
            plan=None,
            shown_hidden=self.revealed,
            hold_anchor=self.revealed,
        )
        self.playback.finished = True
        self.playback.outcome = TradeOutcome.SKIP
        return self.playback

    def sync_revealed_from_playback(self) -> None:
        if self.playback is not None:
            self.revealed = self.playback.shown_hidden
