"""User profile persistence and trade statistics."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from retrade.domain.trading import Side, TradeOutcome, TradePlan


@dataclass
class ProfileStats:
    trades: int = 0
    wins: int = 0
    losses: int = 0
    draws: int = 0
    exits: int = 0
    skips: int = 0
    sum_r: float = 0.0
    open_tails: int = 0  # NO HIT / OPEN

    def reset(self) -> None:
        self.trades = 0
        self.wins = 0
        self.losses = 0
        self.draws = 0
        self.exits = 0
        self.skips = 0
        self.sum_r = 0.0
        self.open_tails = 0

    @property
    def winrate(self) -> float | None:
        closed = self.wins + self.losses
        if closed == 0:
            return None
        return self.wins / closed


@dataclass
class UserProfile:
    display_name: str
    avatar_path: str | None = None
    stats: ProfileStats = field(default_factory=ProfileStats)

    def resolved_avatar(self, default_avatar: Path) -> Path:
        if self.avatar_path:
            path = Path(self.avatar_path)
            if path.is_file():
                return path
        return default_avatar


def default_windows_username() -> str:
    for key in ("USERNAME", "USER", "LOGNAME"):
        value = os.environ.get(key)
        if value:
            return value
    try:
        return os.getlogin()
    except OSError:
        return Path.home().name or "Trader"


class ProfileStore:
    """Load/save profile.json under data_dir."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self.profile = self._load_or_create()

    def _load_or_create(self) -> UserProfile:
        if self._path.exists():
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                stats_raw = raw.get("stats", {})
                stats = ProfileStats(
                    trades=int(stats_raw.get("trades", 0)),
                    wins=int(stats_raw.get("wins", 0)),
                    losses=int(stats_raw.get("losses", 0)),
                    draws=int(stats_raw.get("draws", 0)),
                    exits=int(stats_raw.get("exits", 0)),
                    skips=int(stats_raw.get("skips", 0)),
                    sum_r=float(stats_raw.get("sum_r", 0.0)),
                    open_tails=int(stats_raw.get("open_tails", 0)),
                )
                return UserProfile(
                    display_name=str(
                        raw.get("display_name") or default_windows_username()
                    ),
                    avatar_path=raw.get("avatar_path"),
                    stats=stats,
                )
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                pass
        profile = UserProfile(display_name=default_windows_username())
        self._save(profile)
        return profile

    def save(self) -> None:
        self._save(self.profile)

    def _save(self, profile: UserProfile) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "display_name": profile.display_name,
            "avatar_path": profile.avatar_path,
            "stats": asdict(profile.stats),
        }
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def reset_stats(self) -> None:
        self.profile.stats.reset()
        self.save()

    def set_display_name(self, name: str) -> None:
        cleaned = name.strip() or default_windows_username()
        self.profile.display_name = cleaned
        self.save()

    def set_avatar_path(self, path: Path | None) -> None:
        self.profile.avatar_path = str(path) if path is not None else None
        self.save()

    def record_trade(
        self,
        *,
        outcome: TradeOutcome,
        plan: TradePlan | None,
        exit_price: float | None,
    ) -> float | None:
        """Update stats; return realized R or None for skip."""
        stats = self.profile.stats
        if outcome is TradeOutcome.SKIP:
            stats.skips += 1
            self.save()
            return None

        stats.trades += 1
        realized_r: float | None = None
        if plan is not None and exit_price is not None:
            realized_r = compute_r(plan, exit_price)
            stats.sum_r += realized_r

        if outcome is TradeOutcome.TAKE_PROFIT:
            stats.wins += 1
        elif outcome is TradeOutcome.STOP_LOSS:
            stats.losses += 1
        elif outcome is TradeOutcome.AMBIGUOUS:
            stats.draws += 1
        elif outcome is TradeOutcome.EXIT:
            stats.exits += 1
        elif outcome is TradeOutcome.OPEN:
            stats.open_tails += 1

        self.save()
        return realized_r


def compute_r(plan: TradePlan, exit_price: float) -> float:
    """R-multiple: profit / initial risk."""
    risk = abs(plan.entry - plan.stop_loss)
    if risk <= 0:
        return 0.0
    if plan.side is Side.LONG:
        return (exit_price - plan.entry) / risk
    return (plan.entry - exit_price) / risk


def exit_price_for_outcome(
    outcome: TradeOutcome,
    plan: TradePlan | None,
    candle_close: float | None,
) -> float | None:
    if plan is None:
        return None
    if outcome is TradeOutcome.TAKE_PROFIT:
        return plan.take_profit
    if outcome is TradeOutcome.STOP_LOSS:
        return plan.stop_loss
    if outcome is TradeOutcome.AMBIGUOUS:
        return plan.entry  # 0R draw convention
    if outcome in {TradeOutcome.EXIT, TradeOutcome.OPEN}:
        return candle_close
    return None
