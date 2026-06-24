"""Build LLM repair context when a design fails physical or quality checks."""

from __future__ import annotations

from typing import Any

from gearcity_optimizer.core.models import VehicleType
from gearcity_optimizer.importers.component_choices import ComponentChoice
from gearcity_optimizer.llm.strategy_context import build_design_strategy_context
from gearcity_optimizer.reports.design_objective import DesignScore
from gearcity_optimizer.reports.design_physical_constraints import (
    PhysicalFitAssessment,
    physical_fit_summary_lines,
)


def build_design_repair_context(
    *,
    vehicle_type: VehicleType,
    cost_mode: str,
    year: int,
    skills: dict[str, float],
    available_choices: list[ComponentChoice],
    selected_choices: dict[str, ComponentChoice],
    design_score: DesignScore,
    physical_fit: PhysicalFitAssessment,
    repair_attempt: int,
    max_attempts: int,
) -> dict[str, Any]:
    """Compact context for an LLM repair pass after a failed design."""
    base = build_design_strategy_context(
        vehicle_type=vehicle_type,
        cost_mode=cost_mode,
        year=year,
        skills=skills,
        available_choices=available_choices,
        deterministic_result=None,
        deterministic_warnings=None,
    )
    base["repair_mode"] = True
    base["repair_attempt"] = repair_attempt
    base["max_repair_attempts"] = max_attempts
    base["previous_design"] = {
        "quality_status": design_score.quality_status,
        "global_score": design_score.total_score,
        "failed_thresholds": list(design_score.failed_thresholds),
        "component_choices": {
            choice_type: choice.display_name
            for choice_type, choice in sorted(selected_choices.items())
        },
    }
    base["physical_fit_failures"] = list(physical_fit.violations)
    base["physical_fit_summary"] = physical_fit_summary_lines(physical_fit)
    base["physical_fit_numbers"] = {
        "engine_torque_lbft": physical_fit.engine_torque_lbft,
        "gearbox_max_torque_lbft": physical_fit.gearbox_max_torque_lbft,
        "torque_margin_ratio": physical_fit.torque_margin_ratio,
        "engine_length_in": physical_fit.engine_length_in,
        "engine_width_in": physical_fit.engine_width_in,
        "chassis_max_length_in": physical_fit.chassis_max_length_in,
        "chassis_max_width_in": physical_fit.chassis_max_width_in,
    }
    base["instructions"] = (
        "The previous design FAILED physical fit checks or scored poorly. "
        "Propose a REPLACEMENT strategy that fixes the failures below. "
        "Return the same JSON schema as a normal strategy.\n\n"
        "Torque mismatch fixes (pick several):\n"
        "- Lower engine sliders: Engine Torque, Performance Torque, Performance, "
        "Layout Displacement, Layout Bore/Stroke if too large.\n"
        "- Raise gearbox capacity: Torque Max Input, more forward gears (gear_count), "
        "stronger gearbox_type if available.\n"
        "- Smaller engine: fewer cylinders, smaller displacement-friendly layout.\n\n"
        "Engine bay mismatch fixes:\n"
        "- Pick a chassis frame with a larger engine bay OR a smaller engine layout.\n"
        "- Lower layout length/width sliders.\n\n"
        "Do not repeat the same component set if it already failed. "
        "Prefer practical, feasible designs over maximum performance."
    )
    return base
