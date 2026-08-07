"""Post-trade debrief model and chart overlay payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from retrade.domain.candles import CandleSeries
from retrade.domain.smc import (
    Bias,
    BreakKind,
    StructureEventKind,
    StructureMap,
    analyze_series,
)
from retrade.domain.trading import Side, TradeOutcome, TradePlan


@dataclass(frozen=True, slots=True)
class DebriefChip:
    """Compact visual fact for the debrief strip."""

    label: str
    value: str
    tone: str = "neutral"  # neutral | good | bad | warn | accent


@dataclass(frozen=True, slots=True)
class Explanation:
    """Structured debrief + chart overlays (no wall of text)."""

    outcome: TradeOutcome
    headline: str
    chips: tuple[DebriefChip, ...]
    note: str
    overlays: dict[str, Any]
    execution_map: StructureMap
    context_map: StructureMap | None

    @property
    def text(self) -> str:
        """Fallback plain text (tests / logs)."""
        parts = [self.headline, *(f"{c.label}: {c.value}" for c in self.chips)]
        if self.note:
            parts.append(self.note)
        return "\n".join(parts)


def build_explanation(
    *,
    execution_series: CandleSeries,
    context_series: CandleSeries | None,
    outcome: TradeOutcome,
    plan: TradePlan | None,
) -> Explanation:
    """Analyze revealed price action into a compact visual debrief."""
    execution_map = analyze_series(execution_series)
    context_map = analyze_series(context_series) if context_series is not None else None

    chips: list[DebriefChip] = [
        DebriefChip("OUT", _outcome_short(outcome), _outcome_tone(outcome)),
    ]
    if plan is not None:
        chips.append(
            DebriefChip(
                "SIDE",
                plan.side.value.upper(),
                "good" if plan.side is Side.LONG else "bad",
            )
        )

    chips.append(
        DebriefChip(
            "15M",
            _bias_short(execution_map.bias),
            _bias_tone(execution_map.bias),
        )
    )
    if context_map is not None:
        chips.append(
            DebriefChip(
                context_map.timeframe.upper(),
                _bias_short(context_map.bias),
                _bias_tone(context_map.bias),
            )
        )

    if plan is not None:
        chips.append(_alignment_chip(plan, execution_map))

    recent = execution_map.events[-2:]
    if recent:
        last = recent[-1]
        chips.append(
            DebriefChip(
                last.kind.value.upper(),
                _bias_short(last.bias),
                "accent",
            )
        )

    open_fvgs = [g for g in execution_map.fvgs if not g.mitigated]
    chips.append(
        DebriefChip("FVG", str(len(open_fvgs)), "accent" if open_fvgs else "neutral")
    )

    false_breaks = sum(1 for b in execution_map.breaks if b.kind is BreakKind.FALSE)
    true_breaks = sum(1 for b in execution_map.breaks if b.kind is BreakKind.TRUE)
    if true_breaks or false_breaks:
        chips.append(
            DebriefChip(
                "BREAK",
                f"{true_breaks}T / {false_breaks}F",
                "warn" if false_breaks else "neutral",
            )
        )

    return Explanation(
        outcome=outcome,
        headline=_headline(outcome, plan),
        chips=tuple(chips),
        note=_short_note(outcome, plan, execution_map),
        overlays=structure_to_overlays(execution_map),
        execution_map=execution_map,
        context_map=context_map,
    )


def structure_to_overlays(structure: StructureMap) -> dict[str, Any]:
    """Chart overlays: BOS/CHoCH markers + open FVG zones. No S/R lines."""
    markers: list[dict[str, Any]] = []
    for event in structure.events[-20:]:
        bullish = event.bias is Bias.BULLISH
        label = "BOS" if event.kind is StructureEventKind.BOS else "CHoCH"
        markers.append(
            {
                "time": event.time_sec,
                "position": "belowBar" if bullish else "aboveBar",
                "color": "#26a69a" if bullish else "#ef5350",
                "shape": "arrowUp" if bullish else "arrowDown",
                "text": label,
            }
        )

    zones: list[dict[str, Any]] = []
    for gap in structure.fvgs[-10:]:
        if gap.mitigated:
            continue
        bullish = gap.bias is Bias.BULLISH
        zones.append(
            {
                "timeFrom": gap.time_from_sec,
                "timeTo": gap.time_to_sec,
                "priceTop": gap.top,
                "priceBottom": gap.bottom,
                "color": (
                    "rgba(38, 166, 154, 0.18)"
                    if bullish
                    else "rgba(239, 83, 80, 0.18)"
                ),
                "borderColor": "#26a69a" if bullish else "#ef5350",
                "title": "FVG",
            }
        )

    return {"markers": markers, "levels": [], "zones": zones}


def _headline(outcome: TradeOutcome, plan: TradePlan | None) -> str:
    side = f" · {plan.side.value.upper()}" if plan is not None else ""
    titles = {
        TradeOutcome.TAKE_PROFIT: "TP",
        TradeOutcome.STOP_LOSS: "SL",
        TradeOutcome.AMBIGUOUS: "DRAW",
        TradeOutcome.SKIP: "SKIP",
        TradeOutcome.OPEN: "NO HIT",
    }
    return f"{titles.get(outcome, outcome.value.upper())}{side}"


def _short_note(
    outcome: TradeOutcome,
    plan: TradePlan | None,
    execution_map: StructureMap,
) -> str:
    if outcome is TradeOutcome.AMBIGUOUS:
        return "TP и SL на одной свече"
    if outcome is TradeOutcome.SKIP:
        return "Ордер не выставлялся"
    if outcome is TradeOutcome.OPEN:
        return "Хвост без касания ордеров"
    if plan is None:
        return ""

    last = execution_map.events[-1] if execution_map.events else None
    if outcome is TradeOutcome.STOP_LOSS and last is not None:
        if last.kind is StructureEventKind.CHOCH:
            return "CHoCH перед стопом"
        if execution_map.breaks and execution_map.breaks[-1].kind is BreakKind.FALSE:
            return "Ложный пробой рядом"
    if outcome is TradeOutcome.TAKE_PROFIT:
        if plan.side is Side.LONG and execution_map.bias is Bias.BULLISH:
            return "По структуре"
        if plan.side is Side.SHORT and execution_map.bias is Bias.BEARISH:
            return "По структуре"
        if execution_map.bias is not Bias.RANGE:
            return "Против локальной структуры"
    return ""


def _outcome_short(outcome: TradeOutcome) -> str:
    return {
        TradeOutcome.TAKE_PROFIT: "TP",
        TradeOutcome.STOP_LOSS: "SL",
        TradeOutcome.AMBIGUOUS: "DRAW",
        TradeOutcome.SKIP: "SKIP",
        TradeOutcome.OPEN: "—",
    }.get(outcome, outcome.value.upper())


def _outcome_tone(outcome: TradeOutcome) -> str:
    return {
        TradeOutcome.TAKE_PROFIT: "good",
        TradeOutcome.STOP_LOSS: "bad",
        TradeOutcome.AMBIGUOUS: "warn",
        TradeOutcome.SKIP: "neutral",
        TradeOutcome.OPEN: "neutral",
    }.get(outcome, "neutral")


def _bias_short(bias: Bias) -> str:
    return {
        Bias.BULLISH: "BULL",
        Bias.BEARISH: "BEAR",
        Bias.RANGE: "RANGE",
    }[bias]


def _bias_tone(bias: Bias) -> str:
    return {
        Bias.BULLISH: "good",
        Bias.BEARISH: "bad",
        Bias.RANGE: "neutral",
    }[bias]


def _alignment_chip(plan: TradePlan, structure: StructureMap) -> DebriefChip:
    if structure.bias is Bias.RANGE:
        return DebriefChip("ALIGN", "RANGE", "warn")
    aligned = (
        (plan.side is Side.LONG and structure.bias is Bias.BULLISH)
        or (plan.side is Side.SHORT and structure.bias is Bias.BEARISH)
    )
    return DebriefChip(
        "ALIGN",
        "WITH" if aligned else "AGAINST",
        "good" if aligned else "warn",
    )
