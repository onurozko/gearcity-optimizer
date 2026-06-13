"""Score and rank chassis, engine, and gearbox combinations for vehicle types."""

from __future__ import annotations

from gearcity_optimizer.core.component_models import (
    ChassisCandidate,
    ComponentFitResult,
    ComponentPackageResult,
    EngineCandidate,
    GearboxCandidate,
)
from gearcity_optimizer.core.component_priorities import (
    CHASSIS_INFLUENCE,
    ENGINE_INFLUENCE,
    GEARBOX_INFLUENCE,
    calculate_component_priorities,
    get_adjusted_vehicle_weights,
)
from gearcity_optimizer.core.models import VehicleType
from gearcity_optimizer.formulas.vehicle_assembly_formula import (
    ComponentAssemblyInput,
    assemble_and_score_package,
    calculate_final_formula_fit_score,
    scale_horsepower_to_rating,
    scale_max_torque_to_rating,
    scale_torque_to_rating,
)

PACKAGE_OBJECTIVES = (
    "best_fit",
    "value",
    "balanced",
    "component_fit",
    "formula_fit",
    "formula_value",
    "formula_balanced",
)

COMPONENT_FORMULA_OBJECTIVES = frozenset(
    {"component_fit", "formula_fit", "formula_value", "formula_balanced"}
)
ASSEMBLY_FORMULA_OBJECTIVES = frozenset(
    {"formula_fit", "formula_value", "formula_balanced"}
)

HORSEPOWER_CAP = 80.0
TORQUE_CAP = 150.0
MAX_TORQUE_CAP = 150.0

OVERALL_BACKGROUND_WEIGHT = 0.20
PRIORITY_WEIGHT = 0.80

FORMULA_FIT_OVERALL_SHARE = 0.25
FORMULA_FIT_STAT_SHARE = 0.70
FORMULA_FIT_AUXILIARY_SHARE = 0.05

AUXILIARY_STAT_WEIGHT = 0.35


def _normalize_column(values: list[float]) -> list[float]:
    """Normalize values to 0–1; equal values all receive 1.0."""
    if not values:
        return []
    min_val = min(values)
    max_val = max(values)
    if min_val == max_val:
        return [1.0] * len(values)
    span = max_val - min_val
    return [(v - min_val) / span for v in values]


def _low_weight_score(weight: float) -> float:
    """Lower chassis/engine/gearbox weight is better."""
    return max(0.0, min(100.0, 100.0 - weight / 10.0))


def _engine_fit_room_score(width: float, length: float) -> float:
    """Larger engine bay is better for fit room priority."""
    return min(100.0, (width + length) * 2.0)


def _compact_size_score(width: float, length: float) -> float:
    """Smaller engine footprint is better."""
    return max(0.0, min(100.0, 100.0 - (width + length) / 2.0))


def _horsepower_score(horsepower: float) -> float:
    """Normalize raw horsepower to a 0–100 score (legacy proxy mode)."""
    return min(100.0, horsepower / HORSEPOWER_CAP * 100.0)


def _torque_score(torque: float) -> float:
    """Normalize raw torque to a 0–100 score (legacy proxy mode)."""
    return min(100.0, torque / TORQUE_CAP * 100.0)


def _max_torque_score(max_torque: float) -> float:
    """Normalize gearbox max torque to a 0–100 score (legacy proxy mode)."""
    return min(100.0, max_torque / MAX_TORQUE_CAP * 100.0)


def _priority_lookup(
    vehicle_type: VehicleType, component: str
) -> dict[str, float]:
    """Build stat -> priority map for a component category."""
    priorities = calculate_component_priorities(vehicle_type)
    return {item.stat: item.priority for item in priorities[component]}


