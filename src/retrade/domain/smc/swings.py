"""Swing high / swing low detection."""

from __future__ import annotations

from retrade.domain.candles import Candle
from retrade.domain.smc.types import SwingKind, SwingPoint


def detect_swings(
    candles: tuple[Candle, ...],
    *,
    strength: int = 2,
) -> tuple[SwingPoint, ...]:
    """
    Fractal swings: bar i is a swing if its extreme is strict max/min
    over [i - strength, i + strength].
    """
    if strength < 1:
        raise ValueError("strength must be >= 1")
    n = len(candles)
    if n < strength * 2 + 1:
        return ()

    swings: list[SwingPoint] = []
    for i in range(strength, n - strength):
        window = candles[i - strength : i + strength + 1]
        hi = candles[i].high
        lo = candles[i].low
        is_high = all(hi > c.high for j, c in enumerate(window) if j != strength)
        is_low = all(lo < c.low for j, c in enumerate(window) if j != strength)
        time_sec = candles[i].open_time // 1000
        if is_high:
            swings.append(
                SwingPoint(i, SwingKind.HIGH, hi, time_sec),
            )
        if is_low:
            swings.append(
                SwingPoint(i, SwingKind.LOW, lo, time_sec),
            )

    swings.sort(key=lambda s: (s.index, 0 if s.kind is SwingKind.HIGH else 1))
    return tuple(swings)
