"""Derive component stat priorities from vehicle type importance weights."""

from __future__ import annotations

from gearcity_optimizer.core.component_models import ComponentPriority
from gearcity_optimizer.core.models import VehicleType
from gearcity_optimizer.core.terminology import format_priority_label

RATING_NAMES = (
    "performance",
    "drivability",
    "luxury",
    "safety",
    "fuel",
    "power",
    "cargo",
    "dependability",
    "quality",
)

QUALITY_BACKGROUND_WEIGHT = 0.45

CHASSIS_INFLUENCE: dict[str, dict[str, float]] = {
    "comfort": {"luxury": 0.45, "drivability": 0.25, "safety": 0.05},
    "performance": {"performance": 0.45, "drivability": 0.35, "fuel": 0.05},
    "strength": {
        "safety": 0.50,
        "dependability": 0.20,
        "cargo": 0.15,
        "power": 0.10,
    },
    "durability": {
        "dependability": 0.60,
        "cargo": 0.10,
        "power": 0.10,
        "safety": 0.10,
    },
    "low_weight": {"fuel": 0.35, "performance": 0.20, "drivability": 0.15},
    "engine_fit_room": {"power": 0.25, "cargo": 0.20, "performance": 0.15},
    "cargo_space": {"cargo": 0.65, "luxury": 0.10, "safety": 0.10},
}

ENGINE_INFLUENCE: dict[str, dict[str, float]] = {
    "horsepower": {"performance": 0.55, "power": 0.15, "drivability": 0.10},
    "torque": {
        "power": 0.65,
        "cargo": 0.20,
        "performance": 0.15,
        "dependability": 0.05,
    },
    "fuel_economy": {"fuel": 0.90, "dependability": 0.05},
    "reliability": {"dependability": 0.70, "cargo": 0.10, "fuel": 0.05},
    "smoothness": {"luxury": 0.55, "drivability": 0.15, "dependability": 0.10},
    "low_weight": {"fuel": 0.30, "performance": 0.15, "drivability": 0.10},
    "compact_size": {"cargo": 0.25, "fuel": 0.10, "safety": 0.05},
}

GEARBOX_INFLUENCE: dict[str, dict[str, float]] = {
    "max_torque": {
        "power": 0.50,
        "cargo": 0.20,
        "dependability": 0.20,
        "performance": 0.10,
    },
    "fuel_economy": {"fuel": 0.75, "dependability": 0.05},
    "performance": {"performance": 0.50, "drivability": 0.25, "power": 0.10},
    "reliability": {"dependability": 0.70, "power": 0.10, "cargo": 0.10},
    "comfort": {"luxury": 0.40, "drivability": 0.25, "dependability": 0.05},
    "low_weight": {"fuel": 0.20, "performance": 0.10},
}

VEHICLE_DESIGN_INFLUENCE: dict[str, dict[str, float]] = {
    "safety_focus": {"safety": 0.80, "dependability": 0.10},
    "dependability_focus": {"dependability": 0.80, "quality": 0.20},
    "cargo_focus": {"cargo": 0.90},
    "luxury_focus": {"luxury": 0.80},
    "style_focus": {"luxury": 0.25, "performance": 0.10},
    "material_quality": {
        "dependability": 0.25,
        "safety": 0.15,
        "luxury": 0.15,
        "quality": 0.25,
    },
    "testing_reliability": {"dependability": 0.60, "quality": 0.20},
    "testing_fuel": {"fuel": 0.80},
    "testing_performance": {"performance": 0.60, "drivability": 0.30},
    "testing_utility": {"cargo": 0.45, "dependability": 0.25, "luxury": 0.10},
}

COMPONENT_INFLUENCE = {
    "chassis": CHASSIS_INFLUENCE,
    "engine": ENGINE_INFLUENCE,
    "gearbox": GEARBOX_INFLUENCE,
    "vehicle_design": VEHICLE_DESIGN_INFLUENCE,
}

STAT_LABELS: dict[str, dict[str, str]] = {
    "chassis": {
        "comfort": "Comfort Rating",
        "performance": "Performance Rating",
        "strength": "Strength Rating",
        "durability": "Durability Rating",
        "low_weight": "Low weight",
        "engine_fit_room": "Engine fit room",
        "cargo_space": "Cargo space",
    },
    "engine": {
        "horsepower": "Horsepower",
        "torque": "Torque",
        "power_rating": "Power Rating",
        "fuel_economy": "Fuel Economy Rating",
        "reliability": "Reliability Rating",
        "smoothness": "Smoothness Rating",
        "low_weight": "Low weight",
        "compact_size": "Compact size",
    },
    "gearbox": {
        "max_torque": "Maximum Torque Support",
        "power": "Power Rating",
        "fuel_economy": "Fuel Economy Rating",
        "performance": "Performance Rating",
        "reliability": "Reliability Rating",
        "comfort": "Comfort Rating",
        "low_weight": "Low weight",
    },
    "vehicle_design": {
        "safety_focus": "Design Focus: Safety",
        "dependability_focus": "Design Focus: Dependability",
        "cargo_focus": "Design Focus: Cargo",
        "luxury_focus": "Design Focus: Luxury",
        "style_focus": "Design Focus: Style",
        "material_quality": "Materials: Material Quality",
        "testing_reliability": "Testing: Reliability",
        "testing_fuel": "Testing: Fuel Economy",
        "testing_performance": "Testing: Performance",
        "testing_utility": "Testing: Utility",
    },
}


