"""Basic part recommendation scaffolding built on tech availability and priorities."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from gearcity_optimizer.core.component_priorities import (
    calculate_component_priorities,
    enrich_priorities_for_display,
    format_stat_label,
    get_adjusted_vehicle_weights,
)
from gearcity_optimizer.core.cost_mode import COST_MODE_DESCRIPTIONS, CostMode, parse_cost_mode
from gearcity_optimizer.core.models import VehicleType
from gearcity_optimizer.importers.components_xml import (
    ComponentCatalog,
    classify_components,
    filter_available_components,
    validate_year_input,
)

WORK_NAME_HINTS = (
    "truck",
    "van",
    "utility",
    "commercial",
    "pickup",
    "hauler",
)

RATING_DISPLAY = {
    "performance": "performance",
    "drivability": "drivability",
    "luxury": "luxury",
    "safety": "safety",
    "fuel": "fuel economy",
    "power": "power/torque",
    "cargo": "cargo/utility",
    "dependability": "dependability",
}

FOCUS_DEDUPE_KEYS: dict[str, str] = {
    "max torque": "max_torque",
    "maximum torque support": "max_torque",
    "design focus: dependability": "dependability",
    "dependability": "dependability",
    "fuel economy rating": "fuel_economy",
    "fuel economy": "fuel_economy",
    "testing: fuel economy": "fuel_economy",
    "engine reliability rating": "reliability",
    "gearbox reliability rating": "reliability",
    "reliability rating": "reliability",
    "reliability": "reliability",
    "testing: reliability": "reliability",
    "chassis durability rating": "durability",
    "durability rating": "durability",
    "manufacturing cost": "manufacturing_cost",
    "comfort rating": "comfort",
    "smoothness rating": "smoothness",
    "performance rating": "performance",
}

PREFERRED_FOCUS_LABELS: dict[str, str] = {
    "max torque": "Maximum Torque Support",
    "maximum torque support": "Maximum Torque Support",
    "dependability": "Design Focus: Dependability",
    "fuel economy": "Fuel Economy Rating",
}


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
class ComponentFocusSection:
    """Focus priorities and cost-mode guidance for one component area."""

    top_priorities: list[str]
    cost_mode_adjustment: str


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
    """Structured recommendation output for UI and CLI previews."""

    available_component_count: int
    unavailable_component_count: int
    priority_profile: RecommendationProfile
    strategy_summary: str
    chassis_section: ComponentFocusSection
    engine_section: ComponentFocusSection
    gearbox_section: ComponentFocusSection
    design_testing_focus: list[str]
    avoid: list[str]
    gearbox_guidance: str
    cost_mode_notes: list[str]
    limitations: list[str] = field(default_factory=list)
    recommended_focus: list[str] = field(default_factory=list)


def parse_cost_mode_display(label: str) -> str:
    """Normalize a display cost mode label to cheap/balanced/luxury."""
    return parse_cost_mode(label.strip().lower()).value


def is_work_or_utility_focused(vehicle_type: VehicleType) -> bool:
    """Return True when the vehicle type emphasizes work, cargo, or utility."""
    cargo = vehicle_type.cargo
    power = vehicle_type.power
    name_lower = vehicle_type.name.lower()
    name_hint = any(hint in name_lower for hint in WORK_NAME_HINTS)

    if name_hint and (cargo >= 0.55 or power >= 0.55):
        return True

    return cargo >= 0.75 or power >= 0.75


def normalize_focus_labels(labels: list[str]) -> list[str]:
    """Remove duplicate focus labels that refer to the same concept."""
    seen_keys: set[str] = set()
    normalized: list[str] = []
    for label in labels:
        lowered = label.lower().strip()
        display = PREFERRED_FOCUS_LABELS.get(lowered, label)
        key = _focus_dedupe_key(display)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        normalized.append(display)
    return normalized


def _focus_dedupe_key(label: str) -> str:
    lowered = label.lower().strip()
    return FOCUS_DEDUPE_KEYS.get(lowered, lowered)


def _skill_levels_from_input(inputs: RecommendationInput) -> dict[str, float]:
    return {
        "chassis": inputs.chassis_skill,
        "engine": inputs.engine_skill,
        "gearbox": inputs.gearbox_skill,
        "vehicle": inputs.vehicle_skill,
    }


def _top_priority_labels(
    priorities: dict[str, list],
    component: str,
    *,
    limit: int = 4,
) -> list[str]:
    items = enrich_priorities_for_display(component, priorities.get(component, []))
    labels = [format_stat_label(component, item.stat) for item in items[: limit + 2]]
    return normalize_focus_labels(labels)[:limit]


def recommendation_profile(
    vehicle_type: VehicleType,
    cost_mode: CostMode | str,
) -> RecommendationProfile:
    """Build weighted slider focus areas from vehicle type priorities and cost mode."""
    mode = parse_cost_mode(cost_mode.value if isinstance(cost_mode, CostMode) else cost_mode)
    priorities = calculate_component_priorities(vehicle_type)

    chassis_focus = _top_priority_labels(priorities, "chassis")
    engine_focus = _top_priority_labels(priorities, "engine")
    gearbox_focus = _top_priority_labels(priorities, "gearbox")
    vehicle_focus = _top_priority_labels(priorities, "vehicle_design")

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


def _top_vehicle_rating_names(vehicle_type: VehicleType, limit: int = 3) -> list[str]:
    weights = get_adjusted_vehicle_weights(vehicle_type)
    ranked = sorted(
        ((name, value) for name, value in weights.items() if name != "quality"),
        key=lambda item: item[1],
        reverse=True,
    )
    return [RATING_DISPLAY.get(name, name) for name, _ in ranked[:limit]]


def build_strategy_summary(vehicle_type: VehicleType, cost_mode: CostMode) -> str:
    """Return a short plain-English strategy paragraph."""
    top = _top_vehicle_rating_names(vehicle_type)
    top_text = ", ".join(top)
    name = vehicle_type.name

    if cost_mode is CostMode.CHEAP:
        return (
            f"Build this as a practical low-cost {name.lower()}. Prioritize "
            f"{top_text}, and keep spending under control. Avoid expensive luxury, "
            f"racing, or over-advanced tech unless this vehicle type strongly needs it."
        )
    if cost_mode is CostMode.LUXURY:
        return (
            f"Build this {name.lower()} with room for higher-end choices. Keep "
            f"{top_text} as the core strengths, but allow more comfort, smoothness, "
            f"safety, material quality, and performance where they support the vehicle type."
        )
    return (
        f"Build this as a balanced {name.lower()}. Focus spending on {top_text}, "
        f"the stats this vehicle type cares about most, without extreme cost cutting "
        f"or unnecessary luxury overspend."
    )


def _component_cost_mode_adjustment(
    component: str,
    cost_mode: CostMode,
    vehicle_type: VehicleType,
) -> str:
    work_focused = is_work_or_utility_focused(vehicle_type)

    if component == "chassis":
        if cost_mode is CostMode.CHEAP:
            return (
                "Cheap: avoid expensive or overbuilt chassis choices unless they "
                "directly improve your top priorities."
            )
        if cost_mode is CostMode.LUXURY:
            return (
                "Luxury: allow stronger comfort, safety, and material quality if "
                "they support the vehicle type."
            )
        return "Balanced: spend on chassis strengths that match this vehicle type most."

    if component == "engine":
        if cost_mode is CostMode.CHEAP:
            return (
                "Cheap: prefer reliable and efficient engines over high power unless "
                "power is a top vehicle-type priority."
            )
        if cost_mode is CostMode.LUXURY:
            return (
                "Luxury: allow smoother, stronger engines when they improve comfort "
                "or performance priorities."
            )
        return "Balanced: match engine spending to the vehicle type's top ratings."

    if component == "gearbox":
        if cost_mode is CostMode.CHEAP:
            if work_focused:
                return (
                    "Cheap: match gearbox torque support to the engine, but avoid "
                    "capacity far beyond what the engine needs."
                )
            return (
                "Cheap: do not overbuild torque capacity far beyond engine needs."
            )
        if cost_mode is CostMode.LUXURY:
            return (
                "Luxury: allow smoother, more refined gearbox choices when comfort "
                "or performance matter."
            )
        return "Balanced: enough torque support and reliability without unnecessary overspec."

    return ""


def build_gearbox_guidance(vehicle_type: VehicleType, cost_mode: CostMode) -> str:
    """Return gearbox torque guidance tailored to the vehicle type."""
    if is_work_or_utility_focused(vehicle_type):
        return (
            "Gearbox max torque support matters for this work-focused vehicle type. "
            "Match the engine, but avoid far more capacity than you need."
        )
    return (
        "Gearbox max torque support should safely match the engine, but do not "
        "overbuild it unnecessarily."
    )


def build_avoid_list(vehicle_type: VehicleType, cost_mode: CostMode) -> list[str]:
    """Return things to avoid based on vehicle type and cost mode."""
    weights = get_adjusted_vehicle_weights(vehicle_type)
    avoids: list[str] = []

    if cost_mode is CostMode.CHEAP:
        if weights.get("fuel", 0.0) >= 0.45:
            avoids.append("Avoid oversized engines if fuel economy matters.")
        if weights.get("luxury", 0.0) < 0.55:
            avoids.append(
                "Avoid luxury-heavy spending unless luxury is a top vehicle-type priority."
            )
        avoids.append(
            "Avoid gearbox torque capacity far beyond the selected engine's needs."
        )
        if weights.get("performance", 0.0) < 0.55:
            avoids.append(
                "Avoid racing or performance-focused tech if performance priority is low."
            )
        if weights.get("cargo", 0.0) < 0.55:
            avoids.append(
                "Avoid utility-first chassis or drivetrain overspend unless cargo matters."
            )
    elif cost_mode is CostMode.LUXURY:
        avoids.append("Avoid cutting comfort or safety so aggressively that luxury goals suffer.")
        avoids.append("Avoid cheap-feeling materials if material quality supports the vehicle type.")
        if weights.get("performance", 0.0) < 0.45:
            avoids.append("Avoid pure performance overspend if performance is not a core priority.")
    else:
        avoids.append("Avoid extreme cost cutting in areas the vehicle type values most.")
        avoids.append("Avoid luxury overspend in areas with low vehicle-type importance.")
        avoids.append("Avoid mismatched gearbox torque support relative to the engine.")

    return normalize_avoid_list(avoids)[:5]


def normalize_avoid_list(items: list[str]) -> list[str]:
    """Remove near-duplicate avoid guidance."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = re.sub(r"\s+", " ", item.lower().strip())
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _maybe_append_torque_note(
    engine_focus: list[str],
    vehicle_type: VehicleType,
) -> list[str]:
    """Add a conditional torque note without duplicating Torque in the list."""
    labels = list(engine_focus)
    keys = {_focus_dedupe_key(label) for label in labels}
    weights = get_adjusted_vehicle_weights(vehicle_type)
    if "torque" in keys:
        return labels
    if weights.get("power", 0.0) >= 0.55 or weights.get("cargo", 0.0) >= 0.55:
        labels.append("Torque if useful for this vehicle type")
    return labels


