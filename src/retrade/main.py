"""Application entry point."""

from __future__ import annotations

import logging
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from retrade.config import get_settings
from retrade.infra.binance import BinanceMarketData
from retrade.infra.cache import KlineCache
from retrade.ui.main_window import MainWindow


def main() -> int:
    """Start Retrade desktop prototype."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    # Must be set before QApplication when using QtWebEngine.
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
    window = MainWindow(settings=settings, market=market)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
