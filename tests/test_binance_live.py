"""Integration-ish test: Binance fetch + cache (network)."""

from __future__ import annotations

from pathlib import Path

import pytest

from retrade.infra.binance import BinanceMarketData
from retrade.infra.cache import KlineCache


@pytest.mark.integration
def test_binance_btc_15m(tmp_path: Path) -> None:
    market = BinanceMarketData(
        base_url="https://api.binance.com",
        cache=KlineCache(tmp_path),
    )
    series = market.get_klines("BTCUSDT", "15m", limit=50)
    assert len(series) >= 40
    assert series.symbol == "BTCUSDT"
    assert series.candles[0].open_time < series.candles[-1].open_time
    # Second call should work from merged cache even if offline logic path unused
    again = market.get_klines("BTCUSDT", "15m", limit=50)
    assert len(again) >= 40
