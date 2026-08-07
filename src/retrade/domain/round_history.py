"""Persistent history of played rounds: symbol cooldown + time windows."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RoundRecord:
    """One completed (or started) training round fingerprint."""

    symbol: str
    window_start_ms: int
    window_end_ms: int
    decision_time_ms: int


class RoundHistory:
    """
    Tracks recent symbols and used timeline slices.

    Symbol cooldown: a symbol used at round index i becomes eligible again
    when starting round i + cooldown (e.g. used at 0 → eligible at 10).
    """

    def __init__(
        self,
        path: Path,
        *,
        symbol_cooldown: int = 10,
        min_window_gap_ms: int = 5 * 24 * 60 * 60 * 1000,
    ) -> None:
        self._path = path
        self.symbol_cooldown = symbol_cooldown
        self.min_window_gap_ms = min_window_gap_ms
        self._rounds: list[RoundRecord] = []
        self._load()

    def __len__(self) -> int:
        return len(self._rounds)

    @property
    def rounds(self) -> tuple[RoundRecord, ...]:
        return tuple(self._rounds)

    def is_symbol_eligible(self, symbol: str) -> bool:
        symbol = symbol.upper()
        last_index = self._last_symbol_index(symbol)
        if last_index is None:
            return True
        # Next round index == len(self); eligible if enough rounds passed.
        return len(self._rounds) - last_index >= self.symbol_cooldown

    def eligible_symbols(self, pool: list[str]) -> list[str]:
        eligible = [s for s in pool if self.is_symbol_eligible(s)]
        return eligible if eligible else list(pool)

    def overlaps_window(
        self,
        symbol: str,
        window_start_ms: int,
        window_end_ms: int,
    ) -> bool:
        """True if this calendar slice is too close to a past round of same symbol."""
        symbol = symbol.upper()
        for record in self._rounds:
            if record.symbol != symbol:
                continue
            if _windows_too_close(
                window_start_ms,
                window_end_ms,
                record.window_start_ms,
                record.window_end_ms,
                gap_ms=self.min_window_gap_ms,
            ):
                return True
        return False

    def record(self, record: RoundRecord) -> None:
        self._rounds.append(
            RoundRecord(
                symbol=record.symbol.upper(),
                window_start_ms=record.window_start_ms,
                window_end_ms=record.window_end_ms,
                decision_time_ms=record.decision_time_ms,
            )
        )
        self._save()

    def _last_symbol_index(self, symbol: str) -> int | None:
        for index in range(len(self._rounds) - 1, -1, -1):
            if self._rounds[index].symbol == symbol:
                return index
        return None

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        rounds = raw.get("rounds", [])
        loaded: list[RoundRecord] = []
        for item in rounds:
            try:
                loaded.append(
                    RoundRecord(
                        symbol=str(item["symbol"]).upper(),
                        window_start_ms=int(item["window_start_ms"]),
                        window_end_ms=int(item["window_end_ms"]),
                        decision_time_ms=int(item["decision_time_ms"]),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        self._rounds = loaded

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"rounds": [asdict(r) for r in self._rounds]}
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _windows_too_close(
    a_start: int,
    a_end: int,
    b_start: int,
    b_end: int,
    *,
    gap_ms: int,
) -> bool:
    # Expand each window by gap/2 on both sides, then test overlap.
    pad = gap_ms // 2
    a0, a1 = a_start - pad, a_end + pad
    b0, b1 = b_start - pad, b_end + pad
    return a0 <= b1 and b0 <= a1
