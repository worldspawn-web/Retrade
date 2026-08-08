"""Post-trade debrief model and chart overlay payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from retrade.domain.candles import CandleSeries
from retrade.domain.smc import (
    Bias,
    BreakKind,
    StructureEventKind,
    StructureLevel,
    StructureMap,
    SwingKind,
    analyze_series,
)
from retrade.domain.trading import Side, TradeOutcome, TradePlan
from retrade.domain.ui_prefs import (
    IndicatorPrefs,
    hex_to_rgba,
    line_style_code,
)


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
    prefs: IndicatorPrefs | None = None,
) -> Explanation:
    """Analyze revealed price action into a compact visual debrief."""
    prefs = prefs or IndicatorPrefs(
        show_bos=True,
        show_fvg=True,
        show_levels=False,
        show_swings=False,
    )
    execution_map = analyze_series(execution_series, swing_strength=2)
    context_map = (
        analyze_series(context_series, swing_strength=2)
        if context_series is not None
        else None
    )

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

    ref_price = plan.entry if plan is not None else None
    if ref_price is None and execution_series.candles:
        ref_price = execution_series.candles[-1].close

    return Explanation(
        outcome=outcome,
        headline=_headline(outcome, plan),
        chips=tuple(chips),
        note=_short_note(outcome, plan, execution_map),
        overlays=structure_to_overlays(
            execution_map,
            prefs=prefs,
            ref_price=ref_price,
        ),
        execution_map=execution_map,
        context_map=context_map,
    )


def structure_to_overlays(
    structure: StructureMap,
    *,
    prefs: IndicatorPrefs | None = None,
    show_bos: bool | None = None,
    show_fvg: bool | None = None,
    show_levels: bool | None = None,
    show_swings: bool | None = None,
    ref_price: float | None = None,
    max_levels: int = 2,
) -> dict[str, Any]:
    """Retrade overlays driven by indicator visibility + visual prefs."""
    prefs = prefs or IndicatorPrefs()
    use_bos = prefs.show_bos if show_bos is None else show_bos
    use_fvg = prefs.show_fvg if show_fvg is None else show_fvg
    use_levels = prefs.show_levels if show_levels is None else show_levels
    use_swings = prefs.show_swings if show_swings is None else show_swings

    markers: list[dict[str, Any]] = []
    segments: list[dict[str, Any]] = []
    labels: list[dict[str, Any]] = []
    bos = prefs.bos
    swings_v = prefs.swings
    fvg_v = prefs.fvg
    levels_v = prefs.levels

    if use_swings:
        for swing in structure.swings[-40:]:
            is_high = swing.kind is SwingKind.HIGH
            icon = _swing_icon(swings_v.icon, is_high=is_high)
            text = ""
            if swings_v.show_labels:
                text = "SH" if is_high else "SL"
            # HTML overlays — real triangles (LWC only has arrow shapes).
            labels.append(
                {
                    "time": swing.time_sec,
                    "price": swing.price,
                    "text": text,
                    "color": swings_v.color,
                    "fontSize": max(6, round(9 * swings_v.size)),
                    "align": "above" if is_high else "below",
                    "icon": icon,
                    "iconSize": max(4, round(7 * swings_v.size)),
                }
            )

    if use_bos:
        swing_by_index = {s.index: s for s in structure.swings}
        for event in structure.events[-20:]:
            bullish = event.bias is Bias.BULLISH
            label = "BOS" if event.kind is StructureEventKind.BOS else "CHoCH"
            color = bos.bull_color if bullish else bos.bear_color
            broken = swing_by_index.get(event.broken_swing_index)
            time_from = broken.time_sec if broken is not None else event.time_sec
            time_to = event.time_sec
            if time_to <= time_from:
                time_to = time_from + 1
            # No title — avoids duplicate label on the right price scale.
            segments.append(
                {
                    "timeFrom": time_from,
                    "timeTo": time_to,
                    "price": event.price,
                    "color": color,
                    "lineWidth": bos.line_width,
                    "lineStyle": line_style_code(bos.line_style),
                    "title": "",
                }
            )
            if bos.show_labels or bos.icon != "none":
                labels.append(
                    {
                        "time": time_to,
                        "price": event.price,
                        "text": label if bos.show_labels else "",
                        "color": color,
                        "fontSize": max(6, round(10 * bos.label_size)),
                        "align": "center",
                        "icon": bos.icon if bos.icon != "none" else "",
                        "iconSize": max(4, round(6 * bos.label_size)),
                    }
                )

    zones: list[dict[str, Any]] = []
    if use_fvg:
        for gap in structure.fvgs[-10:]:
            if gap.mitigated:
                continue
            bullish = gap.bias is Bias.BULLISH
            fill = hex_to_rgba(
                fvg_v.bull_color if bullish else fvg_v.bear_color,
                fvg_v.fill_opacity,
            )
            zones.append(
                {
                    "timeFrom": gap.time_from_sec,
                    "timeTo": gap.time_to_sec,
                    "priceTop": gap.top,
                    "priceBottom": gap.bottom,
                    "color": fill,
                    "borderColor": (
                        fvg_v.bull_border if bullish else fvg_v.bear_border
                    ),
                    "title": "",
                }
            )

    levels_payload: list[dict[str, Any]] = []
    if use_levels:
        chosen = nearest_levels(
            structure.levels,
            ref_price=ref_price,
            limit=max_levels,
        )
        for level in chosen:
            levels_payload.append(
                {
                    "price": level.price,
                    "color": levels_v.color,
                    "lineWidth": levels_v.line_width,
                    "lineStyle": line_style_code(levels_v.line_style),
                    # Empty title — price tick stays; text only via chart labels.
                    "title": "",
                    "axisLabelVisible": True,
                }
            )
            if levels_v.show_labels and levels_v.label_text:
                # Anchor near the right edge using last visible bar time if needed;
                # bridge places at chart right for price-only labels when time=null.
                labels.append(
                    {
                        "time": None,
                        "price": level.price,
                        "text": levels_v.label_text,
                        "color": levels_v.color,
                        "fontSize": max(6, round(10 * 1.0)),
                        "align": "above",
                        "icon": "",
                        "iconSize": 0,
                        "anchor": "right",
                    }
                )

    return {
        "markers": markers,
        "levels": levels_payload,
        "zones": zones,
        "segments": segments,
        "labels": labels,
    }


def _swing_icon(icon: str, *, is_high: bool) -> str:
    """HTML overlay icon name for a swing high/low."""
    if icon == "circle":
        return "circle"
    if icon == "square":
        return "square"
    # Equilateral CSS triangles (not LWC arrows).
    return "triangleDown" if is_high else "triangleUp"


def nearest_levels(
    levels: tuple[StructureLevel, ...],
    *,
    ref_price: float | None,
    limit: int = 2,
) -> tuple[StructureLevel, ...]:
    """Pick up to `limit` structure levels closest to ref_price."""
    if not levels or limit <= 0:
        return ()
    if ref_price is None:
        return levels[-limit:]
    ranked = sorted(levels, key=lambda lv: abs(lv.price - ref_price))
    return tuple(ranked[:limit])


def _headline(outcome: TradeOutcome, plan: TradePlan | None) -> str:
    side = f" · {plan.side.value.upper()}" if plan is not None else ""
    titles = {
        TradeOutcome.TAKE_PROFIT: "TP",
        TradeOutcome.STOP_LOSS: "SL",
        TradeOutcome.AMBIGUOUS: "DRAW",
        TradeOutcome.SKIP: "SKIP",
        TradeOutcome.OPEN: "NO HIT",
        TradeOutcome.EXIT: "EXIT",
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
    if outcome is TradeOutcome.EXIT:
        return "Закрытие по рынку"
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
        TradeOutcome.EXIT: "EXIT",
    }.get(outcome, outcome.value.upper())


def _outcome_tone(outcome: TradeOutcome) -> str:
    return {
        TradeOutcome.TAKE_PROFIT: "good",
        TradeOutcome.STOP_LOSS: "bad",
        TradeOutcome.AMBIGUOUS: "warn",
        TradeOutcome.SKIP: "neutral",
        TradeOutcome.OPEN: "neutral",
        TradeOutcome.EXIT: "accent",
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
