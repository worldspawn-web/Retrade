"""Unit tests for TP/SL hit detection."""

from __future__ import annotations

import pytest

from retrade.domain.candles import Candle
from retrade.domain.trading import (
    Side,
    TradeOutcome,
    TradePlan,
    default_plan,
    evaluate_candle,
)


def _candle(low: float, high: float, *, o: float = 100.0, c: float = 100.0) -> Candle:
    return Candle(
        open_time=0,
        open=o,
        high=high,
        low=low,
        close=c,
        volume=1.0,
        close_time=900_000,
    )


def test_long_take_profit() -> None:
    plan = TradePlan(Side.LONG, entry=100.0, take_profit=110.0, stop_loss=95.0)
    assert evaluate_candle(plan, _candle(99.0, 111.0)) is TradeOutcome.TAKE_PROFIT


def test_long_stop_loss() -> None:
    plan = TradePlan(Side.LONG, entry=100.0, take_profit=110.0, stop_loss=95.0)
    assert evaluate_candle(plan, _candle(94.0, 101.0)) is TradeOutcome.STOP_LOSS


def test_long_ambiguous_is_draw() -> None:
    plan = TradePlan(Side.LONG, entry=100.0, take_profit=110.0, stop_loss=95.0)
    assert evaluate_candle(plan, _candle(94.0, 111.0)) is TradeOutcome.AMBIGUOUS


def test_short_outcomes() -> None:
    plan = TradePlan(Side.SHORT, entry=100.0, take_profit=90.0, stop_loss=105.0)
    assert evaluate_candle(plan, _candle(89.0, 101.0)) is TradeOutcome.TAKE_PROFIT
    assert evaluate_candle(plan, _candle(99.0, 106.0)) is TradeOutcome.STOP_LOSS
    assert evaluate_candle(plan, _candle(89.0, 106.0)) is TradeOutcome.AMBIGUOUS
    assert evaluate_candle(plan, _candle(98.0, 102.0)) is TradeOutcome.OPEN


def test_default_plan_long_rr() -> None:
    plan = default_plan(Side.LONG, 100.0, risk_pct=0.01)
    assert plan.stop_loss == pytest.approx(99.0)
    assert plan.take_profit == pytest.approx(102.0)
    plan.validate()


def test_invalid_plan_raises() -> None:
    plan = TradePlan(Side.LONG, entry=100.0, take_profit=90.0, stop_loss=95.0)
    with pytest.raises(ValueError):
        plan.validate()
