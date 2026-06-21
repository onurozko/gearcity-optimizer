"""Unified Design Optimizer combining component choices and slider controls."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from gearcity_optimizer.core.models import VehicleType
from gearcity_optimizer.importers.component_choices import ComponentChoice, get_available_component_choices
from gearcity_optimizer.reports.component_choice_recommender import (
    ComponentChoiceRecommendationResult,
    ChoiceRecommendation,
    recommend_component_choices,
)
from gearcity_optimizer.reports.design_objective import DesignObjectiveEvaluation, evaluate_design_objective
from gearcity_optimizer.reports.slider_optimizer import (
    SliderOptimizationInput,
    SliderOptimizationResult,
    optimize_real_slider_settings,
)

ComponentChoiceMode = Literal["auto", "manual"]


@dataclass(frozen=True)
class DesignOptimizationInput:
    """Inputs for full design optimization."""

    vehicle_type: VehicleType
    year: int
    cost_mode: str
    chassis_skill: float = 0.0
    engine_skill: float = 0.0
    gearbox_skill: float = 0.0
    vehicle_skill: float = 0.0
    depth: str = "balanced"
    component_choice_mode: ComponentChoiceMode = "auto"
    manual_choices: dict[str, ComponentChoice] | None = None


@dataclass(frozen=True)
class DesignOptimizationResult:
    """Recommended component choices, slider controls, and predicted outputs."""

    component_choices: ComponentChoiceRecommendationResult | None
    slider_result: SliderOptimizationResult
    available_choice_count: int
    component_choice_mode: ComponentChoiceMode
    objective: DesignObjectiveEvaluation | None = None
    warnings: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


def optimize_design(input_data: DesignOptimizationInput) -> DesignOptimizationResult:
    """Recommend component choices and slider controls for a design setup."""
    skills = {
        "chassis": input_data.chassis_skill,
        "engine": input_data.engine_skill,
        "gearbox": input_data.gearbox_skill,
        "vehicle": input_data.vehicle_skill,
    }
    available_choices = get_available_component_choices(
        input_data.year,
        input_data.chassis_skill,
        input_data.engine_skill,
        input_data.gearbox_skill,
        input_data.vehicle_skill,
    )

    choice_result: ComponentChoiceRecommendationResult | None = None
    selected_choices: dict[str, ComponentChoice] = {}
    warnings: list[str] = []

    if available_choices:
        manual = input_data.manual_choices if input_data.component_choice_mode == "manual" else None
        choice_result = recommend_component_choices(
            vehicle_type=input_data.vehicle_type,
            cost_mode=input_data.cost_mode,
            year=input_data.year,
            skills=skills,
            available_choices=available_choices,
            manual_selections=manual,
            component_choice_mode=input_data.component_choice_mode,
        )
        warnings.extend(choice_result.warnings)

        if input_data.component_choice_mode == "manual":
            selected_choices = dict(input_data.manual_choices or {})
        else:
            for recommendation in choice_result.choices:
                if recommendation.recommended_choice is not None:
                    selected_choices[recommendation.choice_type] = recommendation.recommended_choice
    else:
        warnings.append(
            "Components.xml is required for component/dropdown recommendations. "
            "Slider optimization can still run, but component choices cannot be ranked."
        )

    slider_result = optimize_real_slider_settings(
        SliderOptimizationInput(
            vehicle_type=input_data.vehicle_type,
            year=input_data.year,
            cost_mode=input_data.cost_mode,
            chassis_skill=input_data.chassis_skill,
            engine_skill=input_data.engine_skill,
            gearbox_skill=input_data.gearbox_skill,
            vehicle_skill=input_data.vehicle_skill,
            depth=input_data.depth,  # type: ignore[arg-type]
            selected_choices=selected_choices or None,
        )
    )

    objective: DesignObjectiveEvaluation | None = None
    if slider_result.predicted_outputs and not slider_result.optimization_disabled:
        objective = evaluate_design_objective(
            input_data.vehicle_type,
            slider_result.predicted_outputs,
        )
        warnings.extend(objective.warnings)

    limitations = list(slider_result.limitations)
    if choice_result is None:
        limitations.append(
            "Import Components.xml to enable component/dropdown candidate inspection."
        )
    else:
        limitations.append(
            "Component suitability scoring uses parsed Components.xml stats and heuristics. "
            "Auto-pick is experimental; review alternatives before copying into GearCity."
        )

    return DesignOptimizationResult(
        component_choices=choice_result,
        slider_result=slider_result,
        available_choice_count=len(available_choices),
        component_choice_mode=input_data.component_choice_mode,
        objective=objective,
        warnings=warnings + list(slider_result.warnings),
        limitations=limitations,
    )


def choice_recommendations_for_section(
    result: DesignOptimizationResult,
    section: str,
) -> list[ChoiceRecommendation]:
    """Return component choice recommendations for one section."""
    if result.component_choices is None:
        return []
    normalized = section.strip().lower()
    return [item for item in result.component_choices.choices if item.section == normalized]
