"""Quiet UI sound effects (QSoundEffect)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QSoundEffect

VOLUME = 0.25
_SOUNDS_DIR = Path(__file__).resolve().parent / "assets" / "sounds"


class SoundPlayer:
    """Plays short cue WAVs; no-op if unavailable or muted."""

    def __init__(self) -> None:
        self._enabled = True
        self._effects: dict[str, QSoundEffect] = {}
        root = _SOUNDS_DIR
        for name in ("tp", "sl", "exit", "hold", "error"):
            path = root / f"{name}.wav"
            if not path.is_file():
                continue
            effect = QSoundEffect()
            effect.setSource(QUrl.fromLocalFile(str(path.resolve())))
            effect.setVolume(VOLUME)
            self._effects[name] = effect

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    def play(self, name: str) -> None:
        if not self._enabled:
            return
        effect = self._effects.get(name)
        if effect is None:
            return
        try:
            effect.play()
        except Exception:
            return
