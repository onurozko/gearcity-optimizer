"""Basic part recommendation scaffolding built on tech availability and priorities."""

from __future__ import annotations

from dataclasses import dataclass, field

from gearcity_optimizer.core.component_priorities import (
    calculate_component_priorities,
    format_stat_label,
)
from gearcity_optimizer.core.cost_mode import COST_MODE_DESCRIPTIONS, CostMode, parse_cost_mode
from gearcity_optimizer.core.models import VehicleType
from gearcity_optimizer.importers.components_xml import (
    ComponentCatalog,
    classify_components,
    filter_available_components,
    validate_year_input,
)


@dataclass(frozen=True)
class RecommendationInput:
    """Inputs for a basic recommendation pass."""

    vehicle_type_name: str
    year: int
    cost_mode: str
    chassis_skill: float
    engine_skill: float
    gearbox_skill: float
    vehicle_skill: float


@dataclass(frozen=True)
class RecommendationProfile:
    """Weighted focus areas for chassis, engine, gearbox, and vehicle design."""

    cost_mode: CostMode
    cost_mode_description: str
    chassis_focus: list[str]
    engine_focus: list[str]
    gearbox_focus: list[str]
    vehicle_focus: list[str]
    component_priorities: dict[str, list[tuple[str, float]]]


@dataclass(frozen=True)
class RecommendationResult:
    """V1 recommendation output with availability summary and focus bullets."""

    available_component_count: int
    unavailable_component_count: int
    priority_profile: RecommendationProfile
    cost_mode_notes: list[str]
    recommended_focus: list[str]
    limitations: list[str] = field(default_factory=list)


def _skill_levels_from_input(inputs: RecommendationInput) -> dict[str, float]:
    return {
        "chassis": inputs.chassis_skill,
        "engine": inputs.engine_skill,
        "gearbox": inputs.gearbox_skill,
        "vehicle": inputs.vehicle_skill,
    }


def recommendation_profile(
    vehicle_type: VehicleType,
    cost_mode: CostMode | str,
) -> RecommendationProfile:
    """Build weighted slider focus areas from vehicle type priorities and cost mode."""
    mode = parse_cost_mode(cost_mode.value if isinstance(cost_mode, CostMode) else cost_mode)
    priorities = calculate_component_priorities(vehicle_type)

    def top_labels(component: str, limit: int = 4) -> list[str]:
        items = priorities.get(component, [])
        return [
            format_stat_label(component, item.stat)
            for item in items[:limit]
        ]

    chassis_focus = top_labels("chassis")
    engine_focus = top_labels("engine")
    gearbox_focus = top_labels("gearbox")
    vehicle_focus = top_labels("vehicle_design")

    if mode is CostMode.CHEAP:
        cheap_bias = [
            "manufacturing cost",
            "dependability",
            "reliability",
            "fuel economy",
        ]
        chassis_focus = _merge_focus(chassis_focus, cheap_bias, limit=5)
        engine_focus = _merge_focus(engine_focus, cheap_bias, limit=5)
        gearbox_focus = _merge_focus(gearbox_focus, ["max torque", "reliability"], limit=5)
        vehicle_focus = _merge_focus(vehicle_focus, ["dependability", "cargo"], limit=5)
    elif mode is CostMode.LUXURY:
        luxury_bias = [
            "comfort",
            "smoothness",
            "luxury",
            "safety",
            "material quality",
        ]
        chassis_focus = _merge_focus(chassis_focus, luxury_bias, limit=5)
        engine_focus = _merge_focus(engine_focus, luxury_bias, limit=5)
        gearbox_focus = _merge_focus(gearbox_focus, ["comfort", "performance"], limit=5)
        vehicle_focus = _merge_focus(vehicle_focus, luxury_bias, limit=5)

    serialized_priorities = {
        component: [(item.stat, item.priority) for item in items]
        for component, items in priorities.items()
    }

    return RecommendationProfile(
        cost_mode=mode,
        cost_mode_description=COST_MODE_DESCRIPTIONS[mode],
        chassis_focus=chassis_focus,
        engine_focus=engine_focus,
        gearbox_focus=gearbox_focus,
        vehicle_focus=vehicle_focus,
        component_priorities=serialized_priorities,
    )


def _merge_focus(primary: list[str], secondary: list[str], *, limit: int) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for label in primary + secondary:
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(label)
        if len(merged) >= limit:
            break
    return merged


def build_recommendation_result(
    *,
    vehicle_type: VehicleType,
    inputs: RecommendationInput,
    catalog: ComponentCatalog | None,
) -> RecommendationResult:
    """Produce a v1 recommendation summary without exact part selection."""
    validate_year_input(inputs.year)
    profile = recommendation_profile(vehicle_type, inputs.cost_mode)
    skill_levels = _skill_levels_from_input(inputs)

    available_count = 0
    unavailable_count = 0
    if catalog is not None:
        available = filter_available_components(catalog, inputs.year, skill_levels)
        available_count = len(available)
        _, locked = classify_components(catalog, inputs.year, skill_levels)
        unavailable_count = len(locked)

    cost_mode_notes = [profile.cost_mode_description]
    recommended_focus = _recommended_focus_bullets(vehicle_type.name, profile)
    limitations = [
        "Available tech has been filtered by year and skill. Exact best-part "
        "selection is experimental until Components.xml category parsing is verified.",
    ]
    if catalog is None:
        limitations.append(
            "Import Components.xml to filter tech availability by year and skill."
        )

    return RecommendationResult(
        available_component_count=available_count,
        unavailable_component_count=unavailable_count,
        priority_profile=profile,
        cost_mode_notes=cost_mode_notes,
        recommended_focus=recommended_focus,
        limitations=limitations,
    )


def _recommended_focus_bullets(
    vehicle_type_name: str,
    profile: RecommendationProfile,
) -> list[str]:
    """Return human-readable focus bullets for v1 output."""
    bullets = [
        f"Vehicle type: {vehicle_type_name}",
        f"Cost mode: {profile.cost_mode.value}",
        f"Chassis focus: {', '.join(profile.chassis_focus) or 'general balance'}",
        f"Engine focus: {', '.join(profile.engine_focus) or 'general balance'}",
        f"Gearbox focus: {', '.join(profile.gearbox_focus) or 'general balance'}",
        f"Vehicle/coachwork focus: {', '.join(profile.vehicle_focus) or 'general balance'}",
    ]

    if profile.cost_mode is CostMode.CHEAP:
        bullets.append(
            "Cheap mode: prioritize torque, dependability, cargo/utility, and "
            "manufacturing cost; avoid expensive luxury or smoothness tech unless "
            "the vehicle type demands it."
        )
        bullets.append("Gearbox max torque support matters for work-focused types.")
    elif profile.cost_mode is CostMode.LUXURY:
        bullets.append(
            "Luxury mode: keep core vehicle-type strengths, but allow better "
            "smoothness, comfort, safety, and material quality where useful."
        )
    else:
        bullets.append(
            "Balanced mode: spend on the stats this vehicle type cares about most "
            "while keeping cost under control."
        )

    return bullets
