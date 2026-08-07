"""Minimal visual debrief strip under the chart."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from retrade.domain.explanation import DebriefChip, Explanation

_TONE_COLORS = {
    "neutral": ("#2a2e39", "#d1d4dc"),
    "good": ("#12352f", "#26a69a"),
    "bad": ("#3a1f22", "#ef5350"),
    "warn": ("#3a2f14", "#f0b90b"),
    "accent": ("#1a2744", "#5b8def"),
}


class DebriefPanel(QFrame):
    """Chip-based post-trade summary: few words, high signal."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("debriefPanel")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setMinimumHeight(72)
        self.setMaximumHeight(96)

        self._headline = QLabel("—")
        self._headline.setObjectName("debriefHeadline")

        self._note = QLabel("")
        self._note.setObjectName("debriefNote")
        self._note.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        self._chips_row = QHBoxLayout()
        self._chips_row.setSpacing(8)
        self._chips_row.setContentsMargins(0, 0, 0, 0)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addWidget(self._headline)
        top.addStretch(1)
        top.addWidget(self._note)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)
        root.addLayout(top)
        root.addLayout(self._chips_row)

        self.setStyleSheet(
            """
            QFrame#debriefPanel {
                background-color: #131722;
                border: 1px solid #2a2e39;
                border-radius: 6px;
            }
            QLabel#debriefHeadline {
                color: #f0f3fa;
                font-size: 16px;
                font-weight: 700;
                letter-spacing: 0.5px;
            }
            QLabel#debriefNote {
                color: #787b86;
                font-size: 12px;
            }
            """
        )
        self.clear()

    def clear(self) -> None:
        self._headline.setText("DEBRIEF")
        self._note.setText("ожидание результата")
        self._rebuild_chips(())

    def show_explanation(self, explanation: Explanation) -> None:
        self._headline.setText(explanation.headline)
        self._note.setText(explanation.note or "")
        self._rebuild_chips(explanation.chips)

    def _rebuild_chips(self, chips: tuple[DebriefChip, ...]) -> None:
        while self._chips_row.count():
            item = self._chips_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for chip in chips:
            self._chips_row.addWidget(self._make_chip(chip))
        self._chips_row.addStretch(1)

    def _make_chip(self, chip: DebriefChip) -> QWidget:
        bg, fg = _TONE_COLORS.get(chip.tone, _TONE_COLORS["neutral"])
        frame = QFrame()
        frame.setObjectName("debriefChip")
        frame.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(6)

        label = QLabel(chip.label)
        label.setStyleSheet("color: #787b86; font-size: 10px; font-weight: 600;")
        value = QLabel(chip.value)
        value.setStyleSheet(f"color: {fg}; font-size: 12px; font-weight: 700;")
        layout.addWidget(label)
        layout.addWidget(value)

        frame.setStyleSheet(
            f"""
            QFrame#debriefChip {{
                background-color: {bg};
                border: 1px solid #2a2e39;
                border-radius: 4px;
            }}
            """
        )
        return frame
