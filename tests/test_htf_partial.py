"""Tests for HTF partial candle aggregation."""

from __future__ import annotations

from retrade.domain.candles import Candle, CandleSeries, htf_series_with_partial


def _c(
    i: int,
    o: float,
    h: float,
    low: float,
    c: float,
    *,
    step: int = 900_000,
) -> Candle:
    open_time = i * step
    return Candle(
        open_time=open_time,
        open=o,
        high=h,
        low=low,
        close=c,
        volume=1.0,
        close_time=open_time + step - 1,
    )


def test_htf_partial_close_matches_last_exec() -> None:
    # 4h = 16 * 15m. Build 20 fifteen-minute bars.
    exec_bars = tuple(
        _c(i, 1.0 + i * 0.01, 1.02 + i * 0.01, 0.99 + i * 0.01, 1.01 + i * 0.01)
        for i in range(20)
    )
    # One closed 4h covering bars 0..15, then partial from 16..19
    htf = CandleSeries(
        "TEST",
        "4h",
        (
            Candle(
                open_time=0,
                open=1.0,
                high=1.2,
                low=0.9,
                close=1.15,
                volume=16.0,
                close_time=16 * 900_000 - 1,
            ),
        ),
    )
    cursor = exec_bars[-1].close_time
    view = htf_series_with_partial(
        htf,
        exec_bars,
        cursor_ms=cursor,
        interval_ms=14_400_000,
    )
    assert len(view.candles) == 2
    assert view.candles[-1].close == exec_bars[-1].close
