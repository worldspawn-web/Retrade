"""Main application window for the Retrade prototype."""

from __future__ import annotations

import logging
from enum import Enum, auto

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
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
from retrade.domain.round_history import RoundHistory
from retrade.domain.scenario import build_scenario, pick_symbol
from retrade.domain.smc import analyze_series
from retrade.domain.trading import (
    Side,
    TradeOutcome,
    TradePlan,
    default_plan,
)
from retrade.infra.binance import BinanceMarketData
from retrade.infra.symbol_universe import SymbolUniverse
from retrade.ui.debrief_panel import DebriefPanel

logger = logging.getLogger(__name__)


class UiPhase(Enum):
    LOADING = auto()
    DECIDE = auto()
    PLACE_ORDERS = auto()
    PLAYBACK = auto()
    RESULT = auto()


_OUTCOME_TEXT = {
    TradeOutcome.TAKE_PROFIT: "Take Profit",
    TradeOutcome.STOP_LOSS: "Stop Loss",
    TradeOutcome.AMBIGUOUS: "Draw (TP and SL on same bar)",
    TradeOutcome.SKIP: "Skipped",
    TradeOutcome.OPEN: "No hit in scenario tail",
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
        self._session: RoundSession | None = None
        self._playback: PlaybackState | None = None
        self._phase = UiPhase.LOADING
        self._side: Side | None = None
        self._active_tf = settings.execution_timeframe
        self._plan_entry = 0.0
        self._explanation: Explanation | None = None
        self._current_symbol = settings.symbol

        self.setWindowTitle("Retrade")
        self.resize(1280, 800)
        self.setMinimumSize(960, 600)

        self._chart = ChartWidget(self)
        self._chart.ready.connect(self._on_chart_ready)
        self._chart.levels_changed.connect(self._on_levels_changed)

        self._debrief = DebriefPanel(self)

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

        self._btn_long = QPushButton("LONG")
        self._btn_short = QPushButton("SHORT")
        self._btn_skip = QPushButton("Ничего не делать")
        self._btn_confirm = QPushButton("Подтвердить")
        self._btn_next = QPushButton("Следующая симуляция")
        self._btn_long.setObjectName("longButton")
        self._btn_short.setObjectName("shortButton")
        self._btn_skip.setObjectName("skipButton")
        self._btn_confirm.setObjectName("confirmButton")
        self._btn_next.setObjectName("nextButton")

        self._btn_long.clicked.connect(lambda: self._on_side(Side.LONG))
        self._btn_short.clicked.connect(lambda: self._on_side(Side.SHORT))
        self._btn_skip.clicked.connect(self._on_skip)
        self._btn_confirm.clicked.connect(self._on_confirm)
        self._btn_next.clicked.connect(self._start_new_round)

        self._tp_spin = QDoubleSpinBox()
        self._sl_spin = QDoubleSpinBox()
        for spin in (self._tp_spin, self._sl_spin):
            spin.setDecimals(2)
            spin.setRange(0.01, 10_000_000.0)
            spin.setSingleStep(1.0)
            spin.setGroupSeparatorShown(True)
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
        action_row.addWidget(self._btn_next)
        action_row.addStretch(1)

        header = QHBoxLayout()
        header.addWidget(self._symbol_label)
        header.addSpacing(16)
        header.addLayout(tf_row)
        header.addWidget(self._phase_label)

        root = QVBoxLayout()
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)
        root.addLayout(header)
        root.addWidget(self._chart, stretch=1)
        root.addWidget(self._debrief)
        root.addLayout(action_row)

        central = QWidget(self)
        central.setLayout(root)
        self.setCentralWidget(central)
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

    def _on_chart_ready(self) -> None:
        self._start_new_round()

    def _start_new_round(self) -> None:
        self._timer.stop()
        self._playback = None
        self._side = None
        self._explanation = None
        self._debrief.clear()
        self._chart.clear_overlays()
        self._set_phase(UiPhase.LOADING)
        self.statusBar().showMessage("Selecting symbol and historical window…")
        QTimer.singleShot(0, self._load_scenario)

    def _load_scenario(self) -> None:
        try:
            self._universe.ensure_loaded()
            symbol = pick_symbol(self._universe, self._history)
            self._current_symbol = symbol
            self._symbol_label.setText(symbol)
            self.setWindowTitle(f"Retrade — {symbol}")
            self.statusBar().showMessage(f"Loading {symbol}…")

            scenario = build_scenario(
                self._market,
                symbol=symbol,
                execution_timeframe=self._settings.execution_timeframe,
                context_timeframes=self._settings.context_timeframes,
                history=self._history,
                history_lookback_days=self._settings.history_lookback_days,
            )
        except Exception as exc:  # noqa: BLE001 - show to user in prototype
            logger.exception("Failed to build scenario")
            QMessageBox.critical(
                self,
                "Retrade",
                f"Не удалось загрузить данные:\n{exc}",
            )
            self._set_phase(UiPhase.RESULT)
            return

        self._session = RoundSession(scenario=scenario)
        self._active_tf = self._settings.execution_timeframe
        self._tf_buttons[self._active_tf].setChecked(True)
        self._refresh_chart(fit=True)
        self._chart.clear_trade_levels()
        self._chart.clear_overlays()
        self._set_phase(UiPhase.DECIDE)
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
        if self._playback is not None:
            series = self._playback.series_for(self._active_tf)
        else:
            cursor = self._session.scenario.cursor_ms
            if self._active_tf == self._settings.execution_timeframe:
                series = self._session.scenario.visible_execution
            else:
                series = self._session.scenario.series_at_cursor(
                    self._active_tf, cursor
                )
        self._chart.set_candles(list(series.candles), fit=fit)
        self._chart.set_hud(
            f"{self._current_symbol}  {self._active_tf.upper()}"
        )
        if self._phase is UiPhase.RESULT and self._explanation is not None:
            self._apply_overlays_for_tf(self._active_tf)

    def _apply_overlays_for_tf(self, timeframe: str) -> None:
        if self._explanation is None:
            return
        if timeframe == self._settings.execution_timeframe:
            self._chart.set_overlays(self._explanation.overlays)
            return
        context = self._explanation.context_map
        if context is not None and context.timeframe == timeframe:
            self._chart.set_overlays(structure_to_overlays(context))
            return
        # Other context TF: analyze on the fly from current series.
        if self._playback is None or self._session is None:
            return
        series = self._playback.series_for(timeframe)
        self._chart.set_overlays(structure_to_overlays(analyze_series(series)))

    def _on_tf_clicked(self, timeframe: str) -> None:
        self._active_tf = timeframe
        self._refresh_chart(fit=True)

    def _on_side(self, side: Side) -> None:
        if self._session is None or self._phase not in {
            UiPhase.DECIDE,
            UiPhase.PLACE_ORDERS,
        }:
            return
        self._side = side
        entry = self._session.scenario.entry_price
        self._plan_entry = entry
        plan = default_plan(side, entry)
        decimals = price_decimals(entry)
        step = price_step(entry)
        self._tp_spin.blockSignals(True)
        self._sl_spin.blockSignals(True)
        for spin in (self._tp_spin, self._sl_spin):
            spin.setDecimals(decimals)
            spin.setSingleStep(step)
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
            take_profit=float(self._tp_spin.value()),
            stop_loss=float(self._sl_spin.value()),
        )

    def _on_spin_changed(self, _value: float) -> None:
        if self._phase is not UiPhase.PLACE_ORDERS or self._side is None:
            return
        self._chart.set_trade_levels(
            entry=self._plan_entry,
            take_profit=float(self._tp_spin.value()),
            stop_loss=float(self._sl_spin.value()),
            editable=True,
        )

    def _on_levels_changed(self, entry: float, tp: float, sl: float) -> None:
        if self._phase is not UiPhase.PLACE_ORDERS:
            return
        self._plan_entry = entry
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
        self._chart.set_trade_levels(
            entry=plan.entry,
            take_profit=plan.take_profit,
            stop_loss=plan.stop_loss,
            editable=False,
        )
        self._active_tf = self._settings.execution_timeframe
        self._tf_buttons[self._active_tf].setChecked(True)
        self._set_phase(UiPhase.PLAYBACK)
        self.statusBar().showMessage("Playback…")
        self._timer.start()

    def _on_playback_tick(self) -> None:
        if self._playback is None:
            self._timer.stop()
            return

        before = self._playback.shown_hidden
        result = self._playback.step()
        # Update chart with newly revealed execution candle when on exec TF.
        if (
            self._active_tf == self._settings.execution_timeframe
            and self._playback.shown_hidden > before
        ):
            candle = self._playback.scenario.hidden_execution[before]
            self._chart.update_candle(candle)
        else:
            self._refresh_chart(fit=False)

        if result is None:
            self.statusBar().showMessage(
                f"Playback bar {self._playback.shown_hidden}/"
                f"{len(self._playback.scenario.hidden_execution)}"
            )
            return

        self._timer.stop()
        self._finish_with_outcome(result.outcome)

    def _finish_with_outcome(self, outcome: TradeOutcome) -> None:
        self._set_phase(UiPhase.RESULT)
        text = _OUTCOME_TEXT.get(outcome, outcome.value)
        self._phase_label.setText(text)
        self.statusBar().showMessage(f"Результат: {text}")

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

            plan = self._playback.plan if self._playback is not None else None
            explanation = build_explanation(
                execution_series=execution,
                context_series=context,
                outcome=outcome,
                plan=plan,
            )
            self._explanation = explanation
            self._debrief.show_explanation(explanation)
            self._active_tf = self._settings.execution_timeframe
            self._tf_buttons[self._active_tf].setChecked(True)
            self._refresh_chart(fit=True)
            self._chart.set_overlays(explanation.overlays)

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

        self._btn_long.setEnabled(decide or place)
        self._btn_short.setEnabled(decide or place)
        self._btn_skip.setEnabled(decide)
        self._btn_confirm.setEnabled(place)
        self._btn_next.setEnabled(result or (not loading and not playback))
        self._tp_spin.setEnabled(place)
        self._sl_spin.setEnabled(place)
        for btn in self._tf_buttons.values():
            btn.setEnabled(not loading)

        labels = {
            UiPhase.LOADING: "Loading…",
            UiPhase.DECIDE: "Выбери действие",
            UiPhase.PLACE_ORDERS: "Выставь TP / SL",
            UiPhase.PLAYBACK: "Playback…",
            UiPhase.RESULT: "Результат",
        }
        if phase is not UiPhase.RESULT:
            self._phase_label.setText(labels[phase])
