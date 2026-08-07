"""Post-trade explanations and chart overlay payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from retrade.domain.candles import CandleSeries
from retrade.domain.smc import (
    Bias,
    BreakKind,
    LevelStrength,
    StructureEventKind,
    StructureMap,
    SwingKind,
    analyze_series,
)
from retrade.domain.trading import Side, TradeOutcome, TradePlan


@dataclass(frozen=True, slots=True)
class Explanation:
    """Human-readable debrief + serializable chart overlays."""

    summary_lines: tuple[str, ...]
    overlays: dict[str, Any]
    execution_map: StructureMap
    context_map: StructureMap | None

    @property
    def text(self) -> str:
        return "\n".join(self.summary_lines)


def build_explanation(
    *,
    execution_series: CandleSeries,
    context_series: CandleSeries | None,
    outcome: TradeOutcome,
    plan: TradePlan | None,
) -> Explanation:
    """Analyze revealed price action and describe why the round resolved."""
    execution_map = analyze_series(execution_series)
    context_map = analyze_series(context_series) if context_series is not None else None

    lines: list[str] = []
    lines.append(_outcome_line(outcome, plan))
    lines.append(
        f"Структура на {execution_map.timeframe}: {_bias_ru(execution_map.bias)}."
    )
    if context_map is not None:
        lines.append(
            f"Контекст {_upper_tf(context_map.timeframe)}: "
            f"{_bias_ru(context_map.bias)}."
        )

    if plan is not None:
        lines.extend(_plan_context_lines(plan, execution_map))

    recent_events = execution_map.events[-3:]
    if recent_events:
        lines.append("Ключевые события структуры:")
        for event in recent_events:
            label = "BOS" if event.kind is StructureEventKind.BOS else "CHoCH"
            lines.append(
                f"  • {label} {_bias_ru(event.bias)} @ {event.price:.2f}"
            )
    else:
        lines.append("Явных BOS/CHoCH на видимом участке мало — рынок скорее в range.")

    open_fvgs = [g for g in execution_map.fvgs if not g.mitigated][-3:]
    if open_fvgs:
        lines.append("Активные имбалансы (FVG):")
        for gap in open_fvgs:
            lines.append(
                f"  • {_bias_ru(gap.bias)} FVG {gap.bottom:.2f}–{gap.top:.2f}"
            )

    strong = [lv for lv in execution_map.levels if lv.strength is LevelStrength.STRONG]
    if strong:
        ref = _ref_price(plan, execution_series)
        nearest = sorted(strong, key=lambda lv: abs(lv.price - ref))[:3]
        lines.append("Сильные уровни рядом:")
        for lv in nearest:
            side = "high" if lv.kind is SwingKind.HIGH else "low"
            lines.append(f"  • {side} {lv.price:.2f} (touches={lv.touches})")

    recent_breaks = execution_map.breaks[-3:]
    if recent_breaks:
        lines.append("Пробои:")
        for br in recent_breaks:
            kind = "истинный" if br.kind is BreakKind.TRUE else "ложный"
            lines.append(
                f"  • {kind} пробой {br.level_price:.2f} ({_bias_ru(br.bias)})"
            )

    if plan is not None and outcome in {
        TradeOutcome.TAKE_PROFIT,
        TradeOutcome.STOP_LOSS,
        TradeOutcome.AMBIGUOUS,
    }:
        lines.append(_trade_read(plan, outcome, execution_map, context_map))

    overlays = structure_to_overlays(execution_map)
    return Explanation(
        summary_lines=tuple(lines),
        overlays=overlays,
        execution_map=execution_map,
        context_map=context_map,
    )


def structure_to_overlays(structure: StructureMap) -> dict[str, Any]:
    """JSON-serializable overlays for Lightweight Charts bridge."""
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

    levels: list[dict[str, Any]] = []
    for lv in structure.levels:
        if lv.strength is LevelStrength.WEAK and lv.touches == 0:
            continue
        strong = lv.strength is LevelStrength.STRONG
        levels.append(
            {
                "price": lv.price,
                "color": "#f5a623" if strong else "#787b86",
                "title": ("S" if strong else "W")
                + ("H" if lv.kind is SwingKind.HIGH else "L"),
                "lineWidth": 2 if strong else 1,
                "lineStyle": 0 if strong else 2,  # solid / dashed
            }
        )

    # Keep chart readable.
    levels = levels[-14:]

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
                "color": "rgba(38, 166, 154, 0.18)"
                if bullish
                else "rgba(239, 83, 80, 0.18)",
                "borderColor": "#26a69a" if bullish else "#ef5350",
                "title": "FVG",
            }
        )

    return {"markers": markers, "levels": levels, "zones": zones}


def _outcome_line(outcome: TradeOutcome, plan: TradePlan | None) -> str:
    mapping = {
        TradeOutcome.TAKE_PROFIT: "Результат: Take Profit.",
        TradeOutcome.STOP_LOSS: "Результат: Stop Loss.",
        TradeOutcome.AMBIGUOUS: "Результат: ничья (TP и SL на одной 15M-свече).",
        TradeOutcome.SKIP: "Сделка пропущена — ниже разбор структуры без ордера.",
        TradeOutcome.OPEN: "Хвост сценария закончился без касания TP/SL.",
    }
    base = mapping.get(outcome, f"Результат: {outcome.value}.")
    if plan is None:
        return base
    return f"{base} Сторона: {plan.side.value.upper()}."


def _plan_context_lines(plan: TradePlan, structure: StructureMap) -> list[str]:
    aligned = (
        (plan.side is Side.LONG and structure.bias is Bias.BULLISH)
        or (plan.side is Side.SHORT and structure.bias is Bias.BEARISH)
    )
    if structure.bias is Bias.RANGE:
        return ["Вход против неясного range-контекста на рабочем ТФ."]
    if aligned:
        return ["Вход в сторону текущей структуры рабочего ТФ."]
    return ["Вход против структуры рабочего ТФ — повышенный риск."]


def _trade_read(
    plan: TradePlan,
    outcome: TradeOutcome,
    execution_map: StructureMap,
    context_map: StructureMap | None,
) -> str:
    htf = ""
    if context_map is not None:
        htf = f" HTF-bias: {_bias_ru(context_map.bias)}."

    if outcome is TradeOutcome.TAKE_PROFIT:
        return (
            "Цена дошла до TP: движение совпало с выбранной стороной."
            + htf
        )
    if outcome is TradeOutcome.STOP_LOSS:
        last = execution_map.events[-1] if execution_map.events else None
        extra = ""
        if last is not None and last.kind is StructureEventKind.CHOCH:
            extra = " Перед стопом был CHoCH — смена структуры."
        elif execution_map.breaks and execution_map.breaks[-1].kind is BreakKind.FALSE:
            extra = " Рядом ложный пробой — типичная ловушка ликвидности."
        return "Сработал SL: цена пошла против позиции." + extra + htf
    return (
        "Ambiguous bar: по OHLC нельзя восстановить порядок TP/SL." + htf
    )


def _bias_ru(bias: Bias) -> str:
    return {
        Bias.BULLISH: "бычий",
        Bias.BEARISH: "медвежий",
        Bias.RANGE: "range",
    }[bias]


def _upper_tf(tf: str) -> str:
    return tf.upper()


def _ref_price(plan: TradePlan | None, series: CandleSeries) -> float:
    if plan is not None:
        return plan.entry
    if series.candles:
        return series.candles[-1].close
    return 0.0
