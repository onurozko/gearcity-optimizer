"""Global design objective scoring for complete vehicle designs."""

from __future__ import annotations

from dataclasses import dataclass, field

from gearcity_optimizer.core.component_priorities import get_adjusted_vehicle_weights
from gearcity_optimizer.core.component_vehicle_groups import PASSENGER_GROUPS, classify_vehicle_group
from gearcity_optimizer.core.wiki_component_compatibility import validate_component_choices
from gearcity_optimizer.core.cost_mode import CostMode, parse_cost_mode
from gearcity_optimizer.core.models import VehicleType
from gearcity_optimizer.importers.component_choices import ComponentChoice
from gearcity_optimizer.reports.component_choice_recommender import (
    ComponentSuitabilityScore,
    score_component_suitability,
)
from gearcity_optimizer.reports.design_physical_constraints import (
    PhysicalFitAssessment,
    assess_physical_fit,
)
from gearcity_optimizer.reports.slider_optimizer import ControlSetting, PredictedOutput

try:
    from gearcity_optimizer.formulas.chassis_formula import ChassisFormulaResult
    from gearcity_optimizer.formulas.engine_formula import EngineFormulaResult
    from gearcity_optimizer.formulas.gearbox_formula import GearboxFormulaResult
except ImportError:  # pragma: no cover
    ChassisFormulaResult = None  # type: ignore[misc, assignment]
    EngineFormulaResult = None  # type: ignore[misc, assignment]
    GearboxFormulaResult = None  # type: ignore[misc, assignment]

PRIORITY_OUTPUT_ALIASES: dict[str, tuple[str, ...]] = {
    "performance": ("vehicle_performance", "performance", "engine_overall", "overall"),
    "drivability": ("drivability", "vehicle_drivability", "chassis_comfort"),
    "luxury": ("luxury", "smoothness", "chassis_comfort"),
    "safety": ("safety", "chassis_strength"),
    "fuel": ("fuel", "fuel_economy"),
    "power": ("vehicle_performance", "power"),
    "cargo": ("cargo",),
    "dependability": ("vehicle_dependability", "dependability", "reliability"),
    "quality": ("vehicle_quality", "quality", "reliability", "vehicle_dependability"),
    "overall": ("vehicle_overall", "overall", "engine_overall"),
}

COST_MODE_PENALTY_SCALE: dict[CostMode, float] = {
    CostMode.CHEAP: 1.35,
    CostMode.BALANCED: 1.0,
    CostMode.LUXURY: 0.55,
}

STAT_DISPLAY_LABELS: dict[str, str] = {
    "performance": "Performance",
    "drivability": "Driveability",
    "luxury": "Luxury",
    "safety": "Safety",
    "fuel": "Fuel",
    "power": "Power",
    "cargo": "Cargo",
    "dependability": "Dependability",
    "quality": "Quality",
    "overall": "Overall",
}


@dataclass(frozen=True)
class DesignObjective:
    """Targets and weights for scoring a complete vehicle design."""

    vehicle_type_name: str
    cost_mode: str
    stat_weights: dict[str, float]
    minimum_targets: dict[str, float]
    penalties: dict[str, float]
    notes: list[str]


@dataclass(frozen=True)
class DesignScore:
    """Global score for one complete design candidate."""

    total_score: float
    weighted_stat_score: float
    cost_penalty: float
    complexity_penalty: float
    mismatch_penalty: float
    low_priority_stat_penalty: float
    component_confidence_penalty: float
    failed_thresholds: list[str]
    warnings: list[str]
    quality_status: str
    stat_statuses: dict[str, str] = field(default_factory=dict)
    stat_targets: dict[str, float] = field(default_factory=dict)
    stat_values: dict[str, float] = field(default_factory=dict)
    physical_fit: PhysicalFitAssessment | None = None


@dataclass(frozen=True)
class DesignObjectiveEvaluation:
    """Legacy evaluation wrapper kept for existing callers."""

    weighted_output_score: float
    objective_score: float
    warnings: tuple[str, ...]
    poor_priority_stats: tuple[str, ...]


