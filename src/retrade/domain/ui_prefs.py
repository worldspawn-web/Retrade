"""Persisted UI preferences (indicator toggles, etc.)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class IndicatorPrefs:
    show_bos: bool = False
    show_fvg: bool = False
    show_levels: bool = False
    show_swings: bool = False


@dataclass
class UiPrefs:
    indicators: IndicatorPrefs

    @classmethod
    def defaults(cls) -> UiPrefs:
        return cls(indicators=IndicatorPrefs())


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
            ind = raw.get("indicators", {})
            return UiPrefs(
                indicators=IndicatorPrefs(
                    show_bos=bool(ind.get("show_bos", False)),
                    show_fvg=bool(ind.get("show_fvg", False)),
                    show_levels=bool(ind.get("show_levels", False)),
                    show_swings=bool(ind.get("show_swings", False)),
                )
            )
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
