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
BOS_ICONS: tuple[str, ...] = ("none", "circle", "triangle", "square")


@dataclass
class BosVisual:
    bull_color: str = "#26a69a"
    bear_color: str = "#ef5350"
    line_style: str = "dashed"
    line_width: int = 1
    show_labels: bool = True
    label_size: float = 1.0
    icon: str = "circle"


@dataclass
class FvgVisual:
    bull_color: str = "#26a69a"
    bear_color: str = "#ef5350"
    bull_border: str = "#26a69a"
    bear_border: str = "#ef5350"
    fill_opacity: float = 0.18


@dataclass
class LevelsVisual:
    color: str = "#f0b90b"
    line_style: str = "dashed"
    line_width: int = 1
    show_labels: bool = True
    label_text: str = "LVL"


@dataclass
class SwingsVisual:
    color: str = "#9a9da6"
    icon: str = "triangle"
    size: float = 1.0
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


def _migrate_size(value: float, *, default: float) -> float:
    """Old scale used ~0.2–2.0 with default ~0.45–0.5; map 0.2 → 1.0."""
    if value <= 0:
        return default
    if value < 0.9:
        return round(value * 5.0, 2)
    return value


def _load_bos(
    raw: dict[str, Any] | None,
    *,
    migrate: bool,
) -> BosVisual:
    d = BosVisual()
    if not isinstance(raw, dict):
        return d
    legacy_icon = "icon" not in raw
    icon = str(raw.get("icon", d.icon))
    if icon not in BOS_ICONS:
        if legacy_icon and raw.get("show_icons"):
            icon = "circle"
        elif legacy_icon:
            icon = "none"
        else:
            icon = d.icon
    size = float(raw.get("label_size", d.label_size))
    if migrate:
        size = _migrate_size(size, default=d.label_size)
    return BosVisual(
        bull_color=str(raw.get("bull_color", d.bull_color)),
        bear_color=str(raw.get("bear_color", d.bear_color)),
        line_style=str(raw.get("line_style", d.line_style)),
        line_width=int(raw.get("line_width", d.line_width)),
        show_labels=bool(raw.get("show_labels", d.show_labels)),
        label_size=size,
        icon=icon,
    )


def _parse_opacity_from_rgba(value: str, fallback: float) -> float:
    try:
        inner = value[value.index("(") + 1 : value.index(")")]
        parts = [p.strip() for p in inner.split(",")]
        if len(parts) >= 4:
            return float(parts[3])
    except (ValueError, IndexError):
        pass
    return fallback


def _rgba_to_hex(value: str, fallback: str) -> str:
    if value.startswith("#"):
        return value
    try:
        inner = value[value.index("(") + 1 : value.index(")")]
        parts = [p.strip() for p in inner.split(",")]
        r, g, b = (int(float(parts[0])), int(float(parts[1])), int(float(parts[2])))
        return f"#{r:02x}{g:02x}{b:02x}"
    except (ValueError, IndexError):
        return fallback


def _load_fvg(raw: dict[str, Any] | None) -> FvgVisual:
    d = FvgVisual()
    if not isinstance(raw, dict):
        return d
    bull_color = str(raw.get("bull_color", d.bull_color))
    bear_color = str(raw.get("bear_color", d.bear_color))
    opacity = float(raw.get("fill_opacity", d.fill_opacity))
    # Legacy rgba fills
    if "bull_fill" in raw and "bull_color" not in raw:
        bull_color = _rgba_to_hex(str(raw["bull_fill"]), d.bull_color)
        opacity = _parse_opacity_from_rgba(str(raw["bull_fill"]), opacity)
    if "bear_fill" in raw and "bear_color" not in raw:
        bear_color = _rgba_to_hex(str(raw["bear_fill"]), d.bear_color)
    return FvgVisual(
        bull_color=bull_color,
        bear_color=bear_color,
        bull_border=str(raw.get("bull_border", d.bull_border)),
        bear_border=str(raw.get("bear_border", d.bear_border)),
        fill_opacity=max(0.0, min(1.0, opacity)),
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
        label_text=str(raw.get("label_text", d.label_text)) or d.label_text,
    )


def _load_swings(
    raw: dict[str, Any] | None,
    *,
    migrate: bool,
) -> SwingsVisual:
    d = SwingsVisual()
    if not isinstance(raw, dict):
        return d
    icon = str(raw.get("icon", d.icon))
    if icon not in SWING_ICONS:
        icon = d.icon
    size = float(raw.get("size", d.size))
    if migrate:
        size = _migrate_size(size, default=d.size)
    return SwingsVisual(
        color=str(raw.get("color", d.color)),
        icon=icon,
        size=size,
        show_labels=bool(raw.get("show_labels", d.show_labels)),
    )


def load_indicator_prefs(raw: dict[str, Any] | None) -> IndicatorPrefs:
    if not isinstance(raw, dict):
        return IndicatorPrefs()
    migrate = int(raw.get("visual_scale", 1)) < 2
    return IndicatorPrefs(
        show_bos=bool(raw.get("show_bos", False)),
        show_fvg=bool(raw.get("show_fvg", False)),
        show_levels=bool(raw.get("show_levels", False)),
        show_swings=bool(raw.get("show_swings", False)),
        bos=_load_bos(
            raw.get("bos") if isinstance(raw.get("bos"), dict) else None,
            migrate=migrate,
        ),
        fvg=_load_fvg(raw.get("fvg") if isinstance(raw.get("fvg"), dict) else None),
        levels=_load_levels(
            raw.get("levels") if isinstance(raw.get("levels"), dict) else None
        ),
        swings=_load_swings(
            raw.get("swings") if isinstance(raw.get("swings"), dict) else None,
            migrate=migrate,
        ),
    )


def hex_to_rgba(hex_color: str, alpha: float) -> str:
    color = hex_color.lstrip("#")
    if len(color) != 6:
        return f"rgba(38, 166, 154, {alpha})"
    r = int(color[0:2], 16)
    g = int(color[2:4], 16)
    b = int(color[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


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
        indicators = asdict(prefs.indicators)
        indicators["visual_scale"] = 2
        payload = {"indicators": indicators}
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
