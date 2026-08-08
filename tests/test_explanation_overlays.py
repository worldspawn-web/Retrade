"""Nearest-level, swing and BOS overlay selection."""

from __future__ import annotations

from retrade.domain.explanation import nearest_levels, structure_to_overlays
from retrade.domain.smc import (
    Bias,
    LevelStrength,
    StructureEvent,
    StructureEventKind,
    StructureLevel,
    SwingKind,
    SwingPoint,
)
from retrade.domain.smc.types import StructureMap
from retrade.domain.ui_prefs import IndicatorPrefs


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
    swings = (
        SwingPoint(5, SwingKind.HIGH, 110.0, 1_000),
        SwingPoint(8, SwingKind.LOW, 90.0, 2_000),
    )
    empty = StructureMap(
        timeframe="15m",
        bias=Bias.RANGE,
        swings=swings,
        events=(),
        fvgs=(),
        levels=(_level(100.0), _level(105.0)),
        breaks=(),
    )
    off = structure_to_overlays(
        empty,
        show_bos=False,
        show_fvg=False,
        show_levels=False,
        show_swings=False,
        ref_price=100.0,
    )
    assert off["markers"] == []
    assert off["zones"] == []
    assert off["levels"] == []
    assert off["segments"] == []
    assert off["labels"] == []

    on = structure_to_overlays(
        empty,
        show_bos=False,
        show_fvg=False,
        show_levels=True,
        show_swings=True,
        ref_price=100.0,
    )
    assert len(on["levels"]) == 2
    assert on["markers"] == []
    swing_labels = [lb for lb in on["labels"] if lb.get("icon") in {
        "triangleUp",
        "triangleDown",
        "circle",
        "square",
    } and lb.get("anchor") != "right"]
    # 2 swings + 2 level labels
    assert len(on["labels"]) == 4
    assert {lb["icon"] for lb in swing_labels} == {"triangleUp", "triangleDown"}
    assert all(lv["title"] == "" for lv in on["levels"])
    assert all(
        lb["text"] == "LVL" for lb in on["labels"] if lb.get("anchor") == "right"
    )

def test_bos_label_on_break_line_not_axis() -> None:
    swings = (
        SwingPoint(5, SwingKind.HIGH, 110.0, 1_000),
        SwingPoint(8, SwingKind.LOW, 90.0, 2_000),
    )
    events = (
        StructureEvent(
            kind=StructureEventKind.BOS,
            bias=Bias.BULLISH,
            index=12,
            price=110.0,
            time_sec=3_000,
            broken_swing_index=5,
        ),
    )
    structure = StructureMap(
        timeframe="15m",
        bias=Bias.BULLISH,
        swings=swings,
        events=events,
        fvgs=(),
        levels=(),
        breaks=(),
    )
    prefs = IndicatorPrefs(show_bos=True)
    overlays = structure_to_overlays(structure, prefs=prefs)
    assert len(overlays["segments"]) == 1
    seg = overlays["segments"][0]
    assert seg["price"] == 110.0
    assert seg["title"] == ""
    assert overlays["markers"] == []
    assert len(overlays["labels"]) == 1
    label = overlays["labels"][0]
    assert label["text"] == "BOS"
    assert label["price"] == 110.0
    assert label["time"] == 3_000
    assert label["align"] == "center"
    assert label["icon"] == "circle"
    assert label["fontSize"] == 10