def _priority_weighted_fit(
    stat_scores: dict[str, float],
    priorities: dict[str, float],
    *,
    weight_scale: float = 1.0,
) -> tuple[float, list[str], dict[str, float]]:
    """
    Compute priority-weighted average fit from applicable stat scores.

    Returns fit score, reason strings, and per-stat weighted contributions.
    """
    weighted_sum = 0.0
    weight_total = 0.0
    contributions: list[tuple[str, float, float]] = []
    debug_contributions: dict[str, float] = {}

    for stat, priority in priorities.items():
        if stat not in stat_scores:
            continue
        effective_priority = priority * weight_scale
        score = stat_scores[stat]
        contribution = score * effective_priority
        weighted_sum += contribution
        weight_total += effective_priority
        contributions.append((stat, score, effective_priority))
        debug_contributions[stat] = contribution

    if weight_total == 0:
        return 0.0, [], debug_contributions

    fit = weighted_sum / weight_total
    contributions.sort(key=lambda item: item[1] * item[2], reverse=True)
    reasons = [
        f"Strong match on {stat.replace('_', ' ')} ({score:.0f})"
        for stat, score, _ in contributions[:3]
    ]
    return fit, reasons, debug_contributions


def _formula_package_component_weights(
    vehicle_type: VehicleType,
) -> tuple[float, float, float]:
    """Derive package weights from vehicle-type importance and influence matrices."""
    adjusted = get_adjusted_vehicle_weights(vehicle_type)

    def _component_weight(influence_matrix: dict[str, dict[str, float]]) -> float:
        total = 0.0
        for influences in influence_matrix.values():
            for rating, influence in influences.items():
                total += adjusted.get(rating, 0.0) * influence
        return total

    chassis_w = _component_weight(CHASSIS_INFLUENCE)
    engine_w = _component_weight(ENGINE_INFLUENCE)
    gearbox_w = _component_weight(GEARBOX_INFLUENCE)
    total = chassis_w + engine_w + gearbox_w
    if total == 0:
        return 1 / 3, 1 / 3, 1 / 3
    return chassis_w / total, engine_w / total, gearbox_w / total


def _package_component_weights(vehicle_type: VehicleType) -> tuple[float, float, float]:
    """
    Legacy package weights for best_fit / balanced / value objectives.

    Uses vehicle-type numeric importance weights only (not component names).
    """
    chassis_w = 0.35
    engine_w = 0.40
    gearbox_w = 0.25

    if vehicle_type.power >= 0.75:
        engine_w += 0.05
        gearbox_w += 0.05
        chassis_w -= 0.10

    if vehicle_type.drivability >= 0.75:
        chassis_w += 0.10
        gearbox_w += 0.05
        engine_w -= 0.15

    if vehicle_type.fuel >= 0.75:
        engine_w += 0.10
        gearbox_w += 0.05
        chassis_w -= 0.15

    if vehicle_type.cargo >= 0.75:
        chassis_w += 0.10
        engine_w += 0.05
        gearbox_w -= 0.15

    if vehicle_type.luxury >= 0.75:
        chassis_w += 0.10
        engine_w -= 0.05
        gearbox_w -= 0.05

    total = chassis_w + engine_w + gearbox_w
    return chassis_w / total, engine_w / total, gearbox_w / total


def proxy_chassis_unit_cost(chassis: ChassisCandidate) -> float:
    """Estimate chassis unit cost from formula-backed stats (proxy only)."""
    weight = chassis.weight if chassis.weight is not None else 150.0
    return max(50.0, weight * 1.2 + chassis.overall * 6.0)


def proxy_engine_unit_cost(engine: EngineCandidate) -> float:
    """Estimate engine unit cost from formula-backed stats (proxy only)."""
    weight = engine.weight if engine.weight is not None else 150.0
    return max(
        50.0,
        weight * 1.5
        + engine.horsepower * 4.0
        + engine.torque * 1.5
        + engine.overall * 5.0,
    )


