"""Fair Value Gap / imbalance detection."""

from __future__ import annotations

from retrade.domain.candles import Candle
from retrade.domain.smc.types import Bias, FairValueGap


def detect_fvgs(
    candles: tuple[Candle, ...],
    *,
    look_ahead: int = 40,
) -> tuple[FairValueGap, ...]:
    """
    Classic 3-candle FVG:
    - bullish: candle[i-2].high < candle[i].low
    - bearish: candle[i-2].low > candle[i].high
    """
    if len(candles) < 3:
        return ()

    gaps: list[FairValueGap] = []
    for i in range(2, len(candles)):
        left = candles[i - 2]
        right = candles[i]
        if left.high < right.low:
            top = right.low
            bottom = left.high
            mitigated = _is_mitigated(
                candles,
                start=i + 1,
                top=top,
                bottom=bottom,
                bullish=True,
                look_ahead=look_ahead,
            )
            gaps.append(
                FairValueGap(
                    index=i,
                    bias=Bias.BULLISH,
                    top=top,
                    bottom=bottom,
                    time_from_sec=left.open_time // 1000,
                    time_to_sec=right.open_time // 1000,
                    mitigated=mitigated,
                )
            )
        elif left.low > right.high:
            top = left.low
            bottom = right.high
            mitigated = _is_mitigated(
                candles,
                start=i + 1,
                top=top,
                bottom=bottom,
                bullish=False,
                look_ahead=look_ahead,
            )
            gaps.append(
                FairValueGap(
                    index=i,
                    bias=Bias.BEARISH,
                    top=top,
                    bottom=bottom,
                    time_from_sec=left.open_time // 1000,
                    time_to_sec=right.open_time // 1000,
                    mitigated=mitigated,
                )
            )
    return tuple(gaps)


def _is_mitigated(
    candles: tuple[Candle, ...],
    *,
    start: int,
    top: float,
    bottom: float,
    bullish: bool,
    look_ahead: int,
) -> bool:
    end = min(len(candles), start + look_ahead)
    for candle in candles[start:end]:
        if bullish and candle.low <= bottom:
            return True
        if not bullish and candle.high >= top:
            return True
    return False
