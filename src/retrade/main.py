"""Application entry point."""

from __future__ import annotations

import logging
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from retrade.config import get_settings
from retrade.domain.round_history import RoundHistory
from retrade.infra.binance import BinanceMarketData
from retrade.infra.cache import KlineCache
from retrade.infra.symbol_universe import SymbolUniverse
from retrade.ui.main_window import MainWindow


def main() -> int:
    """Start Retrade desktop prototype."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    app = QApplication(sys.argv)
    app.setApplicationName("Retrade")
    app.setOrganizationName("Retrade")

    market = BinanceMarketData(
        base_url=settings.binance_base_url,
        cache=KlineCache(settings.data_dir),
    )
    universe = SymbolUniverse(
        base_url=settings.binance_base_url,
        cache_path=settings.data_dir / "universe.json",
        top_n=settings.top_symbols,
    )
    history = RoundHistory(
        settings.data_dir / "round_history.json",
        symbol_cooldown=settings.symbol_cooldown,
    )
    window = MainWindow(
        settings=settings,
        market=market,
        universe=universe,
        history=history,
    )
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