def proxy_gearbox_unit_cost(gearbox: GearboxCandidate) -> float:
    """Estimate gearbox unit cost from formula-backed stats (proxy only)."""
    weight = gearbox.weight if gearbox.weight is not None else 100.0
    gears = gearbox.gears if gearbox.gears is not None else 3
    return max(50.0, weight * 1.0 + gears * 25.0 + gearbox.overall * 5.0)


def resolve_component_unit_cost(
    unit_cost: float,
    proxy_cost: float,
) -> tuple[float, bool]:
    """Return actual cost when present, otherwise labeled proxy cost."""
    if unit_cost > 0:
        return unit_cost, False
    return proxy_cost, True


def resolve_package_unit_cost(
    chassis: ChassisCandidate,
    engine: EngineCandidate,
    gearbox: GearboxCandidate,
    *,
    allow_proxy: bool = True,
) -> tuple[float, bool, dict[str, float]]:
    """
    Resolve package unit cost for value scoring.

    Proxy costs are used only when CSV unit_cost is zero/missing.
    """
    chassis_cost, chassis_proxy = resolve_component_unit_cost(
        chassis.unit_cost,
        proxy_chassis_unit_cost(chassis) if allow_proxy else 0.0,
    )
    engine_cost, engine_proxy = resolve_component_unit_cost(
        engine.unit_cost,
        proxy_engine_unit_cost(engine) if allow_proxy else 0.0,
    )
    gearbox_cost, gearbox_proxy = resolve_component_unit_cost(
        gearbox.unit_cost,
        proxy_gearbox_unit_cost(gearbox) if allow_proxy else 0.0,
    )
    breakdown = {
        "chassis": chassis_cost,
        "engine": engine_cost,
        "gearbox": gearbox_cost,
    }
    return chassis_cost + engine_cost + gearbox_cost, (
        chassis_proxy or engine_proxy or gearbox_proxy
    ), breakdown


def _build_chassis_stat_scores(
    chassis: ChassisCandidate,
    *,
    formula_fit: bool,
) -> tuple[dict[str, float], dict[str, float]]:
    """Build core and auxiliary chassis stat score maps."""
    core = {
        "comfort": chassis.comfort,
        "performance": chassis.performance,
        "strength": chassis.strength,
        "durability": chassis.durability,
    }
    auxiliary: dict[str, float] = {}
    if chassis.weight is not None:
        auxiliary["low_weight"] = _low_weight_score(chassis.weight)
    if (
        chassis.max_engine_width is not None
        and chassis.max_engine_length is not None
    ):
        auxiliary["engine_fit_room"] = _engine_fit_room_score(
            chassis.max_engine_width, chassis.max_engine_length
        )
    return core, auxiliary


def _build_engine_stat_scores(
    engine: EngineCandidate,
    *,
    formula_fit: bool,
) -> tuple[dict[str, float], dict[str, float]]:
    """Build core and auxiliary engine stat score maps."""
    if formula_fit:
        core = {
            "horsepower": scale_horsepower_to_rating(engine.horsepower),
            "torque": scale_torque_to_rating(engine.torque),
            "fuel_economy": engine.fuel_economy,
            "reliability": engine.reliability,
            "smoothness": engine.smoothness,
        }
    else:
        core = {
            "horsepower": _horsepower_score(engine.horsepower),
            "torque": _torque_score(engine.torque),
            "fuel_economy": engine.fuel_economy,
            "reliability": engine.reliability,
            "smoothness": engine.smoothness,
        }

    auxiliary: dict[str, float] = {}
    if engine.weight is not None:
        auxiliary["low_weight"] = _low_weight_score(engine.weight)
    if engine.width is not None and engine.length is not None:
        auxiliary["compact_size"] = _compact_size_score(engine.width, engine.length)
    return core, auxiliary


