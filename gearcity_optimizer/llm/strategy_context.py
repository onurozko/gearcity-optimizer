"""Build compact structured context for LLM design strategy prompts."""

from __future__ import annotations

from typing import Any

from gearcity_optimizer.core.component_priorities import get_adjusted_vehicle_weights
from gearcity_optimizer.core.models import VehicleType
from gearcity_optimizer.core.slider_registry import list_sliders, wiki_model_available
from gearcity_optimizer.importers.component_choices import ComponentChoice, choice_type_label
from gearcity_optimizer.reports.component_choice_recommender import (
    ComponentChoiceRecommendationResult,
)


def _choice_names(choices: list[ComponentChoice], choice_type: str) -> list[str]:
    return sorted(
        {
            choice.display_name
            for choice in choices
            if choice.choice_type == choice_type
        }
    )


def _top_candidate_summary(
    choice_result: ComponentChoiceRecommendationResult | None,
) -> dict[str, dict[str, object]]:
    if choice_result is None:
        return {}
    summary: dict[str, dict[str, object]] = {}
    for item in choice_result.choices:
        if not item.candidates:
            continue
        top = item.candidates[0]
        summary[item.choice_type] = {
            "top_candidate": top.component_name,
            "suitability": top.total_score,
            "confidence": item.confidence,
            "auto_pick_status": item.auto_pick_status,
            "penalties": list(top.penalties),
            "reason": item.reason,
        }
    return summary


def _real_slider_labels() -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for slider in list_sliders():
        grouped.setdefault(slider.section, []).append(slider.label)
    return {section: sorted(labels) for section, labels in grouped.items()}


def build_design_strategy_context(
    *,
    vehicle_type: VehicleType,
    cost_mode: str,
    year: int,
    skills: dict[str, float],
    available_choices: list[ComponentChoice],
    deterministic_result: ComponentChoiceRecommendationResult | None = None,
    deterministic_warnings: list[str] | None = None,
    formula_influence_summary: list[str] | None = None,
) -> dict[str, Any]:
    """Build compact JSON-serializable context for the LLM."""
    priorities = get_adjusted_vehicle_weights(vehicle_type)
    choice_types = sorted({choice.choice_type for choice in available_choices})
    available_by_type = {
        choice_type: _choice_names(available_choices, choice_type)
        for choice_type in choice_types
    }

    parsed_stats: dict[str, dict[str, object]] = {}
    for choice_type in choice_types:
        items = [choice for choice in available_choices if choice.choice_type == choice_type]
        parsed_stats[choice_type] = {
            choice.display_name: dict(choice.stats)
            for choice in items[:6]
            if choice.stats
        }

    context: dict[str, Any] = {
        "vehicle_type": vehicle_type.name,
        "cost_mode": cost_mode,
        "year": year,
        "skills": {key: round(value, 1) for key, value in skills.items()},
        "vehicle_priorities": {
            key: round(value, 3) for key, value in priorities.items() if value >= 0.05
        },
        "available_choices": available_by_type,
        "parsed_component_stats": parsed_stats,
        "real_sliders": _real_slider_labels() if wiki_model_available() else {},
        "deterministic_top_candidates": _top_candidate_summary(deterministic_result),
        "deterministic_warnings": list(deterministic_warnings or []),
        "formula_influence_summary": list(formula_influence_summary or [])[:12],
        "instructions": (
            "Propose sensible component choices and high-level slider strategy for this "
            "vehicle setup. Prefer mainstream/practical components for balanced passenger "
            "vehicles. Avoid primitive layouts or valvetrains when better options exist. "
            "Hard physical rules: predicted engine torque must not exceed gearbox max "
            "torque support; engine length and width must fit the chassis engine bay. "
            "Each forward gear adds ~10 lb-ft base gearbox torque capacity in the wiki "
            "formula; prefer higher gear_count when torque margin is tight. "
            "When fuel or dependability are high vehicle priorities, favor fuel-economy "
            "slider guidance over maximum performance. Return JSON only."
        ),
    }
    if deterministic_result is not None:
        context["deterministic_disclaimer"] = (
            "Deterministic scorer rankings are included for reference only. "
            "Use contextual judgement, but only choose from available_choices."
        )
    return context


def format_choice_types_for_prompt(available_choices: list[ComponentChoice]) -> str:
    """Human-readable choice type listing for debugging."""
    lines: list[str] = []
    grouped: dict[str, list[str]] = {}
    for choice in available_choices:
        grouped.setdefault(choice.choice_type, []).append(choice.display_name)
    for choice_type in sorted(grouped):
        labels = ", ".join(sorted(set(grouped[choice_type]))[:8])
        lines.append(f"- {choice_type_label(choice_type)}: {labels}")
    return "\n".join(lines)
