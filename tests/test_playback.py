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


def test_hold_after_n_bars_without_hit() -> None:
    exec_candles = tuple(_c(i) for i in range(40))
    hidden = tuple(_c(i, h=100.6, low=100.0, c=100.4) for i in range(10, 42))
    visible = CandleSeries("BTCUSDT", "15m", exec_candles[:10])
    full = CandleSeries("BTCUSDT", "15m", exec_candles[:10] + hidden)
    scenario = RoundScenario(
        symbol="BTCUSDT",
        execution_timeframe="15m",
        series_by_tf={"15m": full},
        decision_index=10,
        visible_execution=visible,
        hidden_execution=hidden,
    )
    entry = scenario.entry_price
    plan = TradePlan(
        Side.LONG,
        entry=entry,
        take_profit=entry + 50.0,
        stop_loss=entry - 50.0,
    )
    state = PlaybackState(scenario=scenario, plan=plan)
    hold = None
    for _ in range(4):
        hold = state.step(hold_check_bars=4)
        if hold is not None:
            break
    assert hold is not None
    assert hold.hold is True
    assert state.shown_hidden == 4
    assert state.finished is False

    state.continue_after_hold()
    assert state.step(hold_check_bars=4) is None

    result = state.exit_at_market()
    assert result.outcome is TradeOutcome.EXIT
    assert state.finished


def test_reveal_only_after_finish() -> None:
    exec_candles = tuple(_c(i) for i in range(20))
    hidden = tuple(_c(i, h=100.2, low=99.8, c=100.0) for i in range(10, 16))
    # First hidden bar hits TP
    hidden = (
        _c(10, h=103.0, low=100.0, c=102.0),
        *hidden[1:],
    )
    visible = CandleSeries("BTCUSDT", "15m", exec_candles[:10])
    full = CandleSeries("BTCUSDT", "15m", exec_candles[:10] + hidden)
    scenario = RoundScenario(
        symbol="BTCUSDT",
        execution_timeframe="15m",
        series_by_tf={"15m": full},
        decision_index=10,
        visible_execution=visible,
        hidden_execution=hidden,
    )
    entry = scenario.entry_price
    plan = TradePlan(
        Side.LONG,
        entry=entry,
        take_profit=entry + 1.0,
        stop_loss=entry - 2.0,
    )
    state = PlaybackState(scenario=scenario, plan=plan)
    result = state.step()
    assert result is not None
    assert result.outcome is TradeOutcome.TAKE_PROFIT
    assert state.finished
    assert state.shown_hidden == 1
    candle = state.reveal_only()
    assert candle is not None
    assert state.shown_hidden == 2
    assert state.finished  # still finished; no re-score