def get_vehicle_type_weight(vehicle_type: VehicleType, rating_name: str) -> float:
    """Return importance weight for a rating; quality uses a background default."""
    if rating_name == "quality":
        return QUALITY_BACKGROUND_WEIGHT
    return float(getattr(vehicle_type, rating_name))


def get_adjusted_vehicle_weights(vehicle_type: VehicleType) -> dict[str, float]:
    """
    Apply fleet boosts to vehicle type weights and clamp to [0, 1].

    Military fleet boosts power, cargo, dependability, and safety.
    Civilian fleet boosts fuel, dependability, and cargo.
    """
    weights = {
        name: get_vehicle_type_weight(vehicle_type, name)
        for name in RATING_NAMES
        if name != "quality"
    }

    if vehicle_type.military_fleet:
        weights["power"] += 0.10
        weights["cargo"] += 0.10
        weights["dependability"] += 0.10
        weights["safety"] += 0.05

    if vehicle_type.civilian_fleet:
        weights["fuel"] += 0.05
        weights["dependability"] += 0.05
        weights["cargo"] += 0.05

    for name in weights:
        weights[name] = max(0.0, min(1.0, weights[name]))

    weights["quality"] = QUALITY_BACKGROUND_WEIGHT
    return weights


def _build_reasons(
    vehicle_type: VehicleType,
    influences: dict[str, float],
    adjusted_weights: dict[str, float],
) -> list[str]:
    """Build reason strings from the top contributing vehicle ratings."""
    contributions = [
        (rating, adjusted_weights[rating] * influence)
        for rating, influence in influences.items()
    ]
    contributions.sort(key=lambda item: item[1], reverse=True)
    top = contributions[:2]
    parts = [f"{rating}={adjusted_weights[rating]:.2f}" for rating, _ in top]
    return [f"Because {vehicle_type.name} values {', '.join(parts)}"]


def _priorities_for_component(
    component: str,
    influence_matrix: dict[str, dict[str, float]],
    vehicle_type: VehicleType,
    adjusted_weights: dict[str, float],
) -> list[ComponentPriority]:
    """Calculate normalized priorities for one component category."""
    raw_scores: dict[str, float] = {}

    for stat, influences in influence_matrix.items():
        raw_scores[stat] = sum(
            adjusted_weights[rating] * influence
            for rating, influence in influences.items()
        )

    max_raw = max(raw_scores.values()) if raw_scores else 0.0

    priorities: list[ComponentPriority] = []
    for stat, raw in raw_scores.items():
        normalized = 100 * raw / max_raw if max_raw > 0 else 0.0
        priorities.append(
            ComponentPriority(
                component=component,
                stat=stat,
                priority=normalized,
                reasons=_build_reasons(
                    vehicle_type, influence_matrix[stat], adjusted_weights
                ),
            )
        )

    priorities.sort(key=lambda item: item.priority, reverse=True)
    return priorities


def calculate_component_priorities(
    vehicle_type: VehicleType,
) -> dict[str, list[ComponentPriority]]:
    """
    Derive chassis, engine, gearbox, and vehicle design stat priorities.

    Uses an influence matrix mapping vehicle type importance weights to
    component-specific focus areas.
    """
    adjusted_weights = get_adjusted_vehicle_weights(vehicle_type)

    return {
        component: _priorities_for_component(
            component, influence_matrix, vehicle_type, adjusted_weights
        )
        for component, influence_matrix in COMPONENT_INFLUENCE.items()
    }


def format_stat_label(component: str, stat: str) -> str:
    """Return a human-readable label for a component stat key."""
    return format_priority_label(component, stat)


def enrich_engine_priorities_for_display(
    priorities: list[ComponentPriority],
) -> list[ComponentPriority]:
    """
    Add a display-only engine Power Rating row derived from horsepower/torque.

    Does not affect priority calculations or formula scoring.
    """
    horsepower = next((item for item in priorities if item.stat == "horsepower"), None)
    torque = next((item for item in priorities if item.stat == "torque"), None)
    if horsepower is None and torque is None:
        return priorities

    pseudo_priority = max(
        horsepower.priority if horsepower else 0.0,
        torque.priority if torque else 0.0,
    )
    enriched = list(priorities)
    enriched.append(
        ComponentPriority(
            component="engine",
            stat="power_rating",
            priority=pseudo_priority,
            reasons=[
                "Display-only: max(horsepower, torque) priority; "
                "Power Rating is a separate GearCity rating."
            ],
        )
    )
    enriched.sort(key=lambda item: item.priority, reverse=True)
    return enriched


def enrich_priorities_for_display(
    component: str,
    priorities: list[ComponentPriority],
) -> list[ComponentPriority]:
    """Apply display-only enrichments without changing calculated priorities."""
    if component == "engine":
        return enrich_engine_priorities_for_display(priorities)
    return priorities