def _priority_tier(weight: float) -> tuple[float, float, float, float]:
    """Return desired target, warning threshold, severe threshold, failed threshold."""
    if weight >= 0.70:
        return 70.0, 50.0, 35.0, 25.0
    if weight >= 0.50:
        return 60.0, 45.0, 30.0, 20.0
    if weight >= 0.30:
        return 45.0, 30.0, 22.0, 15.0
    return 35.0, 20.0, 15.0, 10.0


def build_design_objective(vehicle_type: VehicleType, cost_mode: str) -> DesignObjective:
    """Build global objective targets from vehicle type priorities and cost mode."""
    parsed_cost = parse_cost_mode(cost_mode)
    weights = get_adjusted_vehicle_weights(vehicle_type)
    stat_weights = dict(weights)
    stat_weights["overall"] = max(
        weights.get("performance", 0.0),
        weights.get("dependability", 0.0),
        0.40,
    )
    minimum_targets: dict[str, float] = {}
    for stat, importance in stat_weights.items():
        if importance < 0.05:
            continue
        desired, _, _, _ = _priority_tier(importance)
        minimum_targets[stat] = desired

    notes = [
        f"{vehicle_type.name} design objective uses final vehicle priority weights.",
        "The optimizer maximizes weighted predicted final outputs, not individual sliders.",
        "Low-priority stats may be sacrificed when they conflict with high-priority goals or cost mode.",
    ]
    if parsed_cost is CostMode.CHEAP:
        notes.append(
            "Cheap mode penalizes cost, complexity, and overspending while still requiring "
            "important vehicle-type stats to stay usable."
        )
    elif parsed_cost is CostMode.LUXURY:
        notes.append(
            "Luxury mode allows higher material quality and comfort spending with lower cost penalties."
        )
    else:
        notes.append(
            "Balanced mode seeks broad good results for important stats without extreme overspending."
        )

    return DesignObjective(
        vehicle_type_name=vehicle_type.name,
        cost_mode=cost_mode,
        stat_weights=stat_weights,
        minimum_targets=minimum_targets,
        penalties={
            "cost_scale": COST_MODE_PENALTY_SCALE[parsed_cost],
            "complexity_scale": 0.8 if parsed_cost is CostMode.LUXURY else 1.0,
        },
        notes=notes,
    )


def build_priority_explanation(vehicle_type: VehicleType, objective: DesignObjective) -> list[str]:
    """Explain why vehicle-type priorities matter for this optimization run."""
    weights = objective.stat_weights
    ranked = sorted(
        ((stat, weight) for stat, weight in weights.items() if stat not in {"quality", "overall"}),
        key=lambda item: item[1],
        reverse=True,
    )
    top_stats = ", ".join(
        f"{STAT_DISPLAY_LABELS.get(stat, stat)} ({weight:.2f})"
        for stat, weight in ranked[:4]
    )
    return objective.notes + [
        f"{vehicle_type.name} values {top_stats} most strongly for this setup.",
        "Component choices and slider settings are compared by their complete predicted vehicle outputs.",
    ]


def _match_predicted(outputs: list[PredictedOutput], aliases: tuple[str, ...]) -> PredictedOutput | None:
    by_key = {output.output_key.lower(): output for output in outputs}
    for alias in aliases:
        match = by_key.get(alias.lower())
        if match is not None:
            return match
    alias_set = {alias.lower() for alias in aliases}
    for output in outputs:
        label_key = output.label.lower().replace(" ", "_").replace("(", "").replace(")", "")
        if label_key in alias_set:
            return output
    return None


def _stat_status(value: float, importance: float) -> str:
    desired, warn, severe, failed = _priority_tier(importance)
    if value < failed:
        return "failed"
    if value < severe:
        return "weak"
    if value < warn:
        return "okay"
    if value >= desired:
        return "good"
    return "okay"


