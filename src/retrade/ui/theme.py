"""Retrade dark modern-minimal design tokens and QSS."""

from __future__ import annotations

# Surfaces
BG = "#0B0D12"
SURFACE = "#12151C"
ELEVATED = "#181C26"
BORDER = "#2A3040"
BORDER_SOFT = "#222733"

# Text
TEXT = "#E8ECF4"
TEXT_MUTED = "#8B93A7"
TEXT_DIM = "#5C6578"

# Accents (trading-native)
MINT = "#2DD4BF"
MINT_DIM = "#134E4A"
CORAL = "#F87171"
CORAL_DIM = "#4C1D1D"
AMBER = "#FBBF24"
AMBER_DIM = "#422006"
SKY = "#38BDF8"
SKY_DIM = "#0C4A6E"

RADIUS = "10px"
RADIUS_SM = "8px"
RADIUS_PILL = "999px"


def app_stylesheet() -> str:
    """Global application stylesheet."""
    return f"""
    QMainWindow, QDialog {{
        background-color: {BG};
        color: {TEXT};
    }}
    QWidget {{
        background-color: transparent;
        color: {TEXT};
        font-family: "Segoe UI Variable", "Segoe UI";
        font-size: 13px;
    }}
    QLabel {{
        background: transparent;
        color: {TEXT};
    }}
    QLabel#symbolBadge {{
        background-color: {ELEVATED};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_SM};
        padding: 6px 12px;
        font-size: 15px;
        font-weight: 700;
        color: {TEXT};
    }}
    QLabel#phaseBadge {{
        background-color: {SKY_DIM};
        border: 1px solid {SKY};
        border-radius: {RADIUS_PILL};
        padding: 4px 12px;
        font-size: 11px;
        font-weight: 600;
        color: {SKY};
    }}
    QLabel#statsBadge {{
        background-color: {ELEVATED};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_PILL};
        padding: 4px 10px;
        font-size: 11px;
        font-weight: 600;
        color: {TEXT_MUTED};
    }}
    QPushButton#profileNameButton {{
        background: transparent;
        border: none;
        color: {TEXT};
        font-weight: 600;
        padding: 4px 8px;
    }}
    QPushButton#profileNameButton:hover {{
        color: {SKY};
    }}
    QToolButton#avatarButton {{
        border: 1px solid {BORDER};
        border-radius: 18px;
        background: {ELEVATED};
        padding: 0;
    }}
    QToolButton#tfButton {{
        background-color: transparent;
        border: none;
        border-right: 1px solid {BORDER};
        border-radius: 0;
        padding: 6px 12px;
        min-height: 26px;
        color: {TEXT_MUTED};
        font-weight: 600;
        font-size: 12px;
    }}
    QToolButton#tfButton:hover {{
        color: {TEXT};
        background-color: {ELEVATED};
    }}
    QToolButton#tfButton:checked {{
        background-color: {SKY_DIM};
        color: {SKY};
    }}
    QFrame#tfSegment {{
        background-color: {SURFACE};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_SM};
    }}
    QToolButton#indicatorsButton {{
        background-color: {ELEVATED};
        border: 1px solid {BORDER};
        border-right: none;
        border-top-left-radius: {RADIUS_SM};
        border-bottom-left-radius: {RADIUS_SM};
        border-top-right-radius: 0;
        border-bottom-right-radius: 0;
        padding: 6px 12px;
        color: {TEXT};
        font-weight: 600;
    }}
    QToolButton#indicatorSettingsButton {{
        background-color: {ELEVATED};
        border: 1px solid {BORDER};
        border-top-left-radius: 0;
        border-bottom-left-radius: 0;
        border-top-right-radius: {RADIUS_SM};
        border-bottom-right-radius: {RADIUS_SM};
        padding: 6px 10px;
        min-width: 28px;
        color: {TEXT_MUTED};
    }}
    QToolButton#indicatorSettingsButton:hover {{
        color: {TEXT};
        background-color: {BORDER_SOFT};
    }}
    QPushButton {{
        background-color: {ELEVATED};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_SM};
        padding: 8px 14px;
        min-height: 30px;
        font-weight: 600;
        color: {TEXT};
    }}
    QPushButton:hover {{
        background-color: {BORDER_SOFT};
        border-color: #3A4254;
    }}
    QPushButton:disabled {{
        color: {TEXT_DIM};
        background-color: {SURFACE};
        border-color: {BORDER_SOFT};
    }}
    QPushButton#longButton {{
        color: {MINT};
        border-color: {MINT_DIM};
        background-color: {MINT_DIM};
    }}
    QPushButton#longButton:hover {{
        border-color: {MINT};
    }}
    QPushButton#shortButton {{
        color: {CORAL};
        border-color: {CORAL_DIM};
        background-color: {CORAL_DIM};
    }}
    QPushButton#shortButton:hover {{
        border-color: {CORAL};
    }}
    QPushButton#skipButton {{
        background: transparent;
        border: 1px solid {BORDER};
        color: {TEXT_MUTED};
        font-weight: 500;
    }}
    QPushButton#confirmButton {{
        background-color: {SKY_DIM};
        border-color: {SKY};
        color: {SKY};
        font-weight: 700;
    }}
    QPushButton#confirmButton:hover {{
        background-color: #0E7490;
        color: {TEXT};
    }}
    QPushButton#exitButton {{
        background-color: {CORAL_DIM};
        border-color: {CORAL};
        color: {CORAL};
        font-weight: 700;
    }}
    QPushButton#keepButton {{
        background-color: {MINT_DIM};
        border-color: {MINT};
        color: {MINT};
        font-weight: 700;
    }}
    QPushButton#nextButton {{
        background-color: {ELEVATED};
        border-color: {BORDER};
        font-weight: 700;
    }}
    QPushButton#stepButton {{
        background-color: {SURFACE};
        border-color: {BORDER};
        color: {TEXT_MUTED};
    }}
    QFrame#orderGroup {{
        background-color: {SURFACE};
        border: 1px solid {BORDER};
        border-radius: {RADIUS};
    }}
    QDoubleSpinBox {{
        background-color: {ELEVATED};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_SM};
        padding: 6px 8px;
        min-width: 130px;
        color: {TEXT};
        selection-background-color: {SKY_DIM};
    }}
    QDoubleSpinBox:focus, QLineEdit:focus {{
        border-color: {SKY};
    }}
    QLineEdit, QSpinBox, QComboBox {{
        background-color: {ELEVATED};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_SM};
        padding: 6px 8px;
        color: {TEXT};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {ELEVATED};
        border: 1px solid {BORDER};
        selection-background-color: {SKY_DIM};
        color: {TEXT};
    }}
    QCheckBox {{
        spacing: 8px;
        color: {TEXT};
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border-radius: 4px;
        border: 1px solid {BORDER};
        background: {ELEVATED};
    }}
    QCheckBox::indicator:checked {{
        background: {SKY};
        border-color: {SKY};
    }}
    QTabWidget::pane {{
        border: 1px solid {BORDER};
        border-radius: {RADIUS_SM};
        background: {SURFACE};
        top: -1px;
    }}
    QTabBar::tab {{
        background: {ELEVATED};
        border: 1px solid {BORDER};
        border-bottom: none;
        padding: 8px 14px;
        margin-right: 2px;
        border-top-left-radius: {RADIUS_SM};
        border-top-right-radius: {RADIUS_SM};
        color: {TEXT_MUTED};
    }}
    QTabBar::tab:selected {{
        background: {SURFACE};
        color: {TEXT};
        border-color: {BORDER};
    }}
    QMenu {{
        background-color: {ELEVATED};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_SM};
        padding: 4px;
    }}
    QMenu::item {{
        padding: 8px 24px 8px 12px;
        border-radius: 6px;
    }}
    QMenu::item:selected {{
        background-color: {SKY_DIM};
        color: {SKY};
    }}
    QStatusBar {{
        background-color: {BG};
        color: {TEXT_MUTED};
        border-top: 1px solid {BORDER_SOFT};
    }}
    QDialogButtonBox QPushButton {{
        min-width: 88px;
    }}
    QScrollArea {{
        border: none;
        background: transparent;
    }}
    """
