"""Structure levels and true / false breaks."""

from __future__ import annotations

from retrade.domain.candles import Candle
from retrade.domain.smc.types import (
    Bias,
    BreakEvent,
    BreakKind,
    LevelStrength,
    StructureLevel,
    SwingKind,
    SwingPoint,
)


def build_levels(
    candles: tuple[Candle, ...],
    swings: tuple[SwingPoint, ...],
    *,
    touch_tol_pct: float = 0.0008,
) -> tuple[StructureLevel, ...]:
    """Convert swings into strong/weak levels by retest count."""
    levels: list[StructureLevel] = []
    for swing in swings:
        touches = _count_touches(
            candles,
            price=swing.price,
            start=swing.index + 1,
            tol_pct=touch_tol_pct,
        )
        strength = (
            LevelStrength.STRONG if touches >= 1 else LevelStrength.WEAK
        )
        levels.append(
            StructureLevel(
                price=swing.price,
                kind=swing.kind,
                strength=strength,
                time_sec=swing.time_sec,
                touches=touches,
            )
        )
    return tuple(levels)


def detect_breaks(
    candles: tuple[Candle, ...],
    levels: tuple[StructureLevel, ...],
    *,
    tol_pct: float = 0.0003,
) -> tuple[BreakEvent, ...]:
    """
    True break: close beyond level.
    False break: wick beyond level, close back inside.
    """
    if not levels or len(candles) < 2:
        return ()

    # Prefer recent strong levels, then any recent swings.
    ranked = sorted(
        levels,
        key=lambda lv: (0 if lv.strength is LevelStrength.STRONG else 1, -lv.time_sec),
    )[:12]

    events: list[BreakEvent] = []
    seen: set[tuple[int, float, BreakKind]] = set()

    for level in ranked:
        for i, candle in enumerate(candles):
            if candle.open_time // 1000 < level.time_sec:
                continue
            tol = abs(level.price) * tol_pct
            if level.kind is SwingKind.HIGH:
                wick_beyond = candle.high > level.price + tol
                close_beyond = candle.close > level.price + tol
                close_inside = candle.close < level.price - tol
                if wick_beyond and close_beyond:
                    kind = BreakKind.TRUE
                    bias = Bias.BULLISH
                elif wick_beyond and close_inside:
                    kind = BreakKind.FALSE
                    bias = Bias.BEARISH
                else:
                    continue
            else:
                wick_beyond = candle.low < level.price - tol
                close_beyond = candle.close < level.price - tol
                close_inside = candle.close > level.price + tol
                if wick_beyond and close_beyond:
                    kind = BreakKind.TRUE
                    bias = Bias.BEARISH
                elif wick_beyond and close_inside:
                    kind = BreakKind.FALSE
                    bias = Bias.BULLISH
                else:
                    continue

            key = (i, round(level.price, 2), kind)
            if key in seen:
                continue
            seen.add(key)
            events.append(
                BreakEvent(
                    kind=kind,
                    bias=bias,
                    index=i,
                    level_price=level.price,
                    time_sec=candle.open_time // 1000,
                )
            )
    events.sort(key=lambda e: e.index)
    return tuple(events)


def _count_touches(
    candles: tuple[Candle, ...],
    *,
    price: float,
    start: int,
    tol_pct: float,
) -> int:
    tol = abs(price) * tol_pct
    touches = 0
    for candle in candles[start:]:
        if candle.low - tol <= price <= candle.high + tol:
            touches += 1
    return touches
