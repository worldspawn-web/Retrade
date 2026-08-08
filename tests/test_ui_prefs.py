"""UI prefs persistence."""

from __future__ import annotations

from pathlib import Path

from retrade.domain.ui_prefs import UiPrefsStore


def test_ui_prefs_default_off(tmp_path: Path) -> None:
    store = UiPrefsStore(tmp_path / "ui_prefs.json")
    assert store.prefs.indicators.show_bos is False
    assert store.prefs.indicators.show_fvg is False
    assert store.prefs.indicators.show_levels is False


def test_ui_prefs_persist(tmp_path: Path) -> None:
    path = tmp_path / "ui_prefs.json"
    store = UiPrefsStore(path)
    store.set_indicator("bos", True)
    store.set_indicator("levels", True)
    again = UiPrefsStore(path)
    assert again.prefs.indicators.show_bos is True
    assert again.prefs.indicators.show_levels is True
    assert again.prefs.indicators.show_fvg is False
