"""Main application window for the Retrade prototype."""

from __future__ import annotations

import logging
from enum import Enum, auto
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from retrade.chart.widget import ChartWidget
from retrade.config import Settings
from retrade.domain.explanation import (
    Explanation,
    build_explanation,
    structure_to_overlays,
)
from retrade.domain.playback import PlaybackState, RoundSession
from retrade.domain.pricing import price_decimals, price_step
from retrade.domain.profile import (
    ProfileStore,
    exit_price_for_outcome,
)
from retrade.domain.round_history import RoundHistory
from retrade.domain.scenario import build_scenario, pick_symbol
from retrade.domain.smc import analyze_series
from retrade.domain.trading import (
    Side,
    TradeOutcome,
    TradePlan,
    default_plan,
)
from retrade.domain.ui_prefs import UiPrefsStore
from retrade.infra.binance import BinanceMarketData
from retrade.infra.symbol_universe import SymbolUniverse
from retrade.ui.debrief_panel import DebriefPanel
from retrade.ui.indicator_style_dialog import IndicatorStyleDialog
from retrade.ui.loading_overlay import LoadingOverlay, apply_content_blur
from retrade.ui.profile_dialog import ProfileDialog

logger = logging.getLogger(__name__)

_DEFAULT_AVATAR = Path(__file__).resolve().parent / "assets" / "default_avatar.png"


class UiPhase(Enum):
    LOADING = auto()
    DECIDE = auto()
    PLACE_ORDERS = auto()
    PLAYBACK = auto()
    HOLD = auto()
    RESULT = auto()


_OUTCOME_TEXT = {
    TradeOutcome.TAKE_PROFIT: "Take Profit",
    TradeOutcome.STOP_LOSS: "Stop Loss",
    TradeOutcome.AMBIGUOUS: "Draw (TP and SL on same bar)",
    TradeOutcome.SKIP: "Skipped",
    TradeOutcome.OPEN: "No hit in scenario tail",
    TradeOutcome.EXIT: "Exit at market",
}