def _build_gearbox_stat_scores(
    gearbox: GearboxCandidate,
    *,
    formula_fit: bool,
) -> tuple[dict[str, float], dict[str, float]]:
    """Build core and auxiliary gearbox stat score maps."""
    core = {
        "fuel_economy": gearbox.fuel_economy,
        "performance": gearbox.performance,
        "reliability": gearbox.reliability,
        "comfort": gearbox.comfort,
    }
    if gearbox.max_torque is not None:
        if formula_fit:
            core["max_torque"] = scale_max_torque_to_rating(gearbox.max_torque)
        else:
            core["max_torque"] = _max_torque_score(gearbox.max_torque)

    auxiliary: dict[str, float] = {}
    if gearbox.weight is not None:
        auxiliary["low_weight"] = _low_weight_score(gearbox.weight)
    return core, auxiliary


def _score_component_formula_fit(
    component: str,
    overall: float,
    core_stats: dict[str, float],
    auxiliary_stats: dict[str, float],
    priorities: dict[str, float],
) -> tuple[float, list[str], dict[str, float]]:
    """Formula-first component score from overall plus priority-weighted stats."""
    core_fit, reasons, core_debug = _priority_weighted_fit(core_stats, priorities)
    aux_fit, _, aux_debug = _priority_weighted_fit(
        auxiliary_stats,
        priorities,
        weight_scale=AUXILIARY_STAT_WEIGHT,
    )
    fit_score = (
        FORMULA_FIT_OVERALL_SHARE * overall
        + FORMULA_FIT_STAT_SHARE * core_fit
        + FORMULA_FIT_AUXILIARY_SHARE * aux_fit
    )
    debug = {
        "overall": FORMULA_FIT_OVERALL_SHARE * overall,
        "core_fit": FORMULA_FIT_STAT_SHARE * core_fit,
        **{f"core.{k}": v * FORMULA_FIT_STAT_SHARE for k, v in core_debug.items()},
        **{f"aux.{k}": v * FORMULA_FIT_AUXILIARY_SHARE for k, v in aux_debug.items()},
        "component": component,
    }
    return fit_score, reasons, debug


def score_chassis_for_vehicle_type(
    chassis: ChassisCandidate,
    vehicle_type: VehicleType,
    *,
    formula_fit: bool = False,
) -> ComponentFitResult:
    """Score how well a chassis fits a vehicle type's stat priorities."""
    priorities = _priority_lookup(vehicle_type, "chassis")
    core_stats, auxiliary_stats = _build_chassis_stat_scores(
        chassis, formula_fit=formula_fit
    )

    if formula_fit:
        fit_score, reasons, debug = _score_component_formula_fit(
            "chassis",
            chassis.overall,
            core_stats,
            auxiliary_stats,
            priorities,
        )
        unit_cost, proxy_used = resolve_component_unit_cost(
            chassis.unit_cost, proxy_chassis_unit_cost(chassis)
        )
        value_score = fit_score / unit_cost if unit_cost > 0 else 0.0
        return ComponentFitResult(
            name=chassis.name,
            component="chassis",
            fit_score=fit_score,
            value_score=value_score,
            unit_cost=unit_cost,
            warnings=[],
            reasons=reasons,
            fit_debug=debug,
            proxy_cost_used=proxy_used,
        )

    stat_scores = {**core_stats, **auxiliary_stats}
    priority_fit, reasons, _ = _priority_weighted_fit(stat_scores, priorities)
    final_fit = PRIORITY_WEIGHT * priority_fit + OVERALL_BACKGROUND_WEIGHT * chassis.overall
    unit_cost, proxy_used = resolve_component_unit_cost(
        chassis.unit_cost, proxy_chassis_unit_cost(chassis)
    )
    value_score = final_fit / unit_cost if unit_cost > 0 else 0.0

    return ComponentFitResult(
        name=chassis.name,
        component="chassis",
        fit_score=final_fit,
        value_score=value_score,
        unit_cost=unit_cost,
        warnings=[],
        reasons=reasons,
        proxy_cost_used=proxy_used,
    )