def _component_confidence_penalty(
    component_choices: dict[str, ComponentChoice] | None,
    *,
    vehicle_type: VehicleType,
    cost_mode: CostMode,
    year: int,
    available_by_type: dict[str, list[ComponentChoice]] | None,
) -> tuple[float, float]:
    if not component_choices or not available_by_type:
        return 0.0, 0.0

    scores: list[float] = []
    confidence_hits = 0
    for choice_type, choice in component_choices.items():
        candidates = available_by_type.get(choice_type, [choice])
        suitability = score_component_suitability(
            choice,
            vehicle_type=vehicle_type,
            cost_mode=cost_mode,
            year=year,
            candidates=candidates,
        )
        scores.append(suitability.total_score)
        if suitability.confidence == "low" or suitability.penalties:
            confidence_hits += 1

    avg = sum(scores) / len(scores) if scores else 100.0
    penalty = max(0.0, (65.0 - avg) * 0.08) + confidence_hits * 0.35
    return penalty, avg


def _cost_and_complexity_penalties(
    predicted_outputs: list[PredictedOutput],
    slider_settings: list[ControlSetting] | None,
    *,
    cost_scale: float,
    complexity_scale: float,
) -> tuple[float, float]:
    cost_penalty = 0.0
    complexity_penalty = 0.0

    design_req = _match_predicted(predicted_outputs, ("design_requirements",))
    manufacturing = _match_predicted(predicted_outputs, ("manufacturing_requirements",))
    if design_req is not None:
        cost_penalty += max(0.0, design_req.value - 45.0) * 0.03 * cost_scale
    if manufacturing is not None:
        cost_penalty += max(0.0, manufacturing.value - 40.0) * 0.04 * cost_scale

    if slider_settings:
        expensive_keys = {
            "tech_materials",
            "tech_material",
            "tech_technology",
            "tech_components",
            "tech_techniques",
            "design_pace",
            "development_pace",
        }
        for setting in slider_settings:
            if setting.slider_key.split(".")[-1] in expensive_keys:
                normalized = setting.value / 100.0 if setting.value > 1.0 else setting.value
                complexity_penalty += normalized * 0.35
        complexity_penalty *= complexity_scale * 0.15

    return cost_penalty, complexity_penalty


