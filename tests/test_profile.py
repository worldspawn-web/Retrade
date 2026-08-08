"""Profile stats and R-multiple helpers."""

from __future__ import annotations

from pathlib import Path

from retrade.domain.profile import (
    ProfileStore,
    compute_r,
    exit_price_for_outcome,
)
from retrade.domain.trading import Side, TradeOutcome, TradePlan


def test_compute_r_long() -> None:
    plan = TradePlan(Side.LONG, entry=100.0, take_profit=110.0, stop_loss=95.0)
    assert compute_r(plan, 110.0) == 2.0
    assert compute_r(plan, 95.0) == -1.0
    assert compute_r(plan, 100.0) == 0.0


def test_compute_r_short() -> None:
    plan = TradePlan(Side.SHORT, entry=100.0, take_profit=90.0, stop_loss=105.0)
    assert compute_r(plan, 90.0) == 2.0
    assert compute_r(plan, 105.0) == -1.0


def test_record_trade_and_reset(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "profile.json")
    plan = TradePlan(Side.LONG, entry=100.0, take_profit=110.0, stop_loss=95.0)
    r = store.record_trade(
        outcome=TradeOutcome.TAKE_PROFIT,
        plan=plan,
        exit_price=exit_price_for_outcome(TradeOutcome.TAKE_PROFIT, plan, None),
    )
    assert r == 2.0
    assert store.profile.stats.wins == 1
    assert store.profile.stats.trades == 1
    assert store.profile.stats.sum_r == 2.0

    store.record_trade(outcome=TradeOutcome.SKIP, plan=None, exit_price=None)
    assert store.profile.stats.skips == 1

    store.record_trade(
        outcome=TradeOutcome.EXIT,
        plan=plan,
        exit_price=102.5,
    )
    assert store.profile.stats.exits == 1

    store.reset_stats()
    assert store.profile.stats.trades == 0
    assert store.profile.stats.sum_r == 0.0
