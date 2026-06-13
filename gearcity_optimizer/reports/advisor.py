"""Rule-based explanation layer for candidate scores."""

from __future__ import annotations

from gearcity_optimizer.core.component_models import ComponentPackageResult, ComponentPriority
from gearcity_optimizer.core.component_priorities import format_stat_label
from gearcity_optimizer.core.models import (
    RATING_ATTRIBUTES,
    CandidateDesign,
    ScoreResult,
    VehicleType,
)

ATTRIBUTE_LABELS = {
    "performance": "Performance",
    "drivability": "Driveability",
    "luxury": "Luxury",
    "safety": "Safety",
    "fuel": "Fuel economy",
    "power": "Power",
    "cargo": "Cargo",
    "dependability": "Dependability",
}

HIGH_IMPORTANCE_THRESHOLD = 0.6
LOW_IMPORTANCE_THRESHOLD = 0.2
OVERBUILT_RATING_THRESHOLD = 70


def explain_candidate(
    candidate: CandidateDesign,
    vehicle_type: VehicleType,
    score_result: ScoreResult,
) -> list[str]:
    """
    Generate human-readable comments about a candidate's fit and trade-offs.

    Rule-based only; no LLM involvement.
    """
    comments: list[str] = []

    if score_result.vehicle_type_fit >= 75:
        comments.append("This design fits the vehicle type well.")
    elif score_result.vehicle_type_fit < 50:
        comments.append("This design is poorly matched to the vehicle type.")

    for attr in RATING_ATTRIBUTES:
        importance = getattr(vehicle_type, attr)
        rating = getattr(candidate, attr)
        label = ATTRIBUTE_LABELS[attr]

        if importance >= HIGH_IMPORTANCE_THRESHOLD and rating < 40:
            comments.append(
                f"{label} is important for this vehicle type, "
                f"but this design has low {label.lower()}."
            )

        if importance <= LOW_IMPORTANCE_THRESHOLD and rating >= OVERBUILT_RATING_THRESHOLD:
            comments.append(
                f"{label} is overbuilt for a vehicle type "
                f"that does not value {label.lower()} much."
            )

    if score_result.penalty_multiplier < 0.9:
        comments.append("Penalties are materially hurting this design.")

    if (
        score_result.value_per_cost >= 2.5
        and score_result.penalty_multiplier >= 0.9
        and score_result.vehicle_type_fit >= 50
    ):
        comments.append(
            "This design has good buyer-rating value for its unit cost."
        )

    comments.extend(score_result.warnings)

    return comments


def explain_component_priorities(
    vehicle_type: VehicleType,
    priorities: dict[str, list[ComponentPriority]],
) -> list[str]:
    """Generate plain-English guidance on what component stats to prioritize."""
    comments: list[str] = []
    name = vehicle_type.name

    high_ratings = [
        ATTRIBUTE_LABELS[attr]
        for attr in RATING_ATTRIBUTES
        if getattr(vehicle_type, attr) >= HIGH_IMPORTANCE_THRESHOLD
    ]
    if high_ratings:
        joined = ", ".join(high_ratings[:3]).lower()
        comments.append(
            f"{name} values {joined} heavily, so match chassis, engine, "
            f"gearbox, and vehicle design choices to those priorities."
        )

    if vehicle_type.fuel >= HIGH_IMPORTANCE_THRESHOLD:
        comments.append(
            f"{name} values safety and fuel heavily, so prioritize chassis "
            f"strength, engine fuel economy, gearbox reliability, and vehicle "
            f"safety/fuel testing."
        )

    if vehicle_type.cargo >= 0.75 and vehicle_type.power >= 0.75:
        comments.append(
            f"{name} values cargo, power, and dependability, so prioritize "
            f"chassis strength/durability, engine torque, and gearbox max "
            f"torque/reliability."
        )

    if vehicle_type.drivability >= 0.75 and vehicle_type.performance >= 0.75:
        comments.append(
            f"{name} values drivability and performance, so prioritize chassis "
            f"performance, low weight, engine horsepower, and gearbox performance."
        )

    if vehicle_type.luxury >= 0.75:
        comments.append(
            f"{name} values luxury, so prioritize chassis comfort, engine "
            f"smoothness, gearbox comfort/reliability, and luxury-focused "
            f"vehicle design sliders."
        )

    for component in ("chassis", "engine", "gearbox", "vehicle_design"):
        top_stats = priorities.get(component, [])[:3]
        if top_stats:
            labels = [
                format_stat_label(component, item.stat) for item in top_stats
            ]
            comments.append(
                f"Top {component.replace('_', ' ')} focus: {', '.join(labels)}."
            )

    return comments


