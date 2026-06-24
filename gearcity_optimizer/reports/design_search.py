"""Global complete-design search: component beam search + slider objective optimization."""

from __future__ import annotations

from dataclasses import dataclass, field

from gearcity_optimizer.core.component_vehicle_groups import filter_engine_layout_candidates
from gearcity_optimizer.core.wiki_component_compatibility import filter_compatible_candidates
from gearcity_optimizer.core.cost_mode import CostMode, parse_cost_mode
from gearcity_optimizer.core.models import VehicleType
from gearcity_optimizer.importers.component_choices import ComponentChoice
from gearcity_optimizer.reports.component_choice_recommender import (
    CHASSIS_CHOICE_TYPES,
    ENGINE_CHOICE_TYPES,
    GEARBOX_CHOICE_TYPES,
    score_component_suitability,
)
from gearcity_optimizer.reports.design_objective import (
    DesignObjective,
    DesignScore,
    build_design_objective,
    design_score_for_optimization,
    score_complete_design,
)
from gearcity_optimizer.reports.slider_optimizer import (
    SliderOptimizationInput,
    SliderOptimizationResult,
    optimize_sliders_for_objective,
    _depth_search_params,
)

BEAM_SEARCH_TYPES: tuple[str, ...] = (
    "engine_layout",
    "cylinder_count",
    "fuel_type",
    "valvetrain",
    "forced_induction",
    "frame",
    "suspension",
    "drivetrain",
    "gearbox_type",
    "gear_count",
)


@dataclass(frozen=True)
class CompleteDesignCandidate:
    """One evaluated complete design."""

    component_choices: dict[str, ComponentChoice]
    slider_result: SliderOptimizationResult
    design_score: DesignScore
    heuristic_score: float = 0.0
    rejection_reason: str | None = None
    why_selected: str = ""


@dataclass
class GlobalDesignSearchResult:
    """Best complete design and alternatives from global search."""

    best: CompleteDesignCandidate | None
    alternatives: list[CompleteDesignCandidate] = field(default_factory=list)
    objective: DesignObjective | None = None
    searched_component_sets: int = 0
    warnings: list[str] = field(default_factory=list)


def _group_choices_by_type(
    available_choices: list[ComponentChoice],
) -> dict[str, list[ComponentChoice]]:
    grouped: dict[str, list[ComponentChoice]] = {}
    for choice in available_choices:
        if choice.choice_type == "unknown":
            continue
        grouped.setdefault(choice.choice_type, []).append(choice)
    return grouped


def _rank_candidates_for_type(
    choice_type: str,
    candidates: list[ComponentChoice],
    *,
    vehicle_type: VehicleType,
    cost_mode: CostMode,
    year: int,
    top_n: int,
) -> list[tuple[float, ComponentChoice]]:
    scored: list[tuple[float, ComponentChoice]] = []
    for choice in candidates:
        suitability = score_component_suitability(
            choice,
            vehicle_type=vehicle_type,
            cost_mode=cost_mode,
            year=year,
            candidates=candidates,
        )
        scored.append((suitability.total_score, choice))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[:top_n]


