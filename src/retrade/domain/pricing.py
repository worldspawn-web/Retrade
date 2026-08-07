"""Helpers for price formatting across cheap/expensive alts."""

from __future__ import annotations


def price_decimals(price: float) -> int:
    """
    Display decimals by magnitude.

    Enough for sub-cent alts (0.015 → 5 dp), without noisy tails on BTC/ETH.
    """
    abs_price = abs(price)
    if abs_price >= 100:
        return 2
    if abs_price >= 1:
        return 3
    if abs_price >= 0.1:
        return 4
    if abs_price >= 0.01:
        return 5
    if abs_price >= 0.001:
        return 6
    return 8


def price_step(price: float) -> float:
    """Reasonable spinbox step (~0.05% of price, floored by decimals)."""
    decimals = price_decimals(price)
    raw = max(abs(price) * 0.0005, 10 ** (-decimals))
    return round(raw, decimals)