def explain_package(
    package_result: ComponentPackageResult,
    vehicle_type: VehicleType,
) -> list[str]:
    """Explain why a component package fits a vehicle type."""
    comments: list[str] = []
    uses_assembly = package_result.final_formula_fit_score is not None

    if uses_assembly:
        comments.append(
            f"Assembly-first formula score {package_result.final_formula_fit_score:.1f} "
            f"(vehicle type fit {package_result.assembly_vehicle_type_fit:.1f}, "
            f"component package score {package_result.component_package_score:.1f})."
        )
        assembly = (
            package_result.fit_debug.get("assembly_ratings")
            if package_result.fit_debug
            else None
        )
        if assembly:
            for attr in RATING_ATTRIBUTES:
                importance = getattr(vehicle_type, attr)
                rating = assembly.get(attr)
                if rating is None:
                    continue
                label = ATTRIBUTE_LABELS[attr]
                if importance >= HIGH_IMPORTANCE_THRESHOLD and rating < 35:
                    comments.append(
                        f"Assembly fit is weak on {label.lower()} for {vehicle_type.name}."
                    )
                elif importance >= HIGH_IMPORTANCE_THRESHOLD and rating >= 50:
                    comments.append(
                        f"Assembly {label.lower()} is strong for {vehicle_type.name}."
                    )

            high_importance = [
                ATTRIBUTE_LABELS[attr]
                for attr in RATING_ATTRIBUTES
                if getattr(vehicle_type, attr) >= HIGH_IMPORTANCE_THRESHOLD
            ]
            strong_attrs = [
                ATTRIBUTE_LABELS[attr]
                for attr in RATING_ATTRIBUTES
                if assembly.get(attr, 0) >= 50
            ]
            weak_attrs = [
                ATTRIBUTE_LABELS[attr]
                for attr in RATING_ATTRIBUTES
                if getattr(vehicle_type, attr) >= HIGH_IMPORTANCE_THRESHOLD
                and assembly.get(attr, 0) < 35
            ]
            if strong_attrs and weak_attrs and high_importance:
                comments.append(
                    f"{', '.join(strong_attrs[:2]).lower()} is strong, but "
                    f"{vehicle_type.name} values {', '.join(high_importance[:2]).lower()} "
                    f"more; watch {', '.join(weak_attrs[:2]).lower()}."
                )
    else:
        comments.append(
            f"Package score {package_result.package_score:.1f} with total unit "
            f"cost {package_result.total_unit_cost:.0f}."
        )

        if package_result.chassis_fit >= 40:
            comments.append(
                f"{package_result.chassis_name} fits well "
                f"(chassis fit {package_result.chassis_fit:.1f})."
            )
            if package_result.chassis_reasons:
                comments.extend(package_result.chassis_reasons[:2])

        if package_result.engine_fit >= 40:
            comments.append(
                f"{package_result.engine_name} fits well "
                f"(engine fit {package_result.engine_fit:.1f})."
            )
            if package_result.engine_reasons:
                comments.extend(package_result.engine_reasons[:2])

        if package_result.gearbox_fit >= 40:
            comments.append(
                f"{package_result.gearbox_name} fits well "
                f"(gearbox fit {package_result.gearbox_fit:.1f})."
            )
            if package_result.gearbox_reasons:
                comments.extend(package_result.gearbox_reasons[:2])

    comments.extend(package_result.warnings)

    if (
        package_result.package_value_score > 0
        and package_result.total_unit_cost < 1200
        and not uses_assembly
    ):
        comments.append("This package offers strong value for its component cost.")

    return comments
