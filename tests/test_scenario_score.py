"""Tests for interesting decision-point scoring."""

from __future__ import annotations

import random

from retrade.domain.candles import Candle, CandleSeries
from retrade.domain.scenario_score import pick_best_decision_index, score_decision_point


def _c(i: int, o: float, h: float, low: float, c: float) -> Candle:
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


def _trending_series(n: int = 120) -> CandleSeries:
    candles: list[Candle] = []
    price = 100.0
    for i in range(n):
        drift = 0.35 if i % 7 else -0.15
        o = price
        c = price + drift
        candles.append(_c(i, o, max(o, c) + 0.9, min(o, c) - 0.9, c))
        price = c
    return CandleSeries("BTCUSDT", "15m", tuple(candles))


def test_score_decision_point_returns_finite() -> None:
    series = _trending_series()
    scored = score_decision_point(series, 80)
    assert scored.index == 80
    assert scored.score == scored.score  # not NaN


def test_pick_best_prefers_nonzero_when_structure_exists() -> None:
    series = _trending_series()
    best = pick_best_decision_index(
        series,
        visible_bars=60,
        hidden_bars=30,
        candidates=20,
        rng=random.Random(42),
    )
    assert 40 <= best.index <= len(series) - 8
    assert isinstance(best.reasons, tuple)
