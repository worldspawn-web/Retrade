"""Main application window for the Retrade prototype."""

from __future__ import annotations

import logging
from enum import Enum, auto
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt, QThread, QTimer
from PySide6.QtGui import QAction, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDoubleSpinBox,
    QFrame,
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
from retrade.domain.scenario import RoundScenario, pick_symbol
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
from retrade.ui import theme
from retrade.ui.debrief_panel import DebriefPanel
from retrade.ui.indicator_style_dialog import IndicatorStyleDialog
from retrade.ui.loading_overlay import LoadingOverlay, apply_content_blur
from retrade.ui.profile_dialog import ProfileDialog
from retrade.ui.scenario_load_worker import ScenarioLoadWorker
from retrade.ui.sounds import SoundPlayer
from retrade.ui.toast import ToastHost, ToastKind

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
        self._load_thread: QThread | None = None
        self._load_worker: ScenarioLoadWorker | None = None

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

        self._symbol_label = QLabel(settings.symbol)
        self._symbol_label.setObjectName("symbolBadge")

        self._phase_label = QLabel("Loading…")
        self._phase_label.setObjectName("phaseBadge")

        self._stats_badge = QLabel("—")
        self._stats_badge.setObjectName("statsBadge")
        self._stats_badge.setToolTip("Σ R · winrate · сделок")
        self._refresh_profile_header()

        self._tf_group = QButtonGroup(self)
        self._tf_group.setExclusive(True)
        self._tf_buttons: dict[str, QToolButton] = {}
        tf_wrap = QFrame()
        tf_wrap.setObjectName("tfSegment")
        tf_row = QHBoxLayout(tf_wrap)
        tf_row.setContentsMargins(0, 0, 0, 0)
        tf_row.setSpacing(0)
        for tf in (settings.execution_timeframe, *settings.context_timeframes):
            btn = QToolButton()
            btn.setText(tf.upper())
            btn.setCheckable(True)
            btn.setObjectName("tfButton")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, t=tf: self._on_tf_clicked(t))
            self._tf_group.addButton(btn)
            self._tf_buttons[tf] = btn
            tf_row.addWidget(btn)
        self._tf_buttons[settings.execution_timeframe].setChecked(True)

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

        order_group = QFrame()
        order_group.setObjectName("orderGroup")
        order_layout = QHBoxLayout(order_group)
        order_layout.setContentsMargins(8, 4, 8, 4)
        order_layout.setSpacing(8)
        order_layout.addWidget(self._sl_spin)
        order_layout.addWidget(self._tp_spin)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        action_row.addWidget(self._btn_long)
        action_row.addWidget(self._btn_short)
        action_row.addWidget(self._btn_skip)
        action_row.addSpacing(8)
        action_row.addWidget(order_group)
        action_row.addWidget(self._btn_confirm)
        action_row.addWidget(self._btn_exit)
        action_row.addWidget(self._btn_keep)
        action_row.addWidget(self._btn_step)
        action_row.addWidget(self._btn_next)
        action_row.addStretch(1)

        header = QHBoxLayout()
        header.setSpacing(10)
        header.addWidget(self._avatar_btn)
        header.addWidget(self._name_btn)
        header.addSpacing(8)
        header.addWidget(self._symbol_label)
        header.addSpacing(8)
        header.addWidget(tf_wrap)
        header.addWidget(indicators_wrap)
        header.addStretch(1)
        header.addWidget(self._phase_label)
        header.addWidget(self._stats_badge)

        root = QVBoxLayout()
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(10)
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
        self._toast = ToastHost(central)
        self._sounds = SoundPlayer()
        self._sounds.set_enabled(self._ui_prefs.prefs.sounds_enabled)
        central.installEventFilter(self)
        self.setStatusBar(QStatusBar(self))
        self.statusBar().showMessage("Initializing…")

        self._timer = QTimer(self)
        self._timer.setInterval(settings.playback_interval_ms)
        self._timer.timeout.connect(self._on_playback_tick)

        self._apply_style()
        self._refresh_stats_badge()
        self._set_phase(UiPhase.LOADING)

    def _apply_style(self) -> None:
        self.setStyleSheet(theme.app_stylesheet())
        font = QFont("Segoe UI", 10)
        self.setFont(font)

    def _notify(
        self,
        title: str,
        body: str = "",
        *,
        kind: ToastKind = ToastKind.INFO,
        sound: str | None = None,
        msec: int = 3200,
    ) -> None:
        self._toast.show_toast(title, body, kind=kind, msec=msec)
        if sound:
            self._sounds.play(sound)

    def _refresh_stats_badge(self) -> None:
        if not hasattr(self, "_stats_badge"):
            return
        stats = self._profile.profile.stats
        wr = stats.winrate
        wr_text = f"{wr * 100:.0f}%" if wr is not None else "—"
        self._stats_badge.setText(
            f"ΣR {stats.sum_r:+.1f} · {wr_text} · {stats.trades}"
        )

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
        self._refresh_stats_badge()

    def _open_profile(self) -> None:
        dialog = ProfileDialog(
            self._profile,
            _DEFAULT_AVATAR,
            self,
            ui_prefs=self._ui_prefs,
        )
        if dialog.exec():
            self._sounds.set_enabled(self._ui_prefs.prefs.sounds_enabled)
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
        ):
            central = self.centralWidget()
            if central is not None:
                if self._loading_overlay is not None:
                    self._loading_overlay.setGeometry(central.rect())
                self._toast.resize_to_parent()
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
        QTimer.singleShot(0, self._start_scenario_load)

    def _start_scenario_load(self) -> None:
        if self._load_thread is not None and self._load_thread.isRunning():
            return

        worker = ScenarioLoadWorker(
            market=self._market,
            universe=self._universe,
            history=self._history,
            settings=self._settings,
            blacklist=frozenset(self._symbol_blacklist),
        )
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_load_progress)
        worker.finished.connect(self._on_load_finished)
        worker.failed.connect(self._on_load_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_load_thread_finished)

        self._load_worker = worker
        self._load_thread = thread
        thread.start()

    def _on_load_progress(self, message: str) -> None:
        self._loading_overlay.set_message(message)
        if not self._loading_overlay.isVisible():
            self._set_loading(True, message)
        self.statusBar().showMessage(message)

    def _on_load_finished(self, scenario: object) -> None:
        if not isinstance(scenario, RoundScenario):
            self._on_load_failed("", "Некорректный ответ загрузчика")
            return

        self._current_symbol = scenario.symbol
        self._symbol_label.setText(scenario.symbol)
        self.setWindowTitle(f"Retrade — {scenario.symbol}")
        self._session = RoundSession(scenario=scenario)
        self._active_tf = self._settings.execution_timeframe
        self._tf_buttons[self._active_tf].setChecked(True)
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

    def _on_load_failed(self, symbol: str, error: str) -> None:
        logger.error("Scenario load failed for %s: %s", symbol or "?", error)
        if symbol:
            self._symbol_blacklist.add(symbol)
            logger.info(
                "Blacklisted %s for this session (%s symbols)",
                symbol,
                len(self._symbol_blacklist),
            )
        self._set_loading(False)
        exhausted = "Нет доступных монет" in error
        detail = (
            f"Не удалось загрузить данные"
            f"{f' для {symbol}' if symbol else ''}: {error}"
        )
        if exhausted:
            QMessageBox.critical(
                self,
                "Retrade",
                f"{detail}\n\nБольше нет монет для попытки в этой сессии.",
            )
            self._set_phase(UiPhase.RESULT)
            return

        self._notify(
            "Повтор загрузки",
            "Попробуем другую монету.",
            kind=ToastKind.WARN,
            sound="error",
            msec=2800,
        )
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

    def _on_load_thread_finished(self) -> None:
        self._load_thread = None
        self._load_worker = None

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
            self._notify(str(exc), kind=ToastKind.WARN, sound="error", msec=2500)
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
            self._notify(
                "HOLD",
                f"После {progress} свечей — EXIT или KEEP",
                kind=ToastKind.INFO,
                sound="hold",
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
        self._emit_outcome_feedback(outcome, text, realized_r)

        can_step = (
            self._playback is not None
            and self._playback.can_reveal_more
            and outcome is not TradeOutcome.SKIP
        )
        self._btn_step.setEnabled(bool(can_step))

    def _emit_outcome_feedback(
        self,
        outcome: TradeOutcome,
        text: str,
        realized_r: float | None,
    ) -> None:
        body = text if realized_r is None else f"{text} · R {realized_r:+.2f}"
        if outcome is TradeOutcome.TAKE_PROFIT:
            self._notify("Take Profit", body, kind=ToastKind.SUCCESS, sound="tp")
        elif outcome is TradeOutcome.STOP_LOSS:
            self._notify("Stop Loss", body, kind=ToastKind.ERROR, sound="sl")
        elif outcome is TradeOutcome.AMBIGUOUS:
            self._notify(
                "Ничья",
                "TP и SL на одной свече — порядок касания неизвестен.",
                kind=ToastKind.WARN,
                sound="exit",
                msec=4000,
            )
        elif outcome is TradeOutcome.SKIP:
            self._notify("Skip", "Сделка пропущена", kind=ToastKind.INFO, msec=2200)
        elif outcome is TradeOutcome.EXIT:
            self._notify("EXIT", body, kind=ToastKind.INFO, sound="exit")
        elif outcome is TradeOutcome.OPEN:
            self._notify("No hit", body, kind=ToastKind.WARN, sound="exit")
        else:
            self._notify(text, body, kind=ToastKind.INFO, sound="exit")

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
