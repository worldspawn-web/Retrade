"""Trade side, orders and hit detection on execution timeframe."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from retrade.domain.candles import Candle


class Side(StrEnum):
    LONG = "long"
    SHORT = "short"


class TradeOutcome(StrEnum):
    TAKE_PROFIT = "tp"
    STOP_LOSS = "sl"
    AMBIGUOUS = "ambiguous"
    SKIP = "skip"
    OPEN = "open"


@dataclass(frozen=True, slots=True)
class TradePlan:
    side: Side
    entry: float
    take_profit: float
    stop_loss: float

    def validate(self) -> None:
        if self.side is Side.LONG:
            if not (self.stop_loss < self.entry < self.take_profit):
                raise ValueError("LONG requires SL < entry < TP")
        elif not (self.take_profit < self.entry < self.stop_loss):
            raise ValueError("SHORT requires TP < entry < SL")


@dataclass(frozen=True, slots=True)
class TradeResult:
    outcome: TradeOutcome
    candle: Candle | None = None


def evaluate_candle(plan: TradePlan, candle: Candle) -> TradeOutcome:
    """
    Evaluate TP/SL against one execution-TF candle.

    If both levels are touched in the same bar -> AMBIGUOUS (draw).
    """
    plan.validate()
    if plan.side is Side.LONG:
        hit_sl = candle.low <= plan.stop_loss
        hit_tp = candle.high >= plan.take_profit
    else:
        hit_sl = candle.high >= plan.stop_loss
        hit_tp = candle.low <= plan.take_profit

    if hit_sl and hit_tp:
        return TradeOutcome.AMBIGUOUS
    if hit_tp:
        return TradeOutcome.TAKE_PROFIT
    if hit_sl:
        return TradeOutcome.STOP_LOSS
    return TradeOutcome.OPEN


def default_plan(side: Side, entry: float, *, risk_pct: float = 0.005) -> TradePlan:
    """Build a simple 1R / 2R plan around entry."""
    risk = entry * risk_pct
    if side is Side.LONG:
        return TradePlan(
            side=side,
            entry=entry,
            stop_loss=entry - risk,
            take_profit=entry + 2 * risk,
        )
    return TradePlan(
        side=side,
        entry=entry,
        stop_loss=entry + risk,
        take_profit=entry - 2 * risk,
    )
