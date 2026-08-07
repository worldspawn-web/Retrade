"""Tests for SMC swing / FVG / structure detectors."""

from __future__ import annotations

from retrade.domain.candles import Candle, CandleSeries
from retrade.domain.explanation import build_explanation
from retrade.domain.smc import (
    Bias,
    BreakKind,
    StructureEventKind,
    analyze_series,
)
from retrade.domain.smc.fvg import detect_fvgs
from retrade.domain.smc.swings import detect_swings
from retrade.domain.trading import Side, TradeOutcome, TradePlan


def _c(
    i: int,
    o: float,
    h: float,
    low: float,
    c: float,
) -> Candle:
    open_time = i * 900_000
    return Candle(
        open_time=open_time,
        open=o,
        high=h,
        low=low,
        close=c,
        volume=1.0,
        close_time=open_time + 899_999,
    )


def test_detect_swing_high_and_low() -> None:
    # Flat then peak then trough.
    candles = (
        _c(0, 10, 11, 9, 10),
        _c(1, 10, 12, 9, 11),
        _c(2, 11, 15, 10, 14),  # swing high candidate
        _c(3, 14, 14, 10, 11),
        _c(4, 11, 12, 9, 10),
        _c(5, 10, 11, 7, 8),  # swing low candidate
        _c(6, 8, 10, 8, 9),
        _c(7, 9, 11, 9, 10),
        _c(8, 10, 12, 10, 11),
    )
    swings = detect_swings(candles, strength=2)
    highs = [s for s in swings if s.kind.value == "high"]
    lows = [s for s in swings if s.kind.value == "low"]
    assert any(s.index == 2 for s in highs)
    assert any(s.index == 5 for s in lows)


def test_detect_bullish_fvg() -> None:
    candles = (
        _c(0, 100, 101, 99, 100),
        _c(1, 100, 102, 100, 101),
        _c(2, 110, 112, 109, 111),  # gap above candle 0 high
    )
    # Need left.high < right.low => 101 < 109
    gaps = detect_fvgs(candles)
    assert len(gaps) == 1
    assert gaps[0].bias is Bias.BULLISH
    assert gaps[0].bottom == 101
    assert gaps[0].top == 109


def test_analyze_series_produces_map() -> None:
    candles = []
    price = 100.0
    for i in range(40):
        # Mild uptrend with wiggles.
        drift = 0.4 if i % 5 else -0.2
        o = price
        c = price + drift
        h = max(o, c) + 0.8
        low = min(o, c) - 0.8
        candles.append(_c(i, o, h, low, c))
        price = c
    series = CandleSeries("BTCUSDT", "15m", tuple(candles))
    structure = analyze_series(series, swing_strength=2)
    assert structure.timeframe == "15m"
    assert structure.bias in {Bias.BULLISH, Bias.BEARISH, Bias.RANGE}
    assert isinstance(structure.swings, tuple)


def test_build_explanation_chips_and_overlays() -> None:
    candles = tuple(
        _c(i, 100 + i * 0.2, 101 + i * 0.2, 99 + i * 0.2, 100.5 + i * 0.2)
        for i in range(30)
    )
    series = CandleSeries("BTCUSDT", "15m", candles)
    plan = TradePlan(
        Side.LONG,
        entry=100.5,
        take_profit=106.0,
        stop_loss=98.0,
    )
    explanation = build_explanation(
        execution_series=series,
        context_series=None,
        outcome=TradeOutcome.TAKE_PROFIT,
        plan=plan,
    )
    assert explanation.headline.startswith("TP")
    assert explanation.chips
    assert explanation.overlays["levels"] == []
    assert "markers" in explanation.overlays
    assert "zones" in explanation.overlays


def test_structure_event_kinds_available() -> None:
    assert StructureEventKind.BOS.value == "bos"
    assert BreakKind.FALSE.value == "false"
