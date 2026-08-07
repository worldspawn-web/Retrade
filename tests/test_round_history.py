"""Tests for round history cooldown and timeline overlap."""

from __future__ import annotations

from pathlib import Path

from retrade.domain.round_history import RoundHistory, RoundRecord


def test_symbol_cooldown_10_rounds(tmp_path: Path) -> None:
    history = RoundHistory(tmp_path / "h.json", symbol_cooldown=10)
    history.record(
        RoundRecord("BTCUSDT", 1_000, 2_000, 1_500),
    )
    # After 1 record, next round index=1 → not yet eligible (need >= 10 gap)
    assert not history.is_symbol_eligible("BTCUSDT")
    assert history.is_symbol_eligible("ETHUSDT")

    for i in range(9):
        history.record(
            RoundRecord(f"ALT{i}USDT", 10_000 + i, 20_000 + i, 15_000 + i),
        )
    # 10 rounds total (btc + 9 alts). Starting 11th → len=10, last btc at 0
    # 10 - 0 >= 10 → eligible
    assert len(history) == 10
    assert history.is_symbol_eligible("BTCUSDT")


def test_window_overlap_detection(tmp_path: Path) -> None:
    day = 24 * 60 * 60 * 1000
    history = RoundHistory(
        tmp_path / "h.json",
        symbol_cooldown=10,
        min_window_gap_ms=5 * day,
    )
    history.record(
        RoundRecord("BTCUSDT", 100 * day, 110 * day, 105 * day),
    )
    assert history.overlaps_window("BTCUSDT", 108 * day, 118 * day)
    assert not history.overlaps_window("BTCUSDT", 200 * day, 210 * day)
    assert not history.overlaps_window("ETHUSDT", 108 * day, 118 * day)


def test_eligible_symbols_fallback(tmp_path: Path) -> None:
    history = RoundHistory(tmp_path / "h.json", symbol_cooldown=10)
    for i in range(3):
        history.record(RoundRecord(f"S{i}", i, i + 1, i))
    # All pool blocked if cooldown and only those symbols — fallback to full pool
    pool = ["S0", "S1", "S2"]
    eligible = history.eligible_symbols(pool)
    assert set(eligible) == set(pool)