class MainWindow(QMainWindow):
    """TradingView-like shell: chart, TF switch, trade actions, playback."""

    def __init__(
        self,
        settings: Settings,
        market: BinanceMarketData,
        universe: SymbolUniverse,
        history: RoundHistory,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._market = market
        self._universe = universe
        self._history = history
        self._profile = ProfileStore(settings.data_dir / "profile.json")
        self._ui_prefs = UiPrefsStore(settings.data_dir / "ui_prefs.json")
        self._session: RoundSession | None = None
        self._playback: PlaybackState | None = None
        self._phase = UiPhase.LOADING
        self._side: Side | None = None
        self._active_tf = settings.execution_timeframe
        self._plan_entry = 0.0
        self._plan_tp = 0.0
        self._plan_sl = 0.0
        self._explanation: Explanation | None = None
        self._current_symbol = settings.symbol
        self._overlay_prefs_override = None
        self._symbol_blacklist: set[str] = set()

        self.setWindowTitle("Retrade")
        self.resize(1280, 800)
        self.setMinimumSize(960, 600)

        self._chart = ChartWidget(self)
        self._chart.ready.connect(self._on_chart_ready)
        self._chart.levels_changed.connect(self._on_levels_changed)

        self._debrief = DebriefPanel(self)

        self._avatar_btn = QToolButton()
        self._avatar_btn.setObjectName("avatarButton")
        self._avatar_btn.setFixedSize(36, 36)
        self._avatar_btn.setIconSize(QSize(36, 36))
        self._avatar_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._avatar_btn.clicked.connect(self._open_profile)

        self._name_btn = QPushButton()
        self._name_btn.setObjectName("profileNameButton")
        self._name_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._name_btn.clicked.connect(self._open_profile)
        self._refresh_profile_header()

        self._symbol_label = QLabel(settings.symbol)
        self._symbol_label.setObjectName("symbolLabel")

        self._phase_label = QLabel("Loading…")
        self._phase_label.setObjectName("phaseLabel")

        self._tf_group = QButtonGroup(self)
        self._tf_buttons: dict[str, QPushButton] = {}
        tf_row = QHBoxLayout()
        for tf in (settings.execution_timeframe, *settings.context_timeframes):
            btn = QPushButton(tf.upper())
            btn.setCheckable(True)
            btn.setObjectName("tfButton")
            btn.clicked.connect(lambda _=False, t=tf: self._on_tf_clicked(t))
            self._tf_group.addButton(btn)
            self._tf_buttons[tf] = btn
            tf_row.addWidget(btn)
        self._tf_buttons[settings.execution_timeframe].setChecked(True)
        tf_row.addStretch(1)

        self._indicators_btn = QToolButton()
        self._indicators_btn.setText("Indicators ▾")
        self._indicators_btn.setObjectName("indicatorsButton")
        self._indicators_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._indicators_menu = QMenu(self)
        self._act_bos = QAction("BOS / CHoCH", self)
        self._act_bos.setCheckable(True)
        self._act_fvg = QAction("FVG", self)
        self._act_fvg.setCheckable(True)
        self._act_levels = QAction("Levels (nearest)", self)
        self._act_levels.setCheckable(True)
        self._act_swings = QAction("Swings (5)", self)
        self._act_swings.setCheckable(True)
        ind = self._ui_prefs.prefs.indicators
        self._act_bos.setChecked(ind.show_bos)
        self._act_fvg.setChecked(ind.show_fvg)
        self._act_levels.setChecked(ind.show_levels)
        self._act_swings.setChecked(ind.show_swings)
        self._act_bos.toggled.connect(lambda v: self._on_indicator_toggled("bos", v))
        self._act_fvg.toggled.connect(lambda v: self._on_indicator_toggled("fvg", v))
        self._act_levels.toggled.connect(
            lambda v: self._on_indicator_toggled("levels", v)
        )
        self._act_swings.toggled.connect(
            lambda v: self._on_indicator_toggled("swings", v)
        )
        self._indicators_menu.addAction(self._act_bos)
        self._indicators_menu.addAction(self._act_fvg)
        self._indicators_menu.addAction(self._act_levels)
        self._indicators_menu.addAction(self._act_swings)
        self._indicators_btn.setMenu(self._indicators_menu)

        self._indicator_settings_btn = QToolButton()
        self._indicator_settings_btn.setObjectName("indicatorSettingsButton")
        self._indicator_settings_btn.setText("⚙")
        self._indicator_settings_btn.setToolTip("Настройки визуала индикаторов")
        self._indicator_settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._indicator_settings_btn.clicked.connect(self._open_indicator_settings)

        indicators_wrap = QWidget()
        indicators_wrap.setObjectName("indicatorsWrap")
        indicators_layout = QHBoxLayout(indicators_wrap)
        indicators_layout.setContentsMargins(0, 0, 0, 0)
        indicators_layout.setSpacing(0)
        indicators_layout.addWidget(self._indicators_btn)
        indicators_layout.addWidget(self._indicator_settings_btn)

        self._btn_long = QPushButton("LONG")
        self._btn_short = QPushButton("SHORT")
        self._btn_skip = QPushButton("Ничего не делать")
        self._btn_confirm = QPushButton("Подтвердить")
        self._btn_exit = QPushButton("EXIT")
        self._btn_keep = QPushButton("KEEP")
        self._btn_step = QPushButton("+1 свеча")
        self._btn_next = QPushButton("Следующая симуляция")
        self._btn_long.setObjectName("longButton")
        self._btn_short.setObjectName("shortButton")
        self._btn_skip.setObjectName("skipButton")
        self._btn_confirm.setObjectName("confirmButton")
        self._btn_exit.setObjectName("exitButton")
        self._btn_keep.setObjectName("keepButton")
        self._btn_step.setObjectName("stepButton")
        self._btn_next.setObjectName("nextButton")

        self._btn_long.clicked.connect(lambda: self._on_side(Side.LONG))
        self._btn_short.clicked.connect(lambda: self._on_side(Side.SHORT))
        self._btn_skip.clicked.connect(self._on_skip)
        self._btn_confirm.clicked.connect(self._on_confirm)
        self._btn_exit.clicked.connect(self._on_exit)
        self._btn_keep.clicked.connect(self._on_keep)
        self._btn_step.clicked.connect(self._on_step_candle)
        self._btn_next.clicked.connect(self._start_new_round)

        self._tp_spin = QDoubleSpinBox()
        self._sl_spin = QDoubleSpinBox()
        for spin in (self._tp_spin, self._sl_spin):
            spin.setDecimals(8)
            spin.setRange(1e-12, 10_000_000.0)
            spin.setSingleStep(1.0)
            spin.setGroupSeparatorShown(False)
            spin.valueChanged.connect(self._on_spin_changed)
        self._tp_spin.setPrefix("TP ")
        self._sl_spin.setPrefix("SL ")

        action_row = QHBoxLayout()
        action_row.addWidget(self._btn_long)
        action_row.addWidget(self._btn_short)
        action_row.addWidget(self._btn_skip)
        action_row.addSpacing(12)
        action_row.addWidget(self._sl_spin)
        action_row.addWidget(self._tp_spin)
        action_row.addWidget(self._btn_confirm)
        action_row.addWidget(self._btn_exit)
        action_row.addWidget(self._btn_keep)
        action_row.addWidget(self._btn_step)
        action_row.addWidget(self._btn_next)
        action_row.addStretch(1)

        header = QHBoxLayout()
        header.addWidget(self._avatar_btn)
        header.addWidget(self._name_btn)
        header.addSpacing(16)
        header.addWidget(self._symbol_label)
        header.addSpacing(16)
        header.addLayout(tf_row)
        header.addWidget(indicators_wrap)
        header.addWidget(self._phase_label)

        root = QVBoxLayout()
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)
        root.addLayout(header)
        root.addWidget(self._chart, stretch=1)
        root.addWidget(self._debrief)
        root.addLayout(action_row)

        self._content = QWidget(self)
        self._content.setObjectName("mainContent")
        self._content.setLayout(root)

        central = QWidget(self)
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self._content)
        self.setCentralWidget(central)

        self._loading_overlay = LoadingOverlay(central)
        central.installEventFilter(self)
        self.setStatusBar(QStatusBar(self))
        self.statusBar().showMessage("Initializing…")

        self._timer = QTimer(self)
        self._timer.setInterval(settings.playback_interval_ms)
        self._timer.timeout.connect(self._on_playback_tick)

        self._apply_style()
        self._set_phase(UiPhase.LOADING)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background-color: #0f1219;
                color: #d1d4dc;
            }
            QLabel#symbolLabel {
                font-size: 18px;
                font-weight: 700;
                color: #f0f3fa;
            }
            QLabel#phaseLabel {
                color: #787b86;
            }
            QPushButton#profileNameButton {
                background: transparent;
                border: none;
                color: #f0f3fa;
                font-weight: 600;
                padding: 4px 8px;
            }
            QPushButton#profileNameButton:hover {
                color: #2962ff;
            }
            QToolButton#avatarButton {
                border: 1px solid #2a2e39;
                border-radius: 18px;
                background: #1e222d;
                padding: 0;
            }
            QToolButton#indicatorsButton {
                background-color: #1e222d;
                border: 1px solid #2a2e39;
                border-right: none;
                border-top-left-radius: 4px;
                border-bottom-left-radius: 4px;
                border-top-right-radius: 0;
                border-bottom-right-radius: 0;
                padding: 6px 10px;
            }
            QToolButton#indicatorSettingsButton {
                background-color: #1e222d;
                border: 1px solid #2a2e39;
                border-top-left-radius: 0;
                border-bottom-left-radius: 0;
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
                padding: 6px 10px;
                min-width: 28px;
                color: #b2b5be;
            }
            QToolButton#indicatorSettingsButton:hover {
                color: #f0f3fa;
                background-color: #2a2e39;
            }
            QPushButton {
                background-color: #1e222d;
                border: 1px solid #2a2e39;
                border-radius: 4px;
                padding: 8px 14px;
                min-height: 28px;
            }
            QPushButton:hover { background-color: #2a2e39; }
            QPushButton:checked {
                background-color: #2962ff;
                border-color: #2962ff;
                color: #ffffff;
            }
            QPushButton:disabled { color: #5d606b; }
            QPushButton#longButton { color: #26a69a; font-weight: 700; }
            QPushButton#shortButton { color: #ef5350; font-weight: 700; }
            QPushButton#confirmButton {
                background-color: #2962ff;
                border-color: #2962ff;
                color: #ffffff;
                font-weight: 700;
            }
            QPushButton#exitButton {
                background-color: #ef5350;
                border-color: #ef5350;
                color: #ffffff;
                font-weight: 700;
            }
            QPushButton#keepButton {
                background-color: #26a69a;
                border-color: #26a69a;
                color: #ffffff;
                font-weight: 700;
            }
            QPushButton#nextButton {
                background-color: #363a45;
                font-weight: 700;
            }
            QDoubleSpinBox {
                background-color: #1e222d;
                border: 1px solid #2a2e39;
                border-radius: 4px;
                padding: 6px;
                min-width: 140px;
            }
            QStatusBar {
                background-color: #0f1219;
                color: #787b86;
            }
            """
        )
        font = QFont("Segoe UI", 10)
        self.setFont(font)

    def _refresh_profile_header(self) -> None:
        profile = self._profile.profile
        self._name_btn.setText(profile.display_name)
        path = profile.resolved_avatar(_DEFAULT_AVATAR)
        pix = QPixmap(str(path))
        if not pix.isNull():
            scaled = pix.scaled(
                36,
                36,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._avatar_btn.setIcon(QIcon(scaled))

    def _open_profile(self) -> None:
        dialog = ProfileDialog(self._profile, _DEFAULT_AVATAR, self)
        if dialog.exec():
            self._refresh_profile_header()

    def _open_indicator_settings(self) -> None:
        dialog = IndicatorStyleDialog(self._ui_prefs, self)
        dialog.preview_changed.connect(self._on_indicator_style_preview)
        result = dialog.exec()
        self._overlay_prefs_override = None
        if result:
            self._apply_indicator_overlays()
        else:
            self._apply_indicator_overlays()

    def _on_indicator_style_preview(self, prefs: object) -> None:
        self._overlay_prefs_override = prefs
        self._apply_indicator_overlays()

    def _indicator_prefs(self):
        if self._overlay_prefs_override is not None:
            return self._overlay_prefs_override
        return self._ui_prefs.prefs.indicators

    def _on_indicator_toggled(self, key: str, value: bool) -> None:
        self._ui_prefs.set_indicator(key, value)
        self._apply_indicator_overlays()

    def _ref_price_for_overlays(self) -> float | None:
        if self._playback is not None and self._playback.plan is not None:
            return self._playback.plan.entry
        if self._session is not None:
            return self._session.entry_price
        return None

    def _current_series(self):
        if self._session is None:
            return None
        if self._playback is not None:
            return self._playback.series_for(self._active_tf)
        return self._session.series_for(self._active_tf)

    def _apply_indicator_overlays(self) -> None:
        """Pre-trade / live indicator overlays from visible series + prefs."""
        if self._session is None:
            return
        if self._phase is UiPhase.RESULT and self._explanation is not None:
            self._apply_overlays_for_tf(self._active_tf)
            return
        if self._phase is UiPhase.LOADING:
            return
        series = self._current_series()
        if series is None:
            return
        structure = analyze_series(series, swing_strength=2)
        self._chart.set_overlays(
            structure_to_overlays(
                structure,
                prefs=self._indicator_prefs(),
                ref_price=self._ref_price_for_overlays(),
            )
        )

    def _on_chart_ready(self) -> None:
        self._start_new_round()

    def eventFilter(self, watched: object, event: QEvent) -> bool:  # noqa: N802
        if (
            watched is self.centralWidget()
            and event.type() is QEvent.Type.Resize
            and self._loading_overlay is not None
        ):
            central = self.centralWidget()
            if central is not None:
                self._loading_overlay.setGeometry(central.rect())
        return super().eventFilter(watched, event)

    def _set_loading(self, enabled: bool, message: str = "Загрузка…") -> None:
        apply_content_blur(self._content, enabled=enabled, radius=12)
        if enabled:
            central = self.centralWidget()
            if central is not None:
                self._loading_overlay.setGeometry(central.rect())
            self._loading_overlay.show_loading(message)
            app = QApplication.instance()
            if app is not None:
                app.processEvents()
        else:
            self._loading_overlay.hide_loading()

    def _start_new_round(self) -> None:
        self._timer.stop()
        self._playback = None
        self._side = None
        self._explanation = None
        self._debrief.clear()
        self._chart.clear_overlays()
        self._set_phase(UiPhase.LOADING)
        self._set_loading(True, "Подбор монеты…")
        self.statusBar().showMessage("Selecting symbol and historical window…")
        QTimer.singleShot(0, self._load_scenario)

    def _load_scenario(self) -> None:
        symbol: str | None = None
        try:
            self._set_loading(True, "Загрузка данных…")
            self._universe.ensure_loaded()
            symbol = pick_symbol(
                self._universe,
                self._history,
                exclude=self._symbol_blacklist,
            )
            self._current_symbol = symbol
            self._symbol_label.setText(symbol)
            self.setWindowTitle(f"Retrade — {symbol}")
            self._set_loading(True, f"Загрузка {symbol}…")
            self.statusBar().showMessage(f"Loading {symbol}…")

            scenario = build_scenario(
                self._market,
                symbol=symbol,
                execution_timeframe=self._settings.execution_timeframe,
                context_timeframes=self._settings.context_timeframes,
                history=self._history,
                history_lookback_days=self._settings.history_lookback_days,
                max_window_attempts=3,
            )
        except Exception as exc:  # noqa: BLE001 - show to user in prototype
            logger.exception("Failed to build scenario")
            if symbol:
                self._symbol_blacklist.add(symbol)
                logger.info(
                    "Blacklisted %s for this session (%s symbols)",
                    symbol,
                    len(self._symbol_blacklist),
                )
            self._set_loading(False)
            exhausted = "Нет доступных монет" in str(exc)
            QMessageBox.critical(
                self,
                "Retrade",
                f"Не удалось загрузить данные"
                f"{f' для {symbol}' if symbol else ''}:\n{exc}"
                + (
                    "\n\nБольше нет монет для попытки в этой сессии."
                    if exhausted
                    else "\n\nПопробуем другую монету."
                ),
            )
            if exhausted:
                self._set_phase(UiPhase.RESULT)
                return
            # Another coin available?
            try:
                pick_symbol(
                    self._universe,
                    self._history,
                    exclude=self._symbol_blacklist,
                )
            except Exception:  # noqa: BLE001
                self._set_phase(UiPhase.RESULT)
                return
            QTimer.singleShot(0, self._start_new_round)
            return

        self._session = RoundSession(scenario=scenario)
        self._active_tf = self._settings.execution_timeframe
        self._tf_buttons[self._active_tf].setChecked(True)
        # fit=True recreates the series in JS (drops previous price scale).
        self._refresh_chart(fit=True)
        self._set_phase(UiPhase.DECIDE)
        self._apply_indicator_overlays()
        self._set_loading(False)
        self.statusBar().showMessage(
            f"{scenario.symbol} | score {scenario.score:.1f}"
            f" [{', '.join(scenario.score_reasons) or '—'}] | "
            f"visible {len(scenario.visible_execution)} | "
            f"hidden {len(scenario.hidden_execution)} | entry "
            f"{scenario.entry_price:.{price_decimals(scenario.entry_price)}f}"
        )

    def _refresh_chart(self, *, fit: bool) -> None:
        if self._session is None:
            return
        series = self._current_series()
        if series is None:
            return
        self._chart.set_candles(list(series.candles), fit=fit)
        self._chart.set_hud(
            f"{self._current_symbol}  {self._active_tf.upper()}"
        )
        if self._phase is UiPhase.RESULT and self._explanation is not None:
            self._apply_overlays_for_tf(self._active_tf)
        elif self._phase in {UiPhase.DECIDE, UiPhase.PLACE_ORDERS}:
            self._apply_indicator_overlays()

    def _apply_overlays_for_tf(self, timeframe: str) -> None:
        if self._explanation is None:
            return
        prefs = self._indicator_prefs()
        ref = self._ref_price_for_overlays()
        if timeframe == self._settings.execution_timeframe:
            self._chart.set_overlays(
                structure_to_overlays(
                    self._explanation.execution_map,
                    prefs=prefs,
                    ref_price=ref,
                )
            )
            return
        context = self._explanation.context_map
        if context is not None and context.timeframe == timeframe:
            self._chart.set_overlays(
                structure_to_overlays(context, prefs=prefs, ref_price=ref)
            )
            return
        if self._playback is not None:
            series = self._playback.series_for(timeframe)
        elif self._session is not None:
            series = self._session.series_for(timeframe)
        else:
            return
        self._chart.set_overlays(
            structure_to_overlays(
                analyze_series(series, swing_strength=2),
                prefs=prefs,
                ref_price=ref,
            )
        )

    def _on_tf_clicked(self, timeframe: str) -> None:
        self._active_tf = timeframe
        # Always fit on TF change so price axis matches the new series range.
        self._refresh_chart(fit=True)

    def _configure_price_spins(self, entry: float) -> None:
        decimals = price_decimals(entry)
        step = price_step(entry)
        minimum = min(10 ** (-(decimals + 2)), entry / 1_000_000)
        minimum = max(minimum, 1e-12)
        maximum = max(entry * 1_000, 1.0)
        for spin in (self._tp_spin, self._sl_spin):
            spin.setDecimals(decimals)
            spin.setRange(minimum, maximum)
            spin.setSingleStep(step)

    def _on_side(self, side: Side) -> None:
        if self._session is None or self._phase not in {
            UiPhase.DECIDE,
            UiPhase.PLACE_ORDERS,
        }:
            return
        self._side = side
        entry = self._session.entry_price
        self._plan_entry = entry
        plan = default_plan(side, entry)
        self._plan_tp = plan.take_profit
        self._plan_sl = plan.stop_loss
        decimals = price_decimals(entry)
        self._configure_price_spins(entry)
        self._tp_spin.blockSignals(True)
        self._sl_spin.blockSignals(True)
        self._tp_spin.setValue(plan.take_profit)
        self._sl_spin.setValue(plan.stop_loss)
        self._tp_spin.blockSignals(False)
        self._sl_spin.blockSignals(False)
        self._chart.set_trade_levels(
            entry=entry,
            take_profit=plan.take_profit,
            stop_loss=plan.stop_loss,
            editable=True,
        )
        self._set_phase(UiPhase.PLACE_ORDERS)
        self._apply_indicator_overlays()
        self.statusBar().showMessage(
            f"{side.value.upper()} @ {entry:.{decimals}f} — "
            "растяни TP/SL на графике или измени значения, затем подтверди"
        )

    def _on_skip(self) -> None:
        if self._session is None or self._phase is not UiPhase.DECIDE:
            return
        self._playback = self._session.start_skip()
        self._chart.clear_trade_levels()
        self._finish_with_outcome(TradeOutcome.SKIP)

    def _current_plan(self) -> TradePlan | None:
        if self._side is None:
            return None
        return TradePlan(
            side=self._side,
            entry=self._plan_entry,
            take_profit=self._plan_tp,
            stop_loss=self._plan_sl,
        )

    def _on_spin_changed(self, _value: float) -> None:
        if self._phase is not UiPhase.PLACE_ORDERS or self._side is None:
            return
        self._plan_tp = float(self._tp_spin.value())
        self._plan_sl = float(self._sl_spin.value())
        self._chart.set_trade_levels(
            entry=self._plan_entry,
            take_profit=self._plan_tp,
            stop_loss=self._plan_sl,
            editable=True,
        )

    def _on_levels_changed(self, entry: float, tp: float, sl: float) -> None:
        if self._phase is not UiPhase.PLACE_ORDERS:
            return
        self._plan_entry = entry
        self._plan_tp = tp
        self._plan_sl = sl
        self._configure_price_spins(entry)
        self._tp_spin.blockSignals(True)
        self._sl_spin.blockSignals(True)
        self._tp_spin.setValue(tp)
        self._sl_spin.setValue(sl)
        self._tp_spin.blockSignals(False)
        self._sl_spin.blockSignals(False)

    def _on_confirm(self) -> None:
        if self._session is None or self._phase is not UiPhase.PLACE_ORDERS:
            return
        plan = self._current_plan()
        if plan is None:
            return
        try:
            plan.validate()
        except ValueError as exc:
            QMessageBox.warning(self, "Retrade", str(exc))
            return

        self._playback = self._session.start_trade(plan)
        # Stay on the TF where the user confirmed (hit-detection still uses 15m).
        if self._active_tf in self._tf_buttons:
            self._tf_buttons[self._active_tf].setChecked(True)
        self._refresh_chart(fit=True)
        self._chart.set_trade_levels(
            entry=plan.entry,
            take_profit=plan.take_profit,
            stop_loss=plan.stop_loss,
            editable=False,
        )
        self._set_phase(UiPhase.PLAYBACK)
        self.statusBar().showMessage(
            f"Playback… ({self._active_tf.upper()}, hits on "
            f"{self._settings.execution_timeframe.upper()})"
        )
        self._timer.start()

    def _on_playback_tick(self) -> None:
        if self._playback is None:
            self._timer.stop()
            return

        before = self._playback.shown_hidden
        result = self._playback.step(
            hold_check_bars=self._settings.hold_check_bars
        )
        use_update = (
            self._active_tf == self._settings.execution_timeframe
            and self._playback.shown_hidden > before
        )
        # Exec TF: append bar. Higher TF: rebuild series (partial candle grows).
        if use_update:
            candle = self._playback.scenario.hidden_execution[before]
            self._chart.update_candle(candle)
        else:
            self._refresh_chart(fit=False)
            if self._playback.plan is not None:
                self._chart.set_trade_levels(
                    entry=self._playback.plan.entry,
                    take_profit=self._playback.plan.take_profit,
                    stop_loss=self._playback.plan.stop_loss,
                    editable=False,
                )

        if result is None:
            self.statusBar().showMessage(
                f"Playback bar {self._playback.shown_hidden}/"
                f"{len(self._playback.scenario.hidden_execution)}"
            )
            return

        if result.hold:
            self._timer.stop()
            if self._session is not None:
                self._session.sync_revealed_from_playback()
            self._set_phase(UiPhase.HOLD)
            n = self._settings.hold_check_bars
            progress = self._playback.shown_hidden - self._playback.hold_anchor
            self.statusBar().showMessage(
                f"Пауза после {progress} свечей сделки "
                f"(каждые {n}) — EXIT или KEEP"
            )
            return

        self._timer.stop()
        if self._session is not None:
            self._session.sync_revealed_from_playback()
        self._finish_with_outcome(result.outcome)

    def _on_exit(self) -> None:
        if self._playback is None or self._phase is not UiPhase.HOLD:
            return
        result = self._playback.exit_at_market()
        if self._session is not None:
            self._session.sync_revealed_from_playback()
        self._finish_with_outcome(result.outcome)

    def _on_keep(self) -> None:
        if self._playback is None or self._phase is not UiPhase.HOLD:
            return
        self._playback.continue_after_hold()
        self._set_phase(UiPhase.PLAYBACK)
        self.statusBar().showMessage("Playback… KEEP")
        self._timer.start()

    def _on_step_candle(self) -> None:
        if self._session is None:
            return
        if self._phase in {UiPhase.DECIDE, UiPhase.PLACE_ORDERS}:
            self._step_pretrade()
            return
        if self._playback is None or self._phase is not UiPhase.RESULT:
            return
        before = self._playback.shown_hidden
        candle = self._playback.reveal_only()
        if candle is None:
            self._btn_step.setEnabled(False)
            return
        self._session.sync_revealed_from_playback()
        use_update = self._active_tf == self._settings.execution_timeframe
        if use_update:
            self._chart.update_candle(
                self._playback.scenario.hidden_execution[before]
            )
        else:
            self._refresh_chart(fit=False)
        if self._playback.plan is not None:
            self._chart.set_trade_levels(
                entry=self._playback.plan.entry,
                take_profit=self._playback.plan.take_profit,
                stop_loss=self._playback.plan.stop_loss,
                editable=False,
            )
        self._apply_overlays_for_tf(self._active_tf)
        self._btn_step.setEnabled(self._playback.can_reveal_more)
        self.statusBar().showMessage(
            f"+1 свеча · {self._playback.shown_hidden}/"
            f"{len(self._playback.scenario.hidden_execution)}"
        )

    def _step_pretrade(self) -> None:
        if self._session is None:
            return
        before = self._session.revealed
        candle = self._session.advance_one()
        if candle is None:
            self._btn_step.setEnabled(False)
            return

        use_update = self._active_tf == self._settings.execution_timeframe
        if use_update:
            self._chart.update_candle(
                self._session.scenario.hidden_execution[before]
            )
        else:
            self._refresh_chart(fit=False)

        if self._phase is UiPhase.PLACE_ORDERS and self._side is not None:
            old_entry = self._plan_entry
            new_entry = self._session.entry_price
            delta = new_entry - old_entry
            self._plan_entry = new_entry
            self._plan_tp += delta
            self._plan_sl += delta
            self._configure_price_spins(new_entry)
            self._tp_spin.blockSignals(True)
            self._sl_spin.blockSignals(True)
            self._tp_spin.setValue(self._plan_tp)
            self._sl_spin.setValue(self._plan_sl)
            self._tp_spin.blockSignals(False)
            self._sl_spin.blockSignals(False)
            self._chart.set_trade_levels(
                entry=self._plan_entry,
                take_profit=self._plan_tp,
                stop_loss=self._plan_sl,
                editable=True,
            )

        self._apply_indicator_overlays()
        self._btn_step.setEnabled(self._session.can_advance)
        entry = self._session.entry_price
        self.statusBar().showMessage(
            f"+1 свеча · {self._session.revealed}/"
            f"{len(self._session.scenario.hidden_execution)} · "
            f"entry {entry:.{price_decimals(entry)}f}"
        )

    def _finish_with_outcome(self, outcome: TradeOutcome) -> None:
        self._set_phase(UiPhase.RESULT)
        text = _OUTCOME_TEXT.get(outcome, outcome.value)
        self._phase_label.setText(text)
        self.statusBar().showMessage(f"Результат: {text}")

        plan = self._playback.plan if self._playback is not None else None
        candle_close = (
            self._playback.result_candle.close
            if self._playback is not None and self._playback.result_candle is not None
            else None
        )
        if (
            candle_close is None
            and self._playback is not None
            and self._playback.shown_hidden
        ):
            candle_close = self._playback.scenario.hidden_execution[
                self._playback.shown_hidden - 1
            ].close
        exit_px = exit_price_for_outcome(outcome, plan, candle_close)
        realized_r = self._profile.record_trade(
            outcome=outcome,
            plan=plan,
            exit_price=exit_px,
        )
        self._refresh_profile_header()

        if self._session is not None:
            if self._playback is not None:
                execution = self._playback.series_for(
                    self._settings.execution_timeframe
                )
                context_tf = (
                    self._settings.context_timeframes[-1]
                    if self._settings.context_timeframes
                    else None
                )
                context = (
                    self._playback.series_for(context_tf)
                    if context_tf is not None
                    else None
                )
            else:
                execution = self._session.scenario.visible_execution
                context = None

            explanation = build_explanation(
                execution_series=execution,
                context_series=context,
                outcome=outcome,
                plan=plan,
                prefs=self._indicator_prefs(),
            )
            self._explanation = explanation
            self._debrief.show_explanation(explanation)
            self._refresh_chart(fit=True)
            self._apply_overlays_for_tf(self._active_tf)
            if self._playback is not None and self._playback.plan is not None:
                self._chart.set_trade_levels(
                    entry=self._playback.plan.entry,
                    take_profit=self._playback.plan.take_profit,
                    stop_loss=self._playback.plan.stop_loss,
                    editable=False,
                )

        r_note = f" · R {realized_r:+.2f}" if realized_r is not None else ""
        self.statusBar().showMessage(f"Результат: {text}{r_note}")

        can_step = (
            self._playback is not None
            and self._playback.can_reveal_more
            and outcome is not TradeOutcome.SKIP
        )
        self._btn_step.setEnabled(bool(can_step))

        if outcome is TradeOutcome.AMBIGUOUS:
            QMessageBox.information(
                self,
                "Ничья",
                "На одной 15M-свече задеты и TP, и SL.\n"
                "По OHLC порядок касания неизвестен — засчитываем ничью.",
            )

    def _set_phase(self, phase: UiPhase) -> None:
        self._phase = phase
        decide = phase is UiPhase.DECIDE
        place = phase is UiPhase.PLACE_ORDERS
        result = phase is UiPhase.RESULT
        loading = phase is UiPhase.LOADING
        playback = phase is UiPhase.PLAYBACK
        hold = phase is UiPhase.HOLD

        self._btn_long.setEnabled(decide or place)
        self._btn_short.setEnabled(decide or place)
        self._btn_skip.setEnabled(decide)
        self._btn_confirm.setEnabled(place)
        self._btn_exit.setVisible(hold)
        self._btn_keep.setVisible(hold)
        self._btn_exit.setEnabled(hold)
        self._btn_keep.setEnabled(hold)

        show_step = decide or place or result
        self._btn_step.setVisible(show_step)
        if decide or place:
            can_step = self._session is not None and self._session.can_advance
        elif result:
            can_step = (
                self._playback is not None
                and self._playback.can_reveal_more
                and self._playback.outcome is not TradeOutcome.SKIP
            )
        else:
            can_step = False
        self._btn_step.setEnabled(bool(can_step))
        self._btn_next.setEnabled(result or (not loading and not playback and not hold))
        self._tp_spin.setEnabled(place)
        self._sl_spin.setEnabled(place)
        for btn in self._tf_buttons.values():
            btn.setEnabled(not loading and not playback and not hold)

        labels = {
            UiPhase.LOADING: "Loading…",
            UiPhase.DECIDE: "Выбери действие",
            UiPhase.PLACE_ORDERS: "Выставь TP / SL",
            UiPhase.PLAYBACK: "Playback…",
            UiPhase.HOLD: "EXIT / KEEP",
            UiPhase.RESULT: "Результат",
        }
        if phase is not UiPhase.RESULT:
            self._phase_label.setText(labels[phase])