def score_engine_for_vehicle_type(
    engine: EngineCandidate,
    vehicle_type: VehicleType,
    *,
    formula_fit: bool = False,
) -> ComponentFitResult:
    """Score how well an engine fits a vehicle type's stat priorities."""
    priorities = _priority_lookup(vehicle_type, "engine")
    core_stats, auxiliary_stats = _build_engine_stat_scores(
        engine, formula_fit=formula_fit
    )

    if formula_fit:
        fit_score, reasons, debug = _score_component_formula_fit(
            "engine",
            engine.overall,
            core_stats,
            auxiliary_stats,
            priorities,
        )
        unit_cost, proxy_used = resolve_component_unit_cost(
            engine.unit_cost, proxy_engine_unit_cost(engine)
        )
        value_score = fit_score / unit_cost if unit_cost > 0 else 0.0
        return ComponentFitResult(
            name=engine.name,
            component="engine",
            fit_score=fit_score,
            value_score=value_score,
            unit_cost=unit_cost,
            warnings=[],
            reasons=reasons,
            fit_debug=debug,
            proxy_cost_used=proxy_used,
        )

    stat_scores = {**core_stats, **auxiliary_stats}
    priority_fit, reasons, _ = _priority_weighted_fit(stat_scores, priorities)
    final_fit = PRIORITY_WEIGHT * priority_fit + OVERALL_BACKGROUND_WEIGHT * engine.overall
    unit_cost, proxy_used = resolve_component_unit_cost(
        engine.unit_cost, proxy_engine_unit_cost(engine)
    )
    value_score = final_fit / unit_cost if unit_cost > 0 else 0.0

    return ComponentFitResult(
        name=engine.name,
        component="engine",
        fit_score=final_fit,
        value_score=value_score,
        unit_cost=unit_cost,
        warnings=[],
        reasons=reasons,
        proxy_cost_used=proxy_used,
    )


def score_gearbox_for_vehicle_type(
    gearbox: GearboxCandidate,
    vehicle_type: VehicleType,
    engine: EngineCandidate | None = None,
    *,
    formula_fit: bool = False,
) -> ComponentFitResult:
    """Score how well a gearbox fits a vehicle type, with optional torque check."""
    priorities = _priority_lookup(vehicle_type, "gearbox")
    core_stats, auxiliary_stats = _build_gearbox_stat_scores(
        gearbox, formula_fit=formula_fit
    )

    warnings: list[str] = []
    torque_penalty = 1.0
    if (
        engine is not None
        and gearbox.max_torque is not None
        and gearbox.max_torque < engine.torque
    ):
        torque_penalty = max(0.0, min(1.0, gearbox.max_torque / engine.torque)) * 0.95
        warnings.append("Gearbox max torque is below engine torque.")

    if formula_fit:
        fit_score, reasons, debug = _score_component_formula_fit(
            "gearbox",
            gearbox.overall,
            core_stats,
            auxiliary_stats,
            priorities,
        )
        fit_score *= torque_penalty
        if torque_penalty < 1.0:
            debug["torque_penalty_factor"] = torque_penalty

        unit_cost, proxy_used = resolve_component_unit_cost(
            gearbox.unit_cost, proxy_gearbox_unit_cost(gearbox)
        )
        value_score = fit_score / unit_cost if unit_cost > 0 else 0.0
        return ComponentFitResult(
            name=gearbox.name,
            component="gearbox",
            fit_score=fit_score,
            value_score=value_score,
            unit_cost=unit_cost,
            warnings=warnings,
            reasons=reasons,
            fit_debug=debug,
            proxy_cost_used=proxy_used,
        )

    stat_scores = {**core_stats, **auxiliary_stats}
    priority_fit, reasons, _ = _priority_weighted_fit(stat_scores, priorities)
    final_fit = PRIORITY_WEIGHT * priority_fit + OVERALL_BACKGROUND_WEIGHT * gearbox.overall
    final_fit *= torque_penalty

    unit_cost, proxy_used = resolve_component_unit_cost(
        gearbox.unit_cost, proxy_gearbox_unit_cost(gearbox)
    )
    value_score = final_fit / unit_cost if unit_cost > 0 else 0.0

    return ComponentFitResult(
        name=gearbox.name,
        component="gearbox",
        fit_score=final_fit,
        value_score=value_score,
        unit_cost=unit_cost,
        warnings=warnings,
        reasons=reasons,
        proxy_cost_used=proxy_used,
    )


