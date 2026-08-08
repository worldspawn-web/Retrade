"""Toast notification stack (top-right)."""

from __future__ import annotations

from enum import StrEnum

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from retrade.ui import theme


class ToastKind(StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    WARN = "warn"
    INFO = "info"


_KIND_STYLE = {
    ToastKind.SUCCESS: (theme.MINT_DIM, theme.MINT),
    ToastKind.ERROR: (theme.CORAL_DIM, theme.CORAL),
    ToastKind.WARN: (theme.AMBER_DIM, theme.AMBER),
    ToastKind.INFO: (theme.SKY_DIM, theme.SKY),
}


class _ToastCard(QFrame):
    def __init__(
        self,
        title: str,
        body: str,
        kind: ToastKind,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("toastCard")
        bg, accent = _KIND_STYLE[kind]
        self.setStyleSheet(
            f"""
            QFrame#toastCard {{
                background-color: {bg};
                border: 1px solid {accent};
                border-radius: 10px;
            }}
            QLabel#toastTitle {{
                color: {accent};
                font-size: 12px;
                font-weight: 700;
            }}
            QLabel#toastBody {{
                color: {theme.TEXT};
                font-size: 12px;
            }}
            """
        )
        title_l = QLabel(title)
        title_l.setObjectName("toastTitle")
        body_l = QLabel(body)
        body_l.setObjectName("toastBody")
        body_l.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)
        layout.addWidget(title_l)
        if body:
            layout.addWidget(body_l)
        self.setFixedWidth(300)


class ToastHost(QWidget):
    """Anchored to a parent window; stacks toasts top-right."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._stack = QVBoxLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._stack.setSpacing(8)
        self._stack.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight
        )
        self._cards: list[_ToastCard] = []
        self.hide()

    def show_toast(
        self,
        title: str,
        body: str = "",
        *,
        kind: ToastKind = ToastKind.INFO,
        msec: int = 3200,
    ) -> None:
        card = _ToastCard(title, body, kind, self)
        self._cards.append(card)
        self._stack.insertWidget(0, card)
        self._relayout()
        self.show()
        self.raise_()

        fade = QPropertyAnimation(card, b"windowOpacity", card)
        fade.setDuration(220)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        card.setWindowOpacity(0.0)
        fade.start()

        QTimer.singleShot(msec, lambda: self._dismiss(card))

    def _dismiss(self, card: _ToastCard) -> None:
        if card not in self._cards:
            return
        self._cards.remove(card)
        self._stack.removeWidget(card)
        card.deleteLater()
        if not self._cards:
            self.hide()
        else:
            self._relayout()

    def _relayout(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        margin = 16
        width = 320
        height = max(80, len(self._cards) * 78)
        self.setGeometry(
            parent.width() - width - margin,
            margin + 8,
            width,
            height,
        )

    def resize_to_parent(self) -> None:
        self._relayout()
