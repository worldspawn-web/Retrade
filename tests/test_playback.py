"""Playback and multi-TF cursor tests."""

from __future__ import annotations

from retrade.domain.candles import Candle, CandleSeries
from retrade.domain.playback import PlaybackState, RoundSession
from retrade.domain.scenario import RoundScenario
from retrade.domain.trading import Side, TradeOutcome, TradePlan


def _c(
    i: int,
    *,
    o: float = 100.0,
    h: float = 101.0,
    low: float = 99.0,
    c: float = 100.5,
) -> Candle:
    open_time = i * 900_000
    return Candle(
        open_time=open_time,
        open=o,
        high=h,
        low=low,
        close=c,
        volume=1.0,
        close_time=open_time + 899_999,
    )


def _scenario() -> RoundScenario:
    exec_candles = tuple(_c(i) for i in range(20))
    # Bar that hits TP for long default around 100.5 entry at index 10 visible end
    hidden = (
        _c(10, h=100.8, low=100.0, c=100.6),
        _c(11, h=103.0, low=100.4, c=102.5),  # TP if tp ~= 101.5 area
    )
    visible = CandleSeries("BTCUSDT", "15m", exec_candles[:10])
    full = CandleSeries("BTCUSDT", "15m", exec_candles[:10] + hidden)
    h1 = CandleSeries(
        "BTCUSDT",
        "1h",
        tuple(
            Candle(
                open_time=i * 3_600_000,
                open=100.0,
                high=102.0,
                low=99.0,
                close=101.0,
                volume=1.0,
                close_time=i * 3_600_000 + 3_599_999,
            )
            for i in range(6)
        ),
    )
    return RoundScenario(
        symbol="BTCUSDT",
        execution_timeframe="15m",
        series_by_tf={"15m": full, "1h": h1, "4h": h1},
        decision_index=10,
        visible_execution=visible,
        hidden_execution=hidden,
    )


def test_playback_hits_tp() -> None:
    scenario = _scenario()
    entry = scenario.entry_price
    plan = TradePlan(
        Side.LONG,
        entry=entry,
        take_profit=entry + 1.0,
        stop_loss=entry - 2.0,
    )
    state = PlaybackState(scenario=scenario, plan=plan)
    assert state.step() is None
    result = state.step()
    assert result is not None
    assert result.outcome is TradeOutcome.TAKE_PROFIT
    assert state.finished


def test_skip_session() -> None:
    session = RoundSession(scenario=_scenario())
    playback = session.start_skip()
    assert playback.outcome is TradeOutcome.SKIP
    assert playback.finished


def test_htf_sync_uses_cursor() -> None:
    scenario = _scenario()
    state = PlaybackState(scenario=scenario, plan=None)
    # Before any reveal, cursor is last visible close_time
    series = state.series_for("1h")
    assert all(c.close_time <= state.cursor_ms for c in series.candles)
