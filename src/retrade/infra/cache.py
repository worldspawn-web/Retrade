"""Local Parquet cache for klines keyed by (symbol, timeframe)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from retrade.domain.candles import Candle, CandleSeries, merge_unique_by_open_time

_COLUMNS = (
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
)


class KlineCache:
    """Filesystem cache under data_dir / klines / SYMBOL / TF.parquet."""

    def __init__(self, data_dir: Path) -> None:
        self._root = data_dir / "klines"
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, symbol: str, timeframe: str) -> Path:
        folder = self._root / symbol.upper()
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"{timeframe}.parquet"

    def load(self, symbol: str, timeframe: str) -> CandleSeries | None:
        path = self._path(symbol, timeframe)
        if not path.exists():
            return None
        frame = pd.read_parquet(path)
        candles = tuple(
            Candle(
                open_time=int(row.open_time),
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=float(row.volume),
                close_time=int(row.close_time),
            )
            for row in frame.itertuples(index=False)
        )
        return CandleSeries(symbol.upper(), timeframe, candles)

    def save(self, series: CandleSeries) -> None:
        path = self._path(series.symbol, series.timeframe)
        frame = pd.DataFrame(
            [
                {
                    "open_time": c.open_time,
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "volume": c.volume,
                    "close_time": c.close_time,
                }
                for c in series.candles
            ],
            columns=list(_COLUMNS),
        )
        frame.to_parquet(path, index=False)

    def merge_and_save(
        self,
        symbol: str,
        timeframe: str,
        incoming: CandleSeries,
    ) -> CandleSeries:
        existing = self.load(symbol, timeframe)
        merged_candles = merge_unique_by_open_time(
            (*(existing.candles if existing else ()), *incoming.candles)
        )
        merged = CandleSeries(symbol.upper(), timeframe, merged_candles)
        self.save(merged)
        return merged
