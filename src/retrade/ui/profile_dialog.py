"""Profile dialog: display name, avatar, statistics, sound toggle, reset."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from retrade.domain.profile import ProfileStore
from retrade.domain.ui_prefs import UiPrefsStore
from retrade.ui import theme


class ProfileDialog(QDialog):
    """Edit profile and view / reset trade statistics."""

    def __init__(
        self,
        store: ProfileStore,
        default_avatar: Path,
        parent: QWidget | None = None,
        *,
        ui_prefs: UiPrefsStore | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._default_avatar = default_avatar
        self._ui_prefs = ui_prefs
        self.setWindowTitle("Профиль")
        self.setMinimumWidth(400)
        self.setStyleSheet(theme.app_stylesheet())

        self._avatar_label = QLabel()
        self._avatar_label.setFixedSize(72, 72)
        self._avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._avatar_label.setStyleSheet(
            f"border-radius: 36px; background: {theme.ELEVATED}; "
            f"border: 1px solid {theme.BORDER};"
        )

        self._name_edit = QLineEdit(store.profile.display_name)
        self._name_edit.setMaxLength(64)

        change_avatar = QPushButton("Сменить аватар…")
        change_avatar.clicked.connect(self._pick_avatar)
        clear_avatar = QPushButton("Сбросить аватар")
        clear_avatar.clicked.connect(self._clear_avatar)

        avatar_row = QHBoxLayout()
        avatar_row.addWidget(self._avatar_label)
        avatar_col = QVBoxLayout()
        avatar_col.addWidget(change_avatar)
        avatar_col.addWidget(clear_avatar)
        avatar_col.addStretch(1)
        avatar_row.addLayout(avatar_col)

        self._sounds_check = QCheckBox("Звуки уведомлений")
        if ui_prefs is not None:
            self._sounds_check.setChecked(ui_prefs.prefs.sounds_enabled)
        else:
            self._sounds_check.setChecked(True)
            self._sounds_check.setEnabled(False)

        self._stats_labels: dict[str, QLabel] = {}
        stats_grid = QGridLayout()
        stats_grid.setHorizontalSpacing(8)
        stats_grid.setVerticalSpacing(8)
        items = (
            ("trades", "Сделок"),
            ("wins", "TP"),
            ("losses", "SL"),
            ("draws", "Ничьи"),
            ("exits", "EXIT"),
            ("skips", "Skip"),
            ("open_tails", "No hit"),
            ("sum_r", "Σ R"),
            ("winrate", "Winrate"),
        )
        for i, (key, title) in enumerate(items):
            card = self._make_stat_card(title, key)
            stats_grid.addWidget(card, i // 3, i % 3)

        reset_btn = QPushButton("Сбросить статистику")
        reset_btn.clicked.connect(self._reset_stats)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.addLayout(avatar_row)
        form = QFormLayout()
        form.addRow("Имя", self._name_edit)
        root.addLayout(form)
        root.addWidget(self._sounds_check)
        root.addWidget(QLabel("Статистика"))
        root.addLayout(stats_grid)
        root.addWidget(reset_btn)
        root.addWidget(buttons)

        self._refresh_avatar()
        self._refresh_stats()

    def _make_stat_card(self, title: str, key: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("statCard")
        frame.setStyleSheet(
            f"""
            QFrame#statCard {{
                background-color: {theme.ELEVATED};
                border: 1px solid {theme.BORDER};
                border-radius: 8px;
            }}
            QLabel#statTitle {{
                color: {theme.TEXT_MUTED};
                font-size: 11px;
            }}
            QLabel#statValue {{
                color: {theme.TEXT};
                font-size: 15px;
                font-weight: 700;
            }}
            """
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)
        title_l = QLabel(title)
        title_l.setObjectName("statTitle")
        value_l = QLabel("—")
        value_l.setObjectName("statValue")
        self._stats_labels[key] = value_l
        layout.addWidget(title_l)
        layout.addWidget(value_l)
        return frame

    def _refresh_avatar(self) -> None:
        path = self._store.profile.resolved_avatar(self._default_avatar)
        pix = QPixmap(str(path))
        if pix.isNull():
            self._avatar_label.clear()
            self._avatar_label.setText("R")
            return
        scaled = pix.scaled(
            72,
            72,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._avatar_label.setPixmap(scaled)

    def _refresh_stats(self) -> None:
        stats = self._store.profile.stats
        self._stats_labels["trades"].setText(str(stats.trades))
        self._stats_labels["wins"].setText(str(stats.wins))
        self._stats_labels["losses"].setText(str(stats.losses))
        self._stats_labels["draws"].setText(str(stats.draws))
        self._stats_labels["exits"].setText(str(stats.exits))
        self._stats_labels["skips"].setText(str(stats.skips))
        self._stats_labels["open_tails"].setText(str(stats.open_tails))
        self._stats_labels["sum_r"].setText(f"{stats.sum_r:+.2f}")
        wr = stats.winrate
        self._stats_labels["winrate"].setText(
            f"{wr * 100:.0f}%" if wr is not None else "—"
        )

    def _pick_avatar(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Выбери аватар",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if not path_str:
            return
        path = Path(path_str)
        if not path.is_file():
            return
        self._store.set_avatar_path(path)
        self._refresh_avatar()

    def _clear_avatar(self) -> None:
        self._store.set_avatar_path(None)
        self._refresh_avatar()

    def _reset_stats(self) -> None:
        reply = QMessageBox.question(
            self,
            "Сброс статистики",
            "Обнулить все счётчики сделок?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply is not QMessageBox.StandardButton.Yes:
            return
        self._store.reset_stats()
        self._refresh_stats()

    def _accept(self) -> None:
        self._store.set_display_name(self._name_edit.text())
        if self._ui_prefs is not None:
            self._ui_prefs.set_sounds_enabled(self._sounds_check.isChecked())
        self.accept()
