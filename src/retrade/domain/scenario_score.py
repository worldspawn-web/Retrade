"""Score and pick pedagogically interesting decision points."""

from __future__ import annotations

import random
from dataclasses import dataclass

from retrade.domain.candles import CandleSeries
from retrade.domain.smc import (
    Bias,
    StructureEventKind,
    analyze_series,
)


@dataclass(frozen=True, slots=True)
class ScoredDecision:
    index: int
    score: float
    reasons: tuple[str, ...]


def score_decision_point(
    execution: CandleSeries,
    decision_index: int,
    *,
    lookback: int = 60,
    avoided_ranges: tuple[tuple[int, int], ...] = (),
) -> ScoredDecision:
    """
    Score a candidate decision index using only candles available at that moment
    (no lookahead into the hidden tail).
    """
    if decision_index < 20 or decision_index > len(execution):
        return ScoredDecision(decision_index, 0.0, ("too_short",))

    window = CandleSeries(
        execution.symbol,
        execution.timeframe,
        execution.candles[max(0, decision_index - lookback) : decision_index],
    )
    structure = analyze_series(window)
    score = 0.0
    reasons: list[str] = []

    decision_time = execution.candles[decision_index - 1].open_time
    if _hits_avoided(decision_time, avoided_ranges):
        score -= 25.0
        reasons.append("seen_timeline")

    recent_events = [e for e in structure.events if e.index >= len(window) - 25]
    if recent_events:
        score += 3.0 * len(recent_events)
        if any(e.kind is StructureEventKind.CHOCH for e in recent_events):
            score += 4.0
            reasons.append("choch")
        if any(e.kind is StructureEventKind.BOS for e in recent_events):
            score += 2.0
            reasons.append("bos")

    open_fvgs = [g for g in structure.fvgs if not g.mitigated]
    if open_fvgs:
        score += min(4.0, 1.5 * len(open_fvgs))
        reasons.append("fvg")

    if structure.bias is not Bias.RANGE:
        score += 2.0
        reasons.append("clear_bias")
    else:
        score -= 1.0

    last = window.candles[-12:]
    if last:
        ranges = [(c.high - c.low) / c.close for c in last if c.close]
        avg_range = sum(ranges) / len(ranges) if ranges else 0.0
        if avg_range > 0.002:
            score += 1.5
            reasons.append("volatility")
        elif avg_range < 0.0005:
            score -= 2.0
            reasons.append("flat")

    if len(structure.swings) >= 4:
        score += 1.0
        reasons.append("swings")

    return ScoredDecision(decision_index, score, tuple(reasons))


def pick_best_decision_index(
    execution: CandleSeries,
    *,
    visible_bars: int,
    hidden_bars: int,
    candidates: int = 36,
    avoided_ranges: tuple[tuple[int, int], ...] = (),
    rng: random.Random | None = None,
) -> ScoredDecision:
    """
    Sample candidate decision points uniformly across history and return best.

    Uniform sampling (not recent-biased) improves timeline variety.
    """
    rng = rng or random.Random()
    total = len(execution)
    min_index = max(40, visible_bars // 2)
    max_index = total - max(8, hidden_bars // 4)
    if max_index <= min_index:
        fallback = max(30, total // 2)
        return score_decision_point(
            execution,
            min(fallback, total - 1),
            avoided_ranges=avoided_ranges,
        )

    pool = list(range(min_index, max_index + 1))
    if len(pool) > candidates:
        # Stratified-ish: spread samples across the full pool.
        step = max(1, len(pool) // candidates)
        grid = pool[::step][:candidates]
        extras = rng.sample(pool, k=min(candidates // 3, len(pool)))
        sample = sorted(set(grid).union(extras))
    else:
        sample = pool

    scored = [
        score_decision_point(
            execution,
            idx,
            avoided_ranges=avoided_ranges,
        )
        for idx in sample
    ]
    return max(scored, key=lambda s: s.score)


def _hits_avoided(time_ms: int, avoided: tuple[tuple[int, int], ...]) -> bool:
    return any(start <= time_ms <= end for start, end in avoided)
