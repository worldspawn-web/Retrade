"""SMC annotation data types."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SwingKind(StrEnum):
    HIGH = "high"
    LOW = "low"


class StructureEventKind(StrEnum):
    BOS = "bos"
    CHOCH = "choch"


class Bias(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    RANGE = "range"


class LevelStrength(StrEnum):
    STRONG = "strong"
    WEAK = "weak"


class BreakKind(StrEnum):
    TRUE = "true"
    FALSE = "false"


@dataclass(frozen=True, slots=True)
class SwingPoint:
    index: int
    kind: SwingKind
    price: float
    time_sec: int


@dataclass(frozen=True, slots=True)
class StructureEvent:
    kind: StructureEventKind
    bias: Bias
    index: int
    price: float
    time_sec: int
    broken_swing_index: int


@dataclass(frozen=True, slots=True)
class FairValueGap:
    index: int
    bias: Bias
    top: float
    bottom: float
    time_from_sec: int
    time_to_sec: int
    mitigated: bool


@dataclass(frozen=True, slots=True)
class StructureLevel:
    price: float
    kind: SwingKind
    strength: LevelStrength
    time_sec: int
    touches: int


@dataclass(frozen=True, slots=True)
class BreakEvent:
    kind: BreakKind
    bias: Bias
    index: int
    level_price: float
    time_sec: int


@dataclass(frozen=True, slots=True)
class StructureMap:
    """Full SMC map for one candle series."""

    timeframe: str
    bias: Bias
    swings: tuple[SwingPoint, ...]
    events: tuple[StructureEvent, ...]
    fvgs: tuple[FairValueGap, ...]
    levels: tuple[StructureLevel, ...]
    breaks: tuple[BreakEvent, ...]
