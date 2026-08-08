"""Fullscreen loading overlay with spinner over blurred content."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QGraphicsBlurEffect,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class _Spinner(QWidget):
    """Simple arc spinner."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._angle = 0
        self.setFixedSize(56, 56)
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        self._angle = (self._angle + 8) % 360
        self.update()

    def paintEvent(self, _event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#2962ff"))
        pen.setWidth(4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        rect = QRectF(6, 6, self.width() - 12, self.height() - 12)
        painter.drawArc(rect, -self._angle * 16, 270 * 16)


class LoadingOverlay(QWidget):
    """Dim + block input; parent content can be blurred separately."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("loadingOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            """
            QWidget#loadingOverlay {
                background-color: rgba(15, 18, 25, 140);
            }
            QLabel#loadingText {
                color: #f0f3fa;
                font-size: 14px;
                font-weight: 600;
            }
            """
        )
        self._spinner = _Spinner(self)
        self._label = QLabel("Загрузка…")
        self._label.setObjectName("loadingText")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        layout.addStretch(1)
        layout.addWidget(self._spinner, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(12)
        layout.addWidget(self._label, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)
        self.hide()

    def set_message(self, text: str) -> None:
        self._label.setText(text)

    def show_loading(self, message: str = "Загрузка…") -> None:
        self.set_message(message)
        self._spinner.start()
        self.raise_()
        self.show()

    def hide_loading(self) -> None:
        self._spinner.stop()
        self.hide()

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
        super().resizeEvent(event)  # type: ignore[misc]


def apply_content_blur(widget: QWidget, *, enabled: bool, radius: int = 10) -> None:
    """Toggle blur on a content widget (not the overlay)."""
    if not enabled:
        widget.setGraphicsEffect(None)
        return
    effect = QGraphicsBlurEffect(widget)
    effect.setBlurRadius(radius)
    widget.setGraphicsEffect(effect)