def build_recommendation_result(
    *,
    vehicle_type: VehicleType,
    inputs: RecommendationInput,
    catalog: ComponentCatalog | None,
) -> RecommendationResult:
    """Produce a structured recommendation summary without exact part selection."""
    validate_year_input(inputs.year)
    profile = recommendation_profile(vehicle_type, inputs.cost_mode)
    skill_levels = _skill_levels_from_input(inputs)

    available_count = 0
    unavailable_count = 0
    if catalog is not None:
        available_count = len(
            filter_available_components(catalog, inputs.year, skill_levels)
        )
        _, locked = classify_components(catalog, inputs.year, skill_levels)
        unavailable_count = len(locked)

    mode = profile.cost_mode
    strategy = build_strategy_summary(vehicle_type, mode)
    gearbox_guidance = build_gearbox_guidance(vehicle_type, mode)

    chassis_section = ComponentFocusSection(
        top_priorities=profile.chassis_focus,
        cost_mode_adjustment=_component_cost_mode_adjustment(
            "chassis", mode, vehicle_type
        ),
    )
    engine_section = ComponentFocusSection(
        top_priorities=_maybe_append_torque_note(profile.engine_focus, vehicle_type),
        cost_mode_adjustment=_component_cost_mode_adjustment(
            "engine", mode, vehicle_type
        ),
    )
    gearbox_section = ComponentFocusSection(
        top_priorities=profile.gearbox_focus,
        cost_mode_adjustment=_component_cost_mode_adjustment(
            "gearbox", mode, vehicle_type
        ),
    )

    design_testing = normalize_focus_labels(profile.vehicle_focus)
    avoid = build_avoid_list(vehicle_type, mode)
    limitations = [
        "Exact best-part selection is experimental until Components.xml category "
        "and stat parsing is fully verified.",
    ]
    if catalog is None:
        limitations.append(
            "Import Components.xml to filter tech availability by year and skill."
        )

    return RecommendationResult(
        available_component_count=available_count,
        unavailable_component_count=unavailable_count,
        priority_profile=profile,
        strategy_summary=strategy,
        chassis_section=chassis_section,
        engine_section=engine_section,
        gearbox_section=gearbox_section,
        design_testing_focus=design_testing,
        avoid=avoid,
        gearbox_guidance=gearbox_guidance,
        cost_mode_notes=[profile.cost_mode_description],
        limitations=limitations,
        recommended_focus=_legacy_focus_lines(inputs, profile, strategy, avoid),
    )


def _legacy_focus_lines(
    inputs: RecommendationInput,
    profile: RecommendationProfile,
    strategy: str,
    avoid: list[str],
) -> list[str]:
    """Compact lines for CLI output."""
    return [
        strategy,
        f"Chassis: {', '.join(profile.chassis_focus) or 'general balance'}",
        f"Engine: {', '.join(profile.engine_focus) or 'general balance'}",
        f"Gearbox: {', '.join(profile.gearbox_focus) or 'general balance'}",
        f"Design/testing: {', '.join(profile.vehicle_focus) or 'general balance'}",
        f"Avoid: {'; '.join(avoid[:3])}",
        f"Year {inputs.year}, cost mode {profile.cost_mode.value}",
    ]
