"""Persisted UI preferences (indicator toggles and visual styles)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Lightweight Charts LineStyle enum values.
LINE_STYLE_CODES: dict[str, int] = {
    "solid": 0,
    "dotted": 1,
    "dashed": 2,
    "large_dashed": 3,
    "sparse_dotted": 4,
}

SWING_ICONS: tuple[str, ...] = ("triangle", "circle", "square")


@dataclass
class BosVisual:
    bull_color: str = "#26a69a"
    bear_color: str = "#ef5350"
    line_style: str = "dashed"
    line_width: int = 1
    show_labels: bool = True
    label_size: float = 0.5
    show_icons: bool = False


@dataclass
class FvgVisual:
    bull_fill: str = "rgba(38, 166, 154, 0.18)"
    bear_fill: str = "rgba(239, 83, 80, 0.18)"
    bull_border: str = "#26a69a"
    bear_border: str = "#ef5350"
    show_labels: bool = False


@dataclass
class LevelsVisual:
    color: str = "#f0b90b"
    line_style: str = "dashed"
    line_width: int = 1
    show_labels: bool = True


@dataclass
class SwingsVisual:
    color: str = "#9a9da6"
    icon: str = "triangle"
    size: float = 0.45
    show_labels: bool = False


@dataclass
class IndicatorPrefs:
    show_bos: bool = False
    show_fvg: bool = False
    show_levels: bool = False
    show_swings: bool = False
    bos: BosVisual = field(default_factory=BosVisual)
    fvg: FvgVisual = field(default_factory=FvgVisual)
    levels: LevelsVisual = field(default_factory=LevelsVisual)
    swings: SwingsVisual = field(default_factory=SwingsVisual)


@dataclass
class UiPrefs:
    indicators: IndicatorPrefs

    @classmethod
    def defaults(cls) -> UiPrefs:
        return cls(indicators=IndicatorPrefs())


def _load_bos(raw: dict[str, Any] | None) -> BosVisual:
    d = BosVisual()
    if not isinstance(raw, dict):
        return d
    return BosVisual(
        bull_color=str(raw.get("bull_color", d.bull_color)),
        bear_color=str(raw.get("bear_color", d.bear_color)),
        line_style=str(raw.get("line_style", d.line_style)),
        line_width=int(raw.get("line_width", d.line_width)),
        show_labels=bool(raw.get("show_labels", d.show_labels)),
        label_size=float(raw.get("label_size", d.label_size)),
        show_icons=bool(raw.get("show_icons", d.show_icons)),
    )


def _load_fvg(raw: dict[str, Any] | None) -> FvgVisual:
    d = FvgVisual()
    if not isinstance(raw, dict):
        return d
    return FvgVisual(
        bull_fill=str(raw.get("bull_fill", d.bull_fill)),
        bear_fill=str(raw.get("bear_fill", d.bear_fill)),
        bull_border=str(raw.get("bull_border", d.bull_border)),
        bear_border=str(raw.get("bear_border", d.bear_border)),
        show_labels=bool(raw.get("show_labels", d.show_labels)),
    )


def _load_levels(raw: dict[str, Any] | None) -> LevelsVisual:
    d = LevelsVisual()
    if not isinstance(raw, dict):
        return d
    return LevelsVisual(
        color=str(raw.get("color", d.color)),
        line_style=str(raw.get("line_style", d.line_style)),
        line_width=int(raw.get("line_width", d.line_width)),
        show_labels=bool(raw.get("show_labels", d.show_labels)),
    )


def _load_swings(raw: dict[str, Any] | None) -> SwingsVisual:
    d = SwingsVisual()
    if not isinstance(raw, dict):
        return d
    icon = str(raw.get("icon", d.icon))
    if icon not in SWING_ICONS:
        icon = d.icon
    return SwingsVisual(
        color=str(raw.get("color", d.color)),
        icon=icon,
        size=float(raw.get("size", d.size)),
        show_labels=bool(raw.get("show_labels", d.show_labels)),
    )


def load_indicator_prefs(raw: dict[str, Any] | None) -> IndicatorPrefs:
    if not isinstance(raw, dict):
        return IndicatorPrefs()
    return IndicatorPrefs(
        show_bos=bool(raw.get("show_bos", False)),
        show_fvg=bool(raw.get("show_fvg", False)),
        show_levels=bool(raw.get("show_levels", False)),
        show_swings=bool(raw.get("show_swings", False)),
        bos=_load_bos(raw.get("bos") if isinstance(raw.get("bos"), dict) else None),
        fvg=_load_fvg(raw.get("fvg") if isinstance(raw.get("fvg"), dict) else None),
        levels=_load_levels(
            raw.get("levels") if isinstance(raw.get("levels"), dict) else None
        ),
        swings=_load_swings(
            raw.get("swings") if isinstance(raw.get("swings"), dict) else None
        ),
    )


class UiPrefsStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self.prefs = self._load()

    def _load(self) -> UiPrefs:
        if not self._path.exists():
            prefs = UiPrefs.defaults()
            self._save(prefs)
            return prefs
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return UiPrefs(indicators=load_indicator_prefs(raw.get("indicators")))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return UiPrefs.defaults()

    def save(self) -> None:
        self._save(self.prefs)

    def _save(self, prefs: UiPrefs) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "indicators": asdict(prefs.indicators),
        }
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def set_indicator(self, key: str, value: bool) -> None:
        if key == "bos":
            self.prefs.indicators.show_bos = value
        elif key == "fvg":
            self.prefs.indicators.show_fvg = value
        elif key == "levels":
            self.prefs.indicators.show_levels = value
        elif key == "swings":
            self.prefs.indicators.show_swings = value
        else:
            raise KeyError(key)
        self.save()

    def set_indicator_prefs(self, indicators: IndicatorPrefs) -> None:
        self.prefs.indicators = indicators
        self.save()


def line_style_code(name: str) -> int:
    return LINE_STYLE_CODES.get(name, LINE_STYLE_CODES["dashed"])