def score_complete_design(
    predicted_outputs: list[PredictedOutput],
    component_choices: dict[str, ComponentChoice] | None,
    slider_settings: list[ControlSetting] | None,
    objective: DesignObjective,
    *,
    vehicle_type: VehicleType | None = None,
    year: int = 1900,
    available_by_type: dict[str, list[ComponentChoice]] | None = None,
    engine_result: EngineFormulaResult | None = None,
    chassis_result: ChassisFormulaResult | None = None,
    gearbox_result: GearboxFormulaResult | None = None,
) -> DesignScore:
    """Score one complete design against vehicle type priorities and cost mode."""
    cost_mode = parse_cost_mode(objective.cost_mode)
    weights = objective.stat_weights
    warnings: list[str] = []
    failed_thresholds: list[str] = []
    stat_statuses: dict[str, str] = {}
    stat_targets: dict[str, float] = {}
    stat_values: dict[str, float] = {}

    weighted_sum = 0.0
    weight_total = 0.0
    low_priority_penalty = 0.0
    mismatch_penalty = 0.0

    for stat, importance in weights.items():
        if importance < 0.05:
            continue
        aliases = PRIORITY_OUTPUT_ALIASES.get(stat, (stat,))
        predicted = _match_predicted(predicted_outputs, aliases)
        if predicted is None:
            continue

        value = predicted.value
        stat_values[stat] = value
        desired, warn, severe, failed = _priority_tier(importance)
        stat_targets[stat] = desired
        normalized = min(max(value / 100.0, 0.0), 1.0)
        weighted_sum += importance * normalized
        weight_total += importance
        status = _stat_status(value, importance)
        stat_statuses[STAT_DISPLAY_LABELS.get(stat, stat)] = status

        label = STAT_DISPLAY_LABELS.get(stat, predicted.label)
        if value < warn and importance >= 0.30:
            warnings.append(
                f"Warning: {label} is important for {objective.vehicle_type_name} "
                f"(weight {importance:.2f}), but predicted {label} is low ({value:.1f}). "
                f"Target is {desired:.0f}+."
            )
        if value < severe and importance >= 0.50:
            failed_thresholds.append(label)
            low_priority_penalty += importance * (severe - value) * 0.06
        if value < failed and importance >= 0.50:
            low_priority_penalty += importance * 1.5
            failed_thresholds.append(f"{label} (failed threshold)")

    overall = _match_predicted(predicted_outputs, ("overall",))
    overall_value = overall.value if overall is not None else 0.0
    if overall is not None:
        stat_values["overall"] = overall_value
        stat_targets["overall"] = 55.0
        if overall_value < 40.0:
            warnings.append(
                f"Warning: predicted Overall is poor ({overall_value:.1f}) for "
                f"{objective.vehicle_type_name}."
            )
            low_priority_penalty += 2.0
        if overall_value < 30.0:
            failed_thresholds.append("Overall")
            low_priority_penalty += 3.5

    if vehicle_type is not None:
        group = classify_vehicle_group(vehicle_type)
        if group in PASSENGER_GROUPS:
            reliability = _match_predicted(
                predicted_outputs,
                ("reliability", "dependability", "vehicle_dependability"),
            )
            if reliability is not None and reliability.value < 35.0:
                warnings.append(
                    f"Warning: predicted {reliability.label} is very low for a passenger vehicle "
                    f"({reliability.value:.1f})."
                )
                mismatch_penalty += 1.2
                if weights.get("dependability", 0.0) >= 0.45:
                    failed_thresholds.append("Dependability")

    component_penalty, _ = _component_confidence_penalty(
        component_choices,
        vehicle_type=vehicle_type or VehicleType(
            name=objective.vehicle_type_name,
            performance=0.4,
            drivability=0.4,
            luxury=0.4,
            safety=0.4,
            fuel=0.4,
            power=0.4,
            cargo=0.4,
            dependability=0.4,
            wealth_demo=4,
        ),
        cost_mode=cost_mode,
        year=year,
        available_by_type=available_by_type,
    )

    if component_choices:
        compat = validate_component_choices(component_choices)
        if compat.violations:
            mismatch_penalty += len(compat.violations) * 2.5
            warnings.extend(compat.violations)

    physical_fit = assess_physical_fit(
        engine=engine_result,
        chassis=chassis_result,
        gearbox=gearbox_result,
        predicted_outputs=predicted_outputs,
    )
    if physical_fit.penalty > 0:
        mismatch_penalty += physical_fit.penalty
    warnings.extend(physical_fit.warnings)
    if not physical_fit.torque_ok and physical_fit.engine_torque_lbft is not None:
        failed_thresholds.append("Gearbox torque support")
    if physical_fit.violations:
        for violation in physical_fit.violations:
            if "Gearbox max torque" in violation:
                stat_statuses["Torque fit"] = "failed"
            if "Engine length" in violation:
                failed_thresholds.append("Engine bay (length)")
                stat_statuses["Engine bay fit"] = "failed"
            if "Engine width" in violation:
                failed_thresholds.append("Engine bay (width)")
                stat_statuses["Engine bay fit"] = "failed"

    cost_penalty, complexity_penalty = _cost_and_complexity_penalties(
        predicted_outputs,
        slider_settings,
        cost_scale=objective.penalties.get("cost_scale", 1.0),
        complexity_scale=objective.penalties.get("complexity_scale", 1.0),
    )

    weighted_stat_score = (weighted_sum / weight_total * 100.0) if weight_total else 0.0
    total_penalty = (
        cost_penalty
        + complexity_penalty
        + mismatch_penalty
        + low_priority_penalty
        + component_penalty
    )
    total_score = max(0.0, weighted_stat_score - total_penalty)
    if physical_fit.has_violations:
        total_score = min(total_score, 30.0)

    quality_status = _quality_status(
        total_score=total_score,
        failed_thresholds=failed_thresholds,
        stat_statuses=stat_statuses,
        overall_value=overall_value,
        physical_violations=physical_fit.has_violations,
    )

    if quality_status in {"Poor", "Failed"}:
        warnings.append(
            f"Design quality is {quality_status}. The complete predicted vehicle outputs do not "
            f"meet {objective.vehicle_type_name} priorities for {objective.cost_mode} mode."
        )

    return DesignScore(
        total_score=round(total_score, 2),
        weighted_stat_score=round(weighted_stat_score, 2),
        cost_penalty=round(cost_penalty, 2),
        complexity_penalty=round(complexity_penalty, 2),
        mismatch_penalty=round(mismatch_penalty, 2),
        low_priority_stat_penalty=round(low_priority_penalty, 2),
        component_confidence_penalty=round(component_penalty, 2),
        failed_thresholds=list(dict.fromkeys(failed_thresholds)),
        warnings=list(dict.fromkeys(warnings)),
        quality_status=quality_status,
        stat_statuses=stat_statuses,
        stat_targets=stat_targets,
        stat_values=stat_values,
        physical_fit=physical_fit,
    )


