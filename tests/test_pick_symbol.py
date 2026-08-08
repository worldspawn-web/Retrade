"""Symbol picking with session blacklist."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from retrade.domain.scenario import pick_symbol


def test_pick_symbol_excludes_blacklist() -> None:
    universe = MagicMock()
    universe.ensure_loaded.return_value = ["AAAUSDT", "BBBUSDT", "CCCUSDT"]
    history = MagicMock()
    history.eligible_symbols.return_value = ["AAAUSDT", "BBBUSDT", "CCCUSDT"]

    chosen = {
        pick_symbol(universe, history, exclude={"AAAUSDT", "BBBUSDT"}, rng=None)
        for _ in range(20)
    }
    assert chosen == {"CCCUSDT"}


def test_pick_symbol_raises_when_all_blocked() -> None:
    universe = MagicMock()
    universe.ensure_loaded.return_value = ["AAAUSDT"]
    history = MagicMock()
    history.eligible_symbols.return_value = ["AAAUSDT"]
    with pytest.raises(RuntimeError, match="Нет доступных"):
        pick_symbol(universe, history, exclude={"AAAUSDT"})
