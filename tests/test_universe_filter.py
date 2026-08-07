"""Tests for symbol universe filtering helpers."""

from __future__ import annotations

from retrade.domain.pricing import price_decimals, price_step
from retrade.infra.symbol_universe import _is_tradable_usdt


def test_filter_leveraged_and_stables() -> None:
    assert _is_tradable_usdt("BTCUSDT")
    assert _is_tradable_usdt("ETHUSDT")
    assert not _is_tradable_usdt("BTCUPUSDT")
    assert not _is_tradable_usdt("ETHDOWNUSDT")
    assert not _is_tradable_usdt("USDCUSDT")
    assert not _is_tradable_usdt("BTCUSD")


def test_price_decimals_and_step() -> None:
    assert price_decimals(64000) == 2
    assert price_decimals(2500) == 2
    assert price_decimals(2.5) == 3
    assert price_decimals(0.15) == 4
    assert price_decimals(0.015) == 5
    assert price_decimals(0.0015) == 6
    assert price_step(64000) > 0
    assert price_step(0.001) > 0