def design_score_for_optimization(score: DesignScore) -> float:
    """Hill-climb score that prefers physically feasible designs over raw stat totals."""
    physical_fit = score.physical_fit
    if physical_fit is not None and physical_fit.has_violations:
        margins: list[float] = []
        if physical_fit.torque_ok is False and physical_fit.torque_margin_ratio is not None:
            margins.append(physical_fit.torque_margin_ratio)
        if physical_fit.length_margin_ratio is not None and physical_fit.length_margin_ratio < 1.0:
            margins.append(physical_fit.length_margin_ratio)
        if physical_fit.width_margin_ratio is not None and physical_fit.width_margin_ratio < 1.0:
            margins.append(physical_fit.width_margin_ratio)
        if margins:
            return min(margins) * 40.0
        return 0.0
    return score.total_score


def _quality_status(
    *,
    total_score: float,
    failed_thresholds: list[str],
    stat_statuses: dict[str, str],
    overall_value: float,
    physical_violations: bool = False,
) -> str:
    failed_stats = [name for name, status in stat_statuses.items() if status == "failed"]
    weak_high_priority = sum(1 for status in stat_statuses.values() if status == "weak")

    if physical_violations:
        return "Failed"
    if failed_stats or len(failed_thresholds) >= 2 or overall_value < 30.0:
        return "Failed"
    if weak_high_priority >= 2 or total_score < 35.0 or overall_value < 40.0:
        return "Poor"
    if total_score < 55.0 or failed_thresholds:
        return "Usable"
    return "Good"


def design_score_to_legacy(score: DesignScore) -> DesignObjectiveEvaluation:
    """Convert a global design score to the legacy evaluation type."""
    poor_stats = [
        name
        for name, status in score.stat_statuses.items()
        if status in {"weak", "failed"}
    ]
    return DesignObjectiveEvaluation(
        weighted_output_score=round(score.weighted_stat_score / 100.0, 4),
        objective_score=score.total_score,
        warnings=tuple(score.warnings),
        poor_priority_stats=tuple(poor_stats),
    )


def evaluate_design_objective(
    vehicle_type: VehicleType,
    predicted_outputs: list[PredictedOutput],
    *,
    cost_mode: str = "balanced",
    component_choices: dict[str, ComponentChoice] | None = None,
    slider_settings: list[ControlSetting] | None = None,
) -> DesignObjectiveEvaluation:
    """Score predicted outputs against vehicle type priorities (legacy entry point)."""
    objective = build_design_objective(vehicle_type, cost_mode)
    score = score_complete_design(
        predicted_outputs,
        component_choices,
        slider_settings,
        objective,
        vehicle_type=vehicle_type,
    )
    return design_score_to_legacy(score)
