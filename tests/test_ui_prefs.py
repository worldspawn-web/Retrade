"""UI prefs persistence."""

from __future__ import annotations

from pathlib import Path

from retrade.domain.ui_prefs import (
    BosVisual,
    FvgVisual,
    IndicatorPrefs,
    UiPrefsStore,
    _migrate_size,
    hex_to_rgba,
)


def test_ui_prefs_default_off(tmp_path: Path) -> None:
    store = UiPrefsStore(tmp_path / "ui_prefs.json")
    assert store.prefs.indicators.show_bos is False
    assert store.prefs.indicators.show_fvg is False
    assert store.prefs.indicators.show_levels is False
    assert store.prefs.indicators.show_swings is False
    assert store.prefs.indicators.bos.show_labels is True
    assert store.prefs.indicators.bos.label_size == 1.0
    assert store.prefs.indicators.bos.icon == "circle"
    assert store.prefs.sounds_enabled is True


def test_sounds_enabled_persist(tmp_path: Path) -> None:
    path = tmp_path / "ui_prefs.json"
    store = UiPrefsStore(path)
    store.set_sounds_enabled(False)
    again = UiPrefsStore(path)
    assert again.prefs.sounds_enabled is False
    again.set_sounds_enabled(True)
    assert UiPrefsStore(path).prefs.sounds_enabled is True


def test_ui_prefs_persist(tmp_path: Path) -> None:
    path = tmp_path / "ui_prefs.json"
    store = UiPrefsStore(path)
    store.set_indicator("bos", True)
    store.set_indicator("levels", True)
    store.set_indicator("swings", True)
    again = UiPrefsStore(path)
    assert again.prefs.indicators.show_bos is True
    assert again.prefs.indicators.show_levels is True
    assert again.prefs.indicators.show_swings is True
    assert again.prefs.indicators.show_fvg is False


def test_ui_prefs_visual_persist(tmp_path: Path) -> None:
    path = tmp_path / "ui_prefs.json"
    store = UiPrefsStore(path)
    prefs = IndicatorPrefs(
        show_bos=True,
        bos=BosVisual(bull_color="#00ff00", label_size=0.35, icon="triangle"),
        fvg=FvgVisual(fill_opacity=0.4),
    )
    store.set_indicator_prefs(prefs)
    again = UiPrefsStore(path)
    assert again.prefs.indicators.bos.bull_color == "#00ff00"
    assert again.prefs.indicators.bos.label_size == 0.35
    assert again.prefs.indicators.bos.icon == "triangle"
    assert again.prefs.indicators.fvg.fill_opacity == 0.4


def test_migrate_size_maps_old_scale() -> None:
    assert _migrate_size(0.2, default=1.0) == 1.0
    assert _migrate_size(1.0, default=1.0) == 1.0


def test_hex_to_rgba() -> None:
    assert hex_to_rgba("#26a69a", 0.18) == "rgba(38, 166, 154, 0.18)"
