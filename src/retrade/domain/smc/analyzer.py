"""Orchestrate SMC detectors into a StructureMap."""

from __future__ import annotations

from retrade.domain.candles import CandleSeries
from retrade.domain.smc.fvg import detect_fvgs
from retrade.domain.smc.levels import build_levels, detect_breaks
from retrade.domain.smc.structure import detect_structure_events, infer_bias
from retrade.domain.smc.swings import detect_swings
from retrade.domain.smc.types import StructureMap


def analyze_series(
    series: CandleSeries,
    *,
    swing_strength: int = 2,
) -> StructureMap:
    """Run MVP SMC pipeline on a candle series."""
    candles = series.candles
    swings = detect_swings(candles, strength=swing_strength)
    events = detect_structure_events(candles, swings)
    fvgs = detect_fvgs(candles)
    levels = build_levels(candles, swings)
    breaks = detect_breaks(candles, levels)
    bias = infer_bias(events, swings)
    return StructureMap(
        timeframe=series.timeframe,
        bias=bias,
        swings=swings,
        events=events,
        fvgs=fvgs,
        levels=levels,
        breaks=breaks,
    )
