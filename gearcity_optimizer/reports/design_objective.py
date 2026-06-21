"""Design objective scoring from predicted outputs and vehicle priorities."""

from __future__ import annotations

from dataclasses import dataclass

from gearcity_optimizer.core.component_priorities import get_adjusted_vehicle_weights
from gearcity_optimizer.core.component_vehicle_groups import PASSENGER_GROUPS, classify_vehicle_group
from gearcity_optimizer.core.models import VehicleType
from gearcity_optimizer.reports.slider_optimizer import PredictedOutput

PRIORITY_OUTPUT_ALIASES: dict[str, tuple[str, ...]] = {
    "performance": ("performance", "vehicle_performance", "overall"),
    "drivability": ("drivability", "vehicle_drivability", "chassis_comfort"),
    "luxury": ("luxury", "smoothness", "chassis_comfort"),
    "safety": ("safety", "chassis_strength"),
    "fuel": ("fuel", "fuel_economy"),
    "power": ("power", "torque", "gearbox_torque_support"),
    "cargo": ("cargo",),
    "dependability": ("dependability", "vehicle_dependability", "reliability"),
}

HIGH_PRIORITY_THRESHOLD = 0.45
LOW_OUTPUT_THRESHOLD = 40.0
VERY_LOW_OUTPUT_THRESHOLD = 25.0


@dataclass(frozen=True)
class DesignObjectiveEvaluation:
    """Weighted objective score and warnings for a design result."""

    weighted_output_score: float
    objective_score: float
    warnings: tuple[str, ...]
    poor_priority_stats: tuple[str, ...]


def _match_predicted(outputs: list[PredictedOutput], aliases: tuple[str, ...]) -> PredictedOutput | None:
    alias_set = {alias.lower() for alias in aliases}
    for output in outputs:
        if output.output_key.lower() in alias_set:
            return output
        if output.label.lower().replace(" ", "_") in alias_set:
            return output
    return None


def evaluate_design_objective(
    vehicle_type: VehicleType,
    predicted_outputs: list[PredictedOutput],
) -> DesignObjectiveEvaluation:
    """Score predicted outputs against vehicle type priorities."""
    weights = get_adjusted_vehicle_weights(vehicle_type)
    warnings: list[str] = []
    poor_stats: list[str] = []
    weighted_sum = 0.0
    weight_total = 0.0
    penalty = 0.0

    for stat, importance in weights.items():
        if importance < 0.05:
            continue
        predicted = _match_predicted(predicted_outputs, PRIORITY_OUTPUT_ALIASES.get(stat, (stat,)))
        if predicted is None:
            continue
        normalized = min(max(predicted.value / 100.0, 0.0), 1.0)
        weighted_sum += importance * normalized
        weight_total += importance

        if importance >= HIGH_PRIORITY_THRESHOLD and predicted.value < LOW_OUTPUT_THRESHOLD:
            label = predicted.label
            poor_stats.append(label)
            warnings.append(
                f"Warning: {_format_stat_label(stat)} is important for {vehicle_type.name}, "
                f"but predicted {label} is low ({predicted.value:.1f}). "
                "Current component/slider setup may be unsuitable."
            )
            penalty += importance * (LOW_OUTPUT_THRESHOLD - predicted.value) * 0.02
            if predicted.value < VERY_LOW_OUTPUT_THRESHOLD:
                penalty += importance * 0.25

    overall = _match_predicted(predicted_outputs, ("overall",))
    if overall is not None and overall.value < 35.0:
        warnings.append(
            f"Warning: predicted Overall is very low ({overall.value:.1f}) for {vehicle_type.name}."
        )
        penalty += 0.35

    group = classify_vehicle_group(vehicle_type)
    if group in PASSENGER_GROUPS:
        reliability = _match_predicted(
            predicted_outputs,
            ("reliability", "dependability", "vehicle_dependability"),
        )
        if reliability is not None and reliability.value < 35.0:
            warnings.append(
                f"Warning: predicted {reliability.label} is low for a passenger vehicle "
                f"({reliability.value:.1f})."
            )
            penalty += 0.2

    weighted_output_score = weighted_sum / weight_total if weight_total else 0.0
    objective_score = max(0.0, (weighted_output_score * 100.0) - penalty)
    return DesignObjectiveEvaluation(
        weighted_output_score=round(weighted_output_score, 4),
        objective_score=round(objective_score, 2),
        warnings=tuple(dict.fromkeys(warnings)),
        poor_priority_stats=tuple(poor_stats),
    )


def _format_stat_label(stat: str) -> str:
    labels = {
        "performance": "Performance",
        "drivability": "Driveability",
        "luxury": "Luxury",
        "safety": "Safety",
        "fuel": "Fuel economy",
        "power": "Power",
        "cargo": "Cargo",
        "dependability": "Dependability",
    }
    return labels.get(stat, stat.replace("_", " ").title())