def generate_component_candidate_sets(
    available_choices: list[ComponentChoice],
    vehicle_type: VehicleType,
    cost_mode: str,
    *,
    year: int = 1900,
    beam_size: int = 20,
    top_per_type: int = 3,
    manual_choices: dict[str, ComponentChoice] | None = None,
) -> list[dict[str, ComponentChoice]]:
    """
    Build diverse component choice combinations via beam search.

    Keeps multiple reasonable candidates per category instead of only the top parsed choice.
    """
    grouped = _group_choices_by_type(available_choices)
    if manual_choices:
        return [dict(manual_choices)]

    cost_mode_enum = parse_cost_mode(cost_mode)
    ranked_by_type: dict[str, list[tuple[float, ComponentChoice]]] = {}
    for choice_type in BEAM_SEARCH_TYPES:
        candidates = grouped.get(choice_type, [])
        if not candidates:
            continue
        if choice_type == "engine_layout":
            candidates = filter_engine_layout_candidates(candidates, vehicle_type=vehicle_type)
        ranked_by_type[choice_type] = _rank_candidates_for_type(
            choice_type,
            candidates,
            vehicle_type=vehicle_type,
            cost_mode=cost_mode_enum,
            year=year,
            top_n=top_per_type,
        )

    if not ranked_by_type:
        return [{}]

    beam: list[tuple[float, dict[str, ComponentChoice]]] = [(0.0, {})]
    for choice_type in BEAM_SEARCH_TYPES:
        options = ranked_by_type.get(choice_type)
        if not options:
            continue
        next_beam: list[tuple[float, dict[str, ComponentChoice]]] = []
        for partial_score, partial in beam:
            for score, choice in options:
                if not filter_compatible_candidates(choice_type, choice, partial):
                    continue
                combined = dict(partial)
                combined[choice_type] = choice
                next_beam.append((partial_score + score, combined))
        next_beam.sort(key=lambda item: item[0], reverse=True)
        beam = next_beam[:beam_size]

    complete_sets: list[dict[str, ComponentChoice]] = []
    for _, partial in beam:
        complete = dict(partial)
        for choice_type, candidates in grouped.items():
            if choice_type in complete or choice_type not in (
                *ENGINE_CHOICE_TYPES,
                *CHASSIS_CHOICE_TYPES,
                *GEARBOX_CHOICE_TYPES,
            ):
                continue
            ranked = _rank_candidates_for_type(
                choice_type,
                candidates,
                vehicle_type=vehicle_type,
                cost_mode=cost_mode_enum,
                year=year,
                top_n=top_per_type if choice_type in {"cylinder_count", "gear_count"} else 1,
            )
            compatible = [
                (score, choice)
                for score, choice in ranked
                if filter_compatible_candidates(choice_type, choice, complete)
            ]
            if compatible:
                complete[choice_type] = compatible[0][1]
        complete_sets.append(complete)

    unique: list[dict[str, ComponentChoice]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for combo in complete_sets:
        key = tuple(sorted((ctype, choice.name) for ctype, choice in combo.items()))
        if key in seen:
            continue
        seen.add(key)
        unique.append(combo)
    return unique[:beam_size]


def _choice_summary(choices: dict[str, ComponentChoice]) -> str:
    key_types = ("engine_layout", "fuel_type", "frame", "gearbox_type")
    parts = [
        f"{ctype}={choices[ctype].display_name}"
        for ctype in key_types
        if ctype in choices
    ]
    return ", ".join(parts) if parts else "default components"


def _why_design_won(candidate: CompleteDesignCandidate, objective: DesignObjective) -> str:
    top_stats = sorted(
        objective.stat_weights.items(),
        key=lambda item: item[1],
        reverse=True,
    )[:3]
    stat_bits = []
    for stat, weight in top_stats:
        label = stat.replace("_", " ").title()
        value = candidate.design_score.stat_values.get(stat)
        if value is not None:
            stat_bits.append(f"{label} {value:.1f} (weight {weight:.2f})")
    summary = _choice_summary(candidate.component_choices)
    return (
        f"Best complete design for {objective.vehicle_type_name} {objective.cost_mode} mode. "
        f"Global score {candidate.design_score.total_score:.1f} ({candidate.design_score.quality_status}). "
        f"Components: {summary}. "
        f"Top predicted stats: {', '.join(stat_bits)}."
    )


def search_best_complete_design(
    *,
    vehicle_type: VehicleType,
    year: int,
    cost_mode: str,
    chassis_skill: float,
    engine_skill: float,
    gearbox_skill: float,
    vehicle_skill: float,
    depth: str,
    available_choices: list[ComponentChoice],
    manual_choices: dict[str, ComponentChoice] | None = None,
    slider_guidance=None,
    max_alternatives: int = 4,
) -> GlobalDesignSearchResult:
    """Search component combinations and slider settings for the best complete design."""
    objective = build_design_objective(vehicle_type, cost_mode)
    cost_mode_enum = parse_cost_mode(cost_mode)
    top_per_type, _, _, max_full_evaluations = _depth_search_params(depth)  # type: ignore[arg-type]
    beam_size = 10 if depth == "quick" else 16 if depth == "balanced" else 24
    grouped = _group_choices_by_type(available_choices)

    component_sets = generate_component_candidate_sets(
        available_choices,
        vehicle_type,
        cost_mode,
        year=year,
        beam_size=beam_size,
        top_per_type=top_per_type,
        manual_choices=manual_choices,
    )

    if manual_choices is None and len(component_sets) > max_full_evaluations:
        scored_sets: list[tuple[float, dict[str, ComponentChoice]]] = []
        for choices in component_sets:
            heuristic = sum(
                score_component_suitability(
                    choice,
                    vehicle_type=vehicle_type,
                    cost_mode=cost_mode_enum,
                    year=year,
                    candidates=grouped.get(choice_type, [choice]),
                ).total_score
                for choice_type, choice in choices.items()
            )
            scored_sets.append((heuristic, choices))
        scored_sets.sort(key=lambda item: item[0], reverse=True)
        component_sets = [choices for _, choices in scored_sets[:max_full_evaluations]]

    evaluated: list[CompleteDesignCandidate] = []
    warnings: list[str] = []

    for choices in component_sets:
        slider_input = SliderOptimizationInput(
            vehicle_type=vehicle_type,
            year=year,
            cost_mode=cost_mode,
            chassis_skill=chassis_skill,
            engine_skill=engine_skill,
            gearbox_skill=gearbox_skill,
            vehicle_skill=vehicle_skill,
            depth=depth,  # type: ignore[arg-type]
            selected_choices=choices or None,
            slider_guidance=slider_guidance,
            available_choices_by_type=grouped,
        )

        def score_fn(result: SliderOptimizationResult, _choices=choices) -> float:
            if not result.predicted_outputs:
                return float("-inf")
            design_score = score_complete_design(
                result.predicted_outputs,
                _choices or None,
                result.control_settings,
                objective,
                vehicle_type=vehicle_type,
                year=year,
                available_by_type=grouped,
                engine_result=result.engine_result,
                chassis_result=result.chassis_result,
                gearbox_result=result.gearbox_result,
            )
            return design_score_for_optimization(design_score)

        slider_result = optimize_sliders_for_objective(slider_input, score_fn=score_fn)
        if slider_result.optimization_disabled or not slider_result.predicted_outputs:
            warnings.append("Wiki mechanics model unavailable; global search skipped.")
            continue

        effective_choices = slider_result.adjusted_component_choices or choices

        design_score = score_complete_design(
            slider_result.predicted_outputs,
            effective_choices or None,
            slider_result.control_settings,
            objective,
            vehicle_type=vehicle_type,
            year=year,
            available_by_type=grouped,
            engine_result=slider_result.engine_result,
            chassis_result=slider_result.chassis_result,
            gearbox_result=slider_result.gearbox_result,
        )
        heuristic = sum(
            score_component_suitability(
                choice,
                vehicle_type=vehicle_type,
                cost_mode=cost_mode_enum,
                year=year,
                candidates=grouped.get(choice_type, [choice]),
            ).total_score
            for choice_type, choice in (effective_choices or {}).items()
        )
        evaluated.append(
            CompleteDesignCandidate(
                component_choices=dict(effective_choices),
                slider_result=slider_result,
                design_score=design_score,
                heuristic_score=heuristic,
            )
        )

    if not evaluated:
        return GlobalDesignSearchResult(
            best=None,
            alternatives=[],
            objective=objective,
            searched_component_sets=len(component_sets),
            warnings=warnings,
        )

    evaluated.sort(key=lambda item: item.design_score.total_score, reverse=True)
    best = evaluated[0]
    best = CompleteDesignCandidate(
        component_choices=best.component_choices,
        slider_result=best.slider_result,
        design_score=best.design_score,
        heuristic_score=best.heuristic_score,
        why_selected=_why_design_won(best, objective),
    )

    alternatives: list[CompleteDesignCandidate] = []
    for candidate in evaluated[1 : max_alternatives + 1]:
        fuel = candidate.design_score.stat_values.get("fuel")
        overall = candidate.design_score.stat_values.get("overall")
        dependability = candidate.design_score.stat_values.get("dependability")
        rejection = (
            f"Score {candidate.design_score.total_score:.1f} vs best "
            f"{best.design_score.total_score:.1f}. "
            f"Fuel {fuel:.1f} | Overall {overall:.1f} | Dependability {dependability:.1f}. "
            f"Components: {_choice_summary(candidate.component_choices)}."
            if fuel is not None and overall is not None and dependability is not None
            else f"Lower global score ({candidate.design_score.total_score:.1f})."
        )
        alternatives.append(
            CompleteDesignCandidate(
                component_choices=candidate.component_choices,
                slider_result=candidate.slider_result,
                design_score=candidate.design_score,
                heuristic_score=candidate.heuristic_score,
                rejection_reason=rejection,
            )
        )

    if best.design_score.quality_status in {"Poor", "Failed"}:
        warnings.append(
            "Best design found is still "
            f"{best.design_score.quality_status}. "
            "Predicted outputs remain below targets for this vehicle type. "
            "Component parsing, formula model completeness, or manual component selection may be needed."
        )

    return GlobalDesignSearchResult(
        best=best,
        alternatives=alternatives,
        objective=objective,
        searched_component_sets=len(component_sets),
        warnings=warnings,
    )
