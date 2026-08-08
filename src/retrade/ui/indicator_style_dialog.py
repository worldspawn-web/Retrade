"""Modal for per-indicator visual settings."""

from __future__ import annotations

from copy import deepcopy

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from retrade.domain.ui_prefs import (
    LINE_STYLE_CODES,
    SWING_ICONS,
    BosVisual,
    FvgVisual,
    IndicatorPrefs,
    LevelsVisual,
    SwingsVisual,
    UiPrefsStore,
)

_LINE_LABELS = {
    "solid": "Solid",
    "dotted": "Dotted",
    "dashed": "Dashed",
    "large_dashed": "Large dashed",
    "sparse_dotted": "Sparse dotted",
}


class _ColorButton(QPushButton):
    def __init__(self, color: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = color
        self.setFixedWidth(88)
        self.clicked.connect(self._pick)
        self._apply()

    @property
    def color(self) -> str:
        return self._color

    def set_color(self, color: str) -> None:
        self._color = color
        self._apply()

    def _apply(self) -> None:
        self.setText(self._color)
        self.setStyleSheet(
            f"background-color: {self._color}; color: #0f1219; "
            "border: 1px solid #2a2e39; border-radius: 4px; padding: 4px;"
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


class IndicatorStyleDialog(QDialog):
    """Tabs: BOS/CHoCH, FVG, Levels, Swings — color, line, labels, icons."""

    def __init__(
        self,
        store: UiPrefsStore,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._draft = deepcopy(store.prefs.indicators)
        self.setWindowTitle("Настройки индикаторов")
        self.setMinimumWidth(440)

        tabs = QTabWidget()
        tabs.addTab(self._build_bos_tab(), "BOS / CHoCH")
        tabs.addTab(self._build_fvg_tab(), "FVG")
        tabs.addTab(self._build_levels_tab(), "Levels")
        tabs.addTab(self._build_swings_tab(), "Swings")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addWidget(tabs)
        root.addWidget(buttons)

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
        self._bos_labels = QCheckBox("Показывать подписи")
        self._bos_labels.setChecked(bos.show_labels)
        self._bos_icons = QCheckBox("Иконки (стрелки)")
        self._bos_icons.setChecked(bos.show_icons)
        self._bos_size = QDoubleSpinBox()
        self._bos_size.setRange(0.2, 2.0)
        self._bos_size.setSingleStep(0.05)
        self._bos_size.setDecimals(2)
        self._bos_size.setValue(bos.label_size)
        form.addRow("Цвет bull", self._bos_bull)
        form.addRow("Цвет bear", self._bos_bear)
        form.addRow("Тип линии", self._bos_line)
        form.addRow("Толщина", self._bos_width)
        form.addRow(self._bos_labels)
        form.addRow(self._bos_icons)
        form.addRow("Размер подписи", self._bos_size)
        form.addRow(QLabel("Линия — уровень пробоя; подпись у бара пробоя."))
        return w

    def _build_fvg_tab(self) -> QWidget:
        fvg = self._draft.fvg
        w = QWidget()
        form = QFormLayout(w)
        self._fvg_bull_fill = _ColorButton(self._rgba_to_hex(fvg.bull_fill))
        self._fvg_bear_fill = _ColorButton(self._rgba_to_hex(fvg.bear_fill))
        self._fvg_bull_border = _ColorButton(fvg.bull_border)
        self._fvg_bear_border = _ColorButton(fvg.bear_border)
        self._fvg_labels = QCheckBox("Подписи FVG")
        self._fvg_labels.setChecked(fvg.show_labels)
        form.addRow("Заливка bull", self._fvg_bull_fill)
        form.addRow("Заливка bear", self._fvg_bear_fill)
        form.addRow("Рамка bull", self._fvg_bull_border)
        form.addRow("Рамка bear", self._fvg_bear_border)
        form.addRow(self._fvg_labels)
        form.addRow(QLabel("Прозрачность заливки задаётся автоматически."))
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
        self._lvl_labels = QCheckBox("Подписи LVL")
        self._lvl_labels.setChecked(levels.show_labels)
        form.addRow("Цвет", self._lvl_color)
        form.addRow("Тип линии", self._lvl_line)
        form.addRow("Толщина", self._lvl_width)
        form.addRow(self._lvl_labels)
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
        self._sw_size = QDoubleSpinBox()
        self._sw_size.setRange(0.2, 2.0)
        self._sw_size.setSingleStep(0.05)
        self._sw_size.setDecimals(2)
        self._sw_size.setValue(swings.size)
        self._sw_labels = QCheckBox("Подписи SH / SL")
        self._sw_labels.setChecked(swings.show_labels)
        form.addRow("Цвет", self._sw_color)
        form.addRow("Иконка", self._sw_icon)
        form.addRow("Размер", self._sw_size)
        form.addRow(self._sw_labels)
        return w

    @staticmethod
    def _rgba_to_hex(value: str) -> str:
        if value.startswith("#"):
            return value
        # rgba(r,g,b,a) → approximate solid hex for the color picker.
        try:
            inner = value[value.index("(") + 1 : value.index(")")]
            parts = [p.strip() for p in inner.split(",")]
            r, g, b = (int(float(parts[0])), int(float(parts[1])), int(float(parts[2])))
            return f"#{r:02x}{g:02x}{b:02x}"
        except (ValueError, IndexError):
            return "#26a69a"

    @staticmethod
    def _hex_to_rgba(hex_color: str, alpha: float) -> str:
        c = QColor(hex_color)
        return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"

    def _collect(self) -> IndicatorPrefs:
        show = self._draft
        return IndicatorPrefs(
            show_bos=show.show_bos,
            show_fvg=show.show_fvg,
            show_levels=show.show_levels,
            show_swings=show.show_swings,
            bos=BosVisual(
                bull_color=self._bos_bull.color,
                bear_color=self._bos_bear.color,
                line_style=str(self._bos_line.currentData()),
                line_width=int(self._bos_width.value()),
                show_labels=self._bos_labels.isChecked(),
                label_size=float(self._bos_size.value()),
                show_icons=self._bos_icons.isChecked(),
            ),
            fvg=FvgVisual(
                bull_fill=self._hex_to_rgba(self._fvg_bull_fill.color, 0.18),
                bear_fill=self._hex_to_rgba(self._fvg_bear_fill.color, 0.18),
                bull_border=self._fvg_bull_border.color,
                bear_border=self._fvg_bear_border.color,
                show_labels=self._fvg_labels.isChecked(),
            ),
            levels=LevelsVisual(
                color=self._lvl_color.color,
                line_style=str(self._lvl_line.currentData()),
                line_width=int(self._lvl_width.value()),
                show_labels=self._lvl_labels.isChecked(),
            ),
            swings=SwingsVisual(
                color=self._sw_color.color,
                icon=str(self._sw_icon.currentData()),
                size=float(self._sw_size.value()),
                show_labels=self._sw_labels.isChecked(),
            ),
        )

    def _accept(self) -> None:
        self._store.set_indicator_prefs(self._collect())
        self.accept()
