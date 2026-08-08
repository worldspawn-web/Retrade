"""Nearest-level overlay selection."""

from __future__ import annotations

from retrade.domain.explanation import nearest_levels, structure_to_overlays
from retrade.domain.smc import Bias, LevelStrength, StructureLevel, SwingKind
from retrade.domain.smc.types import StructureMap


def _level(price: float) -> StructureLevel:
    return StructureLevel(
        price=price,
        kind=SwingKind.HIGH,
        strength=LevelStrength.STRONG,
        time_sec=0,
        touches=1,
    )


def test_nearest_levels_picks_two_closest() -> None:
    levels = tuple(_level(p) for p in (90.0, 98.0, 101.0, 120.0))
    picked = nearest_levels(levels, ref_price=100.0, limit=2)
    assert [lv.price for lv in picked] == [101.0, 98.0]


def test_overlays_respect_toggles() -> None:
    empty = StructureMap(
        timeframe="15m",
        bias=Bias.RANGE,
        swings=(),
        events=(),
        fvgs=(),
        levels=(_level(100.0), _level(105.0)),
        breaks=(),
    )
    off = structure_to_overlays(
        empty, show_bos=False, show_fvg=False, show_levels=False, ref_price=100.0
    )
    assert off["markers"] == []
    assert off["zones"] == []
    assert off["levels"] == []

    on = structure_to_overlays(
        empty, show_bos=False, show_fvg=False, show_levels=True, ref_price=100.0
    )
    assert len(on["levels"]) == 2
