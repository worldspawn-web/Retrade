"""UI theme / toast / sound smoke (no crash)."""

from __future__ import annotations

from retrade.ui import theme
from retrade.ui.sounds import SoundPlayer


def test_app_stylesheet_nonempty() -> None:
    css = theme.app_stylesheet()
    assert theme.BG in css
    assert theme.MINT in css
    assert "QPushButton#longButton" in css


def test_sound_player_no_crash() -> None:
    player = SoundPlayer()
    assert player.enabled is True
    player.set_enabled(False)
    player.play("tp")
    player.set_enabled(True)
    for name in ("tp", "sl", "exit", "hold", "error", "missing"):
        player.play(name)
