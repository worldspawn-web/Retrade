"""Modal for per-indicator visual settings with live preview."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from retrade.domain.ui_prefs import (
    BOS_ICONS,
    LINE_STYLE_CODES,
    SWING_ICONS,
    BosVisual,
    FvgVisual,
    IndicatorPrefs,
    LevelsVisual,
    SwingsVisual,
    UiPrefsStore,
)
from retrade.ui import theme

_LINE_LABELS = {
    "solid": "Solid",
    "dotted": "Dotted",
    "dashed": "Dashed",
    "large_dashed": "Large dashed",
    "sparse_dotted": "Sparse dotted",
}

_BOS_ICON_LABELS = {
    "none": "Нет",
    "circle": "Круг",
    "triangle": "Треугольник",
    "square": "Квадрат",
}

_SIZE_MIN = 0.1
_SIZE_MAX = 3.0


class _ColorButton(QPushButton):
    color_changed = Signal(str)

    def __init__(self, color: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = color
        self.setFixedWidth(88)
        self.clicked.connect(self._pick)
        self._apply()

    @property
    def color(self) -> str:
        return self._color

    def set_color(self, color: str, *, emit: bool = True) -> None:
        self._color = color
        self._apply()
        if emit:
            self.color_changed.emit(self._color)

    def _apply(self) -> None:
        self.setText(self._color)
        self.setStyleSheet(
            f"background-color: {self._color}; color: {theme.BG}; "
            f"border: 1px solid {theme.BORDER}; border-radius: 8px; padding: 4px;"
        )

    def _pick(self) -> None:
        initial = QColor(self._color)
        chosen = QColorDialog.getColor(initial, self, "Цвет")
        if chosen.isValid():
            self.set_color(chosen.name())


def _line_combo(current: str) -> QComboBox:
    box = QComboBox()
    for key in LINE_STYLE_CODES:
        box.addItem(_LINE_LABELS[key], key)
    idx = box.findData(current)
    box.setCurrentIndex(idx if idx >= 0 else 0)
    return box


def _size_spin(value: float) -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setRange(_SIZE_MIN, _SIZE_MAX)
    box.setSingleStep(0.1)
    box.setDecimals(2)
    box.setValue(value)
    return box


class IndicatorStyleDialog(QDialog):
    """Tabs with live preview; Cancel restores baseline."""

    preview_changed = Signal(object)  # IndicatorPrefs

    def __init__(
        self,
        store: UiPrefsStore,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._baseline = deepcopy(store.prefs.indicators)
        self._draft = deepcopy(store.prefs.indicators)
        self.setWindowTitle("Настройки индикаторов")
        self.setMinimumWidth(460)
        self.setStyleSheet(theme.app_stylesheet())

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_bos_tab(), "BOS / CHoCH")
        self._tabs.addTab(self._build_fvg_tab(), "FVG")
        self._tabs.addTab(self._build_levels_tab(), "Levels")
        self._tabs.addTab(self._build_swings_tab(), "Swings")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self._cancel)

        root = QVBoxLayout(self)
        root.addWidget(self._tabs)
        root.addWidget(buttons)

        self._wire_preview()

    def _wire_preview(self) -> None:
        widgets: list[QWidget] = [
            self._bos_bull,
            self._bos_bear,
            self._bos_line,
            self._bos_width,
            self._bos_labels,
            self._bos_icon,
            self._bos_size,
            self._fvg_bull,
            self._fvg_bear,
            self._fvg_bull_border,
            self._fvg_bear_border,
            self._fvg_opacity,
            self._lvl_color,
            self._lvl_line,
            self._lvl_width,
            self._lvl_labels,
            self._lvl_text,
            self._sw_color,
            self._sw_icon,
            self._sw_size,
            self._sw_labels,
        ]
        for w in widgets:
            if isinstance(w, _ColorButton):
                w.color_changed.connect(lambda _=None: self._emit_preview())
            elif isinstance(w, QComboBox):
                w.currentIndexChanged.connect(lambda _=0: self._emit_preview())
            elif isinstance(w, QCheckBox):
                w.toggled.connect(lambda _=False: self._emit_preview())
            elif isinstance(w, (QSpinBox, QDoubleSpinBox)):
                w.valueChanged.connect(lambda _=0: self._emit_preview())
            elif isinstance(w, QLineEdit):
                w.textChanged.connect(lambda _="": self._emit_preview())

    def _build_bos_tab(self) -> QWidget:
        bos = self._draft.bos
        w = QWidget()
        form = QFormLayout(w)
        self._bos_bull = _ColorButton(bos.bull_color)
        self._bos_bear = _ColorButton(bos.bear_color)
        self._bos_line = _line_combo(bos.line_style)
        self._bos_width = QSpinBox()
        self._bos_width.setRange(1, 4)
        self._bos_width.setValue(bos.line_width)
        self._bos_labels = QCheckBox("Показывать подписи (только на графике)")
        self._bos_labels.setChecked(bos.show_labels)
        self._bos_icon = QComboBox()
        for key in BOS_ICONS:
            self._bos_icon.addItem(_BOS_ICON_LABELS[key], key)
        idx = self._bos_icon.findData(bos.icon)
        self._bos_icon.setCurrentIndex(idx if idx >= 0 else 0)
        self._bos_size = _size_spin(bos.label_size)
        form.addRow("Цвет bull", self._bos_bull)
        form.addRow("Цвет bear", self._bos_bear)
        form.addRow("Тип линии", self._bos_line)
        form.addRow("Толщина", self._bos_width)
        form.addRow(self._bos_labels)
        form.addRow("Иконка", self._bos_icon)
        form.addRow("Размер подписи / иконки", self._bos_size)
        self._add_reset(form, self._reset_bos)
        return w

    def _build_fvg_tab(self) -> QWidget:
        fvg = self._draft.fvg
        w = QWidget()
        form = QFormLayout(w)
        self._fvg_bull = _ColorButton(fvg.bull_color)
        self._fvg_bear = _ColorButton(fvg.bear_color)
        self._fvg_bull_border = _ColorButton(fvg.bull_border)
        self._fvg_bear_border = _ColorButton(fvg.bear_border)
        self._fvg_opacity = QDoubleSpinBox()
        self._fvg_opacity.setRange(0.0, 1.0)
        self._fvg_opacity.setSingleStep(0.05)
        self._fvg_opacity.setDecimals(2)
        self._fvg_opacity.setValue(fvg.fill_opacity)
        form.addRow("Цвет заливки bull", self._fvg_bull)
        form.addRow("Цвет заливки bear", self._fvg_bear)
        form.addRow("Рамка bull", self._fvg_bull_border)
        form.addRow("Рамка bear", self._fvg_bear_border)
        form.addRow("Прозрачность заливки", self._fvg_opacity)
        self._add_reset(form, self._reset_fvg)
        return w

    def _build_levels_tab(self) -> QWidget:
        levels = self._draft.levels
        w = QWidget()
        form = QFormLayout(w)
        self._lvl_color = _ColorButton(levels.color)
        self._lvl_line = _line_combo(levels.line_style)
        self._lvl_width = QSpinBox()
        self._lvl_width.setRange(1, 4)
        self._lvl_width.setValue(levels.line_width)
        self._lvl_labels = QCheckBox("Показывать подпись на графике")
        self._lvl_labels.setChecked(levels.show_labels)
        self._lvl_text = QLineEdit(levels.label_text)
        self._lvl_text.setMaxLength(12)
        form.addRow("Цвет", self._lvl_color)
        form.addRow("Тип линии", self._lvl_line)
        form.addRow("Толщина", self._lvl_width)
        form.addRow(self._lvl_labels)
        form.addRow("Текст подписи", self._lvl_text)
        self._add_reset(form, self._reset_levels)
        return w

    def _build_swings_tab(self) -> QWidget:
        swings = self._draft.swings
        w = QWidget()
        form = QFormLayout(w)
        self._sw_color = _ColorButton(swings.color)
        self._sw_icon = QComboBox()
        for key in SWING_ICONS:
            label = {
                "triangle": "Треугольники",
                "circle": "Круги",
                "square": "Квадраты",
            }[key]
            self._sw_icon.addItem(label, key)
        idx = self._sw_icon.findData(swings.icon)
        self._sw_icon.setCurrentIndex(idx if idx >= 0 else 0)
        self._sw_size = _size_spin(swings.size)
        self._sw_labels = QCheckBox("Подписи SH / SL")
        self._sw_labels.setChecked(swings.show_labels)
        form.addRow("Цвет", self._sw_color)
        form.addRow("Иконка", self._sw_icon)
        form.addRow("Размер", self._sw_size)
        form.addRow(self._sw_labels)
        self._add_reset(form, self._reset_swings)
        return w

    def _add_reset(self, form: QFormLayout, reset_fn: Callable[[], None]) -> None:
        btn = QPushButton("Сбросить вкладку по умолчанию")
        btn.clicked.connect(lambda: self._on_reset_tab(reset_fn))
        form.addRow(btn)

    def _on_reset_tab(self, reset_fn: Callable[[], None]) -> None:
        reset_fn()
        self._emit_preview()

    def _reset_bos(self) -> None:
        d = BosVisual()
        self._bos_bull.set_color(d.bull_color, emit=False)
        self._bos_bear.set_color(d.bear_color, emit=False)
        self._bos_line.setCurrentIndex(self._bos_line.findData(d.line_style))
        self._bos_width.setValue(d.line_width)
        self._bos_labels.setChecked(d.show_labels)
        self._bos_icon.setCurrentIndex(self._bos_icon.findData(d.icon))
        self._bos_size.setValue(d.label_size)

    def _reset_fvg(self) -> None:
        d = FvgVisual()
        self._fvg_bull.set_color(d.bull_color, emit=False)
        self._fvg_bear.set_color(d.bear_color, emit=False)
        self._fvg_bull_border.set_color(d.bull_border, emit=False)
        self._fvg_bear_border.set_color(d.bear_border, emit=False)
        self._fvg_opacity.setValue(d.fill_opacity)

    def _reset_levels(self) -> None:
        d = LevelsVisual()
        self._lvl_color.set_color(d.color, emit=False)
        self._lvl_line.setCurrentIndex(self._lvl_line.findData(d.line_style))
        self._lvl_width.setValue(d.line_width)
        self._lvl_labels.setChecked(d.show_labels)
        self._lvl_text.setText(d.label_text)

    def _reset_swings(self) -> None:
        d = SwingsVisual()
        self._sw_color.set_color(d.color, emit=False)
        self._sw_icon.setCurrentIndex(self._sw_icon.findData(d.icon))
        self._sw_size.setValue(d.size)
        self._sw_labels.setChecked(d.show_labels)

    def _collect(self) -> IndicatorPrefs:
        live = self._store.prefs.indicators
        return IndicatorPrefs(
            show_bos=live.show_bos,
            show_fvg=live.show_fvg,
            show_levels=live.show_levels,
            show_swings=live.show_swings,
            bos=BosVisual(
                bull_color=self._bos_bull.color,
                bear_color=self._bos_bear.color,
                line_style=str(self._bos_line.currentData()),
                line_width=int(self._bos_width.value()),
                show_labels=self._bos_labels.isChecked(),
                label_size=float(self._bos_size.value()),
                icon=str(self._bos_icon.currentData()),
            ),
            fvg=FvgVisual(
                bull_color=self._fvg_bull.color,
                bear_color=self._fvg_bear.color,
                bull_border=self._fvg_bull_border.color,
                bear_border=self._fvg_bear_border.color,
                fill_opacity=float(self._fvg_opacity.value()),
            ),
            levels=LevelsVisual(
                color=self._lvl_color.color,
                line_style=str(self._lvl_line.currentData()),
                line_width=int(self._lvl_width.value()),
                show_labels=self._lvl_labels.isChecked(),
                label_text=self._lvl_text.text().strip() or "LVL",
            ),
            swings=SwingsVisual(
                color=self._sw_color.color,
                icon=str(self._sw_icon.currentData()),
                size=float(self._sw_size.value()),
                show_labels=self._sw_labels.isChecked(),
            ),
        )

    def _emit_preview(self) -> None:
        self.preview_changed.emit(self._collect())

    def _accept(self) -> None:
        self._store.set_indicator_prefs(self._collect())
        self.accept()

    def _cancel(self) -> None:
        restored = deepcopy(self._baseline)
        live = self._store.prefs.indicators
        restored.show_bos = live.show_bos
        restored.show_fvg = live.show_fvg
        restored.show_levels = live.show_levels
        restored.show_swings = live.show_swings
        self.preview_changed.emit(restored)
        self.reject()
