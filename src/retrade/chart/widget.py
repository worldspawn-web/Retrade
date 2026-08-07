"""Qt WebEngine host for Lightweight Charts."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget

from retrade.chart.paths import chart_web_dir
from retrade.domain.candles import Candle
from retrade.domain.pricing import price_decimals

logger = logging.getLogger(__name__)


class ChartBridge(QObject):
    """JS -> Python events via QWebChannel."""

    event_received = Signal(dict)

    @Slot(str)
    def onChartEvent(self, payload_json: str) -> None:  # noqa: N802 - QWebChannel API
        try:
            data = json.loads(payload_json)
        except json.JSONDecodeError:
            logger.exception("Invalid chart event JSON")
            return
        if isinstance(data, dict):
            self.event_received.emit(data)


class ChartWidget(QWidget):
    """Embeds TradingView Lightweight Charts and exposes a small Python API."""

    ready = Signal()
    levels_changed = Signal(float, float, float)  # entry, tp, sl

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._bridge = ChartBridge(self)
        self._bridge.event_received.connect(self._on_bridge_event)
        self._is_ready = False
        self._pending: list[Callable[[], None]] = []

        self._view = QWebEngineView(self)
        page = self._view.page()
        assert isinstance(page, QWebEnginePage)
        settings = page.settings()
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
            True,
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls,
            True,
        )

        channel = QWebChannel(page)
        channel.registerObject("qtBridge", self._bridge)
        page.setWebChannel(channel)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)

        index = chart_web_dir() / "index.html"
        self._view.load(QUrl.fromLocalFile(str(index.resolve())))

        # qwebchannel.js is loaded from qrc in index.html.
        self._view.loadFinished.connect(self._on_load_finished)

    def _on_load_finished(self, ok: bool) -> None:
        if not ok:
            logger.error("Failed to load chart index.html")

    def _on_bridge_event(self, data: dict[str, Any]) -> None:
        event_type = data.get("type")
        if event_type == "ready":
            self._is_ready = True
            for action in self._pending:
                action()
            self._pending.clear()
            self.ready.emit()
        elif event_type == "levelsChanged":
            entry = float(data["entry"])
            tp = float(data["tp"])
            sl = float(data["sl"])
            self.levels_changed.emit(entry, tp, sl)

    def _run(self, script: str) -> None:
        def action() -> None:
            self._view.page().runJavaScript(script)

        if self._is_ready:
            action()
        else:
            self._pending.append(action)

    def set_candles(
        self,
        candles: list[Candle],
        *,
        fit: bool = True,
        precision: int | None = None,
    ) -> None:
        payload = [c.to_chart_dict() for c in candles]
        fit_js = "true" if fit else "false"
        if precision is None and candles:
            precision = price_decimals(candles[-1].close)
        if precision is None:
            precision = 2
        self._run(
            "window.retradeChart.setCandles("
            f"{json.dumps(payload)}, {fit_js}, {int(precision)});"
        )

    def reset_view(self) -> None:
        self._run("window.retradeChart.resetView();")

    def update_candle(self, candle: Candle) -> None:
        payload = json.dumps(candle.to_chart_dict())
        self._run(f"window.retradeChart.updateCandle({payload});")

    def set_trade_levels(
        self,
        *,
        entry: float,
        take_profit: float,
        stop_loss: float,
        editable: bool,
    ) -> None:
        levels = {"entry": entry, "tp": take_profit, "sl": stop_loss}
        self._run(
            "window.retradeChart.setTradeLevels("
            f"{json.dumps(levels)}, {'true' if editable else 'false'});"
        )

    def clear_trade_levels(self) -> None:
        self._run("window.retradeChart.clearTradeLevels();")

    def set_overlays(self, overlays: dict[str, Any]) -> None:
        self._run(f"window.retradeChart.setOverlays({json.dumps(overlays)});")

    def clear_overlays(self) -> None:
        self._run("window.retradeChart.clearOverlays();")

    def set_hud(self, text: str) -> None:
        self._run(f"window.retradeChart.setHud({json.dumps(text)});")

    @staticmethod
    def ensure_assets() -> Path:
        path = chart_web_dir()
        if not (path / "index.html").exists():
            raise FileNotFoundError(f"Chart assets missing: {path}")
        return path
