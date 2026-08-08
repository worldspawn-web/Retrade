"""Background scenario loading so the UI spinner can keep animating."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal

from retrade.config import Settings
from retrade.domain.round_history import RoundHistory
from retrade.domain.scenario import RoundScenario, build_scenario, pick_symbol
from retrade.infra.binance import BinanceMarketData
from retrade.infra.symbol_universe import SymbolUniverse

logger = logging.getLogger(__name__)


class ScenarioLoadWorker(QObject):
    """Runs universe + scenario fetch off the GUI thread."""

    progress = Signal(str)
    finished = Signal(object)  # RoundScenario
    failed = Signal(str, str)  # symbol (may be ""), error text

    def __init__(
        self,
        *,
        market: BinanceMarketData,
        universe: SymbolUniverse,
        history: RoundHistory,
        settings: Settings,
        blacklist: frozenset[str],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._market = market
        self._universe = universe
        self._history = history
        self._settings = settings
        self._blacklist = blacklist

    def run(self) -> None:
        symbol = ""
        try:
            self.progress.emit("Загрузка данных…")
            self._universe.ensure_loaded()
            symbol = pick_symbol(
                self._universe,
                self._history,
                exclude=self._blacklist,
            )
            self.progress.emit(f"Загрузка {symbol}…")
            scenario: RoundScenario = build_scenario(
                self._market,
                symbol=symbol,
                execution_timeframe=self._settings.execution_timeframe,
                context_timeframes=self._settings.context_timeframes,
                history=self._history,
                history_lookback_days=self._settings.history_lookback_days,
                max_window_attempts=3,
            )
            self.finished.emit(scenario)
        except Exception as exc:  # noqa: BLE001 - delivered to UI
            logger.exception("Background scenario load failed")
            self.failed.emit(symbol, str(exc))