def _engine_fits_chassis(chassis: ChassisCandidate, engine: EngineCandidate) -> bool:
    """Return False if known dimensions prove the engine cannot fit."""
    if (
        chassis.max_engine_width is not None
        and engine.width is not None
        and engine.width > chassis.max_engine_width
    ):
        return False
    if (
        chassis.max_engine_length is not None
        and engine.length is not None
        and engine.length > chassis.max_engine_length
    ):
        return False
    return True


def rank_component_packages(
    chassis_list: list[ChassisCandidate],
    engine_list: list[EngineCandidate],
    gearbox_list: list[GearboxCandidate],
    vehicle_type: VehicleType,
    objective: str = "balanced",
    top: int = 20,
    year: int = 1901,
) -> list[ComponentPackageResult]:
    """
    Evaluate every chassis + engine + gearbox combination and rank packages.
    """
    if objective not in PACKAGE_OBJECTIVES:
        raise ValueError(
            f"Invalid objective {objective!r}. "
            f"Choose from: {', '.join(PACKAGE_OBJECTIVES)}"
        )

    uses_formula_components = objective in COMPONENT_FORMULA_OBJECTIVES
    uses_assembly_ranking = objective in ASSEMBLY_FORMULA_OBJECTIVES

    if uses_formula_components:
        chassis_w, engine_w, gearbox_w = _formula_package_component_weights(vehicle_type)
    else:
        chassis_w, engine_w, gearbox_w = _package_component_weights(vehicle_type)

    packages: list[ComponentPackageResult] = []

    for chassis in chassis_list:
        for engine in engine_list:
            if not _engine_fits_chassis(chassis, engine):
                continue

            for gearbox in gearbox_list:
                chassis_result = score_chassis_for_vehicle_type(
                    chassis,
                    vehicle_type,
                    formula_fit=uses_formula_components,
                )
                engine_result = score_engine_for_vehicle_type(
                    engine,
                    vehicle_type,
                    formula_fit=uses_formula_components,
                )
                gearbox_result = score_gearbox_for_vehicle_type(
                    gearbox,
                    vehicle_type,
                    engine=engine,
                    formula_fit=uses_formula_components,
                )

                component_package_score = (
                    chassis_w * chassis_result.fit_score
                    + engine_w * engine_result.fit_score
                    + gearbox_w * gearbox_result.fit_score
                )

                warnings = list(gearbox_result.warnings)
                total_unit_cost, proxy_used, cost_breakdown = resolve_package_unit_cost(
                    chassis, engine, gearbox, allow_proxy=True
                )

                assembly_ratings, assembly_fit, buyer_proxy = assemble_and_score_package(
                    ComponentAssemblyInput(chassis, engine, gearbox),
                    vehicle_type,
                    year=year,
                )
                final_formula_fit_score = calculate_final_formula_fit_score(
                    assembly_fit,
                    assembly_ratings.overall,
                    assembly_ratings.quality,
                )
                final_formula_value_score = (
                    final_formula_fit_score / total_unit_cost
                    if total_unit_cost > 0
                    else 0.0
                )

                if uses_assembly_ranking:
                    package_score = final_formula_fit_score
                    package_value_score = final_formula_value_score
                elif objective == "component_fit":
                    package_score = component_package_score
                    package_value_score = (
                        component_package_score / total_unit_cost
                        if total_unit_cost > 0
                        else 0.0
                    )
                else:
                    package_score = component_package_score
                    package_value_score = (
                        component_package_score / total_unit_cost
                        if total_unit_cost > 0
                        else 0.0
                    )

                fit_debug = {
                    "objective": objective,
                    "component_weights": {
                        "chassis": chassis_w,
                        "engine": engine_w,
                        "gearbox": gearbox_w,
                    },
                    "chassis_fit": chassis_result.fit_score,
                    "engine_fit": engine_result.fit_score,
                    "gearbox_fit": gearbox_result.fit_score,
                    "component_package_score": component_package_score,
                    "assembly_vehicle_type_fit": assembly_fit,
                    "assembly_overall": assembly_ratings.overall,
                    "assembly_quality": assembly_ratings.quality,
                    "final_formula_fit_score": final_formula_fit_score,
                    "final_formula_value_score": final_formula_value_score,
                    "chassis": chassis_result.fit_debug,
                    "engine": engine_result.fit_debug,
                    "gearbox": gearbox_result.fit_debug,
                    "cost_breakdown": cost_breakdown,
                    "proxy_cost_used": proxy_used,
                    "assembly_ratings": {
                        "performance": assembly_ratings.performance,
                        "drivability": assembly_ratings.drivability,
                        "luxury": assembly_ratings.luxury,
                        "safety": assembly_ratings.safety,
                        "fuel": assembly_ratings.fuel,
                        "power": assembly_ratings.power,
                        "cargo": assembly_ratings.cargo,
                        "dependability": assembly_ratings.dependability,
                        "quality": assembly_ratings.quality,
                        "overall": assembly_ratings.overall,
                    },
                    "assembly_buyer_rating_proxy": buyer_proxy,
                }

                packages.append(
                    ComponentPackageResult(
                        chassis_name=chassis.name,
                        engine_name=engine.name,
                        gearbox_name=gearbox.name,
                        package_score=package_score,
                        package_value_score=package_value_score,
                        total_unit_cost=total_unit_cost,
                        warnings=warnings,
                        chassis_fit=chassis_result.fit_score,
                        engine_fit=engine_result.fit_score,
                        gearbox_fit=gearbox_result.fit_score,
                        chassis_reasons=chassis_result.reasons,
                        engine_reasons=engine_result.reasons,
                        gearbox_reasons=gearbox_result.reasons,
                        fit_debug=fit_debug,
                        proxy_cost_used=proxy_used,
                        component_package_score=component_package_score,
                        assembly_vehicle_type_fit=assembly_fit,
                        assembly_overall=assembly_ratings.overall,
                        assembly_quality=assembly_ratings.quality,
                        final_formula_fit_score=final_formula_fit_score,
                    )
                )

    if objective == "balanced" and packages:
        raw_scores = [p.package_score for p in packages]
        raw_values = [p.package_value_score for p in packages]
        norm_scores = _normalize_column(raw_scores)
        norm_values = _normalize_column(raw_values)
        indexed = list(enumerate(packages))
        indexed.sort(
            key=lambda item: 0.75 * norm_scores[item[0]] + 0.25 * norm_values[item[0]],
            reverse=True,
        )
        packages = [package for _, package in indexed]
    elif objective == "formula_balanced" and packages:
        raw_fits = [p.final_formula_fit_score or 0.0 for p in packages]
        raw_values = [p.package_value_score for p in packages]
        norm_fits = _normalize_column(raw_fits)
        norm_values = _normalize_column(raw_values)
        for index, package in enumerate(packages):
            package.package_score = (
                0.75 * norm_fits[index] + 0.25 * norm_values[index]
            )
        packages.sort(key=lambda p: p.package_score, reverse=True)
    elif objective in ("value", "formula_value"):
        packages.sort(key=lambda p: p.package_value_score, reverse=True)
    else:
        packages.sort(key=lambda p: p.package_score, reverse=True)

    return packages[:top]
