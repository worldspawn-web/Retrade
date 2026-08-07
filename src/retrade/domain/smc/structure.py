"""BOS / CHoCH from swing structure."""

from __future__ import annotations

from retrade.domain.candles import Candle
from retrade.domain.smc.types import (
    Bias,
    StructureEvent,
    StructureEventKind,
    SwingKind,
    SwingPoint,
)


def detect_structure_events(
    candles: tuple[Candle, ...],
    swings: tuple[SwingPoint, ...],
) -> tuple[StructureEvent, ...]:
    """
    Walk bars in order. Maintain last confirmed swing high/low.

    Each swing level arms once; after a close-break it is consumed until a
    newer swing of the same kind appears (avoids duplicate BOS spam).
    """
    if len(candles) < 5 or len(swings) < 2:
        return ()

    bias = _initial_bias(swings)
    last_high = _last_of_kind(swings, SwingKind.HIGH, before=swings[1].index + 1)
    last_low = _last_of_kind(swings, SwingKind.LOW, before=swings[1].index + 1)
    if last_high is None or last_low is None:
        return ()

    swing_by_index = {s.index: s for s in swings}
    events: list[StructureEvent] = []
    start_i = max(last_high.index, last_low.index) + 1
    high_armed = True
    low_armed = True

    for i in range(start_i, len(candles)):
        if i in swing_by_index:
            swing = swing_by_index[i]
            if swing.kind is SwingKind.HIGH:
                last_high = swing
                high_armed = True
            else:
                last_low = swing
                low_armed = True

        candle = candles[i]
        time_sec = candle.open_time // 1000

        if high_armed and candle.close > last_high.price:
            kind = (
                StructureEventKind.BOS
                if bias is Bias.BULLISH
                else StructureEventKind.CHOCH
            )
            events.append(
                StructureEvent(
                    kind=kind,
                    bias=Bias.BULLISH,
                    index=i,
                    price=last_high.price,
                    time_sec=time_sec,
                    broken_swing_index=last_high.index,
                )
            )
            bias = Bias.BULLISH
            high_armed = False

        if low_armed and candle.close < last_low.price:
            kind = (
                StructureEventKind.BOS
                if bias is Bias.BEARISH
                else StructureEventKind.CHOCH
            )
            events.append(
                StructureEvent(
                    kind=kind,
                    bias=Bias.BEARISH,
                    index=i,
                    price=last_low.price,
                    time_sec=time_sec,
                    broken_swing_index=last_low.index,
                )
            )
            bias = Bias.BEARISH
            low_armed = False

    return tuple(events)


def infer_bias(
    events: tuple[StructureEvent, ...],
    swings: tuple[SwingPoint, ...],
) -> Bias:
    """Latest structural bias; fall back to swing geometry."""
    if events:
        return events[-1].bias
    return _initial_bias(swings)


def _initial_bias(swings: tuple[SwingPoint, ...]) -> Bias:
    highs = [s for s in swings if s.kind is SwingKind.HIGH]
    lows = [s for s in swings if s.kind is SwingKind.LOW]
    if len(highs) >= 2 and len(lows) >= 2:
        hh = highs[-1].price > highs[-2].price
        hl = lows[-1].price > lows[-2].price
        lh = highs[-1].price < highs[-2].price
        ll = lows[-1].price < lows[-2].price
        if hh and hl:
            return Bias.BULLISH
        if lh and ll:
            return Bias.BEARISH
    return Bias.RANGE


def _last_of_kind(
    swings: tuple[SwingPoint, ...],
    kind: SwingKind,
    *,
    before: int,
) -> SwingPoint | None:
    found: SwingPoint | None = None
    for swing in swings:
        if swing.index >= before:
            break
        if swing.kind is kind:
            found = swing
    return found
