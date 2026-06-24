"""Unified Design Optimizer combining component choices and slider controls."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal

from gearcity_optimizer.core.models import VehicleType
from gearcity_optimizer.importers.component_choices import ComponentChoice, get_available_component_choices
from gearcity_optimizer.llm.config import LLMConfig, load_llm_config_from_env, is_llm_configured
from gearcity_optimizer.llm.strategy_models import ValidatedLLMStrategyResult
from gearcity_optimizer.llm.strategy_validator import run_llm_assisted_strategy, run_llm_design_repair
from gearcity_optimizer.core.cost_mode import parse_cost_mode
from gearcity_optimizer.core.wiki_component_compatibility import is_valid_partial_choices
from gearcity_optimizer.reports.component_choice_recommender import (
    ComponentChoiceRecommendationResult,
    ChoiceRecommendation,
    is_reliable_auto_pick_status,
    recommend_component_choices,
    score_component_suitability,
)
from gearcity_optimizer.reports.design_objective import (
    DesignObjective,
    DesignObjectiveEvaluation,
    DesignScore,
    build_design_objective,
    build_priority_explanation,
    design_score_to_legacy,
    score_complete_design,
)
from gearcity_optimizer.reports.design_diagnostics import (
    DesignRunDiagnostics,
    build_design_run_diagnostics,
)
from gearcity_optimizer.reports.design_search import (
    CompleteDesignCandidate,
    GlobalDesignSearchResult,
    search_best_complete_design,
)
from gearcity_optimizer.reports.slider_optimizer import (
    SliderOptimizationInput,
    SliderOptimizationResult,
    optimize_real_slider_settings,
)

ComponentChoiceMode = Literal["auto", "manual"]
RecommendationMode = Literal["deterministic", "llm"]

LLM_ASSISTED_DISCLAIMER = (
    "LLM-assisted experimental mode. LLM suggestions are validated against Components.xml, "
    "wiki-backed slider registry, and formula/proxy scoring before display."
)

LLM_FAST_PATH_NOTE = (
    "LLM fast path: validating the LLM component set with lightweight slider tuning "
    "(skips multi-candidate beam search)."
)

MAX_LLM_REPAIR_ATTEMPTS = 2

LLM_AUTO_REPAIR_NOTE = (
    "LLM auto-repair: when physical fit fails, the model revises components and slider "
    f"guidance and re-runs optimization (up to {MAX_LLM_REPAIR_ATTEMPTS} repair passes)."
)

GLOBAL_SEARCH_LIMITATION = (
    "Global design search compares complete component + slider combinations using predicted "
    "vehicle outputs and vehicle-type priority weights."
)


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
    recommendation_mode: RecommendationMode = "deterministic"
    llm_config: LLMConfig | None = None
    quarter: int = 4
    available_choices: list[ComponentChoice] | None = None


@dataclass(frozen=True)
class DesignOptimizationResult:
    """Recommended component choices, slider controls, and predicted outputs."""

    component_choices: ComponentChoiceRecommendationResult | None
    slider_result: SliderOptimizationResult
    available_choice_count: int
    component_choice_mode: ComponentChoiceMode
    recommendation_mode: RecommendationMode = "deterministic"
    llm_validation: ValidatedLLMStrategyResult | None = None
    objective: DesignObjectiveEvaluation | None = None
    design_score: DesignScore | None = None
    design_objective: DesignObjective | None = None
    selected_design_choices: dict[str, ComponentChoice] = field(default_factory=dict)
    best_design_summary: str = ""
    alternative_designs: tuple[CompleteDesignCandidate, ...] = ()
    priority_explanation: tuple[str, ...] = ()
    searched_component_sets: int = 0
    warnings: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    diagnostics: DesignRunDiagnostics | None = None
    llm_repair_attempts: int = 0
    llm_repair_notes: tuple[str, ...] = ()


def _design_needs_llm_repair(design_score: DesignScore | None) -> bool:
    """Return True when LLM should try to fix a failed or physically invalid design."""
    if design_score is None:
        return False
    fit = design_score.physical_fit
    if fit is not None and fit.has_violations:
        return True
    return design_score.quality_status == "Failed" and design_score.total_score <= 30.0


def _repair_candidate_is_better(
    candidate: DesignScore,
    current: DesignScore,
) -> bool:
    """Prefer designs that fix physical violations, then higher total score."""
    cand_fit = candidate.physical_fit
    curr_fit = current.physical_fit
    cand_bad = cand_fit.has_violations if cand_fit else False
    curr_bad = curr_fit.has_violations if curr_fit else False
    if curr_bad and not cand_bad:
        return True
    if cand_bad and not curr_bad:
        return False
    return candidate.total_score > current.total_score


def _apply_search_best(
    search_result: GlobalDesignSearchResult,
) -> tuple[
    SliderOptimizationResult,
    DesignScore,
    str,
    tuple[CompleteDesignCandidate, ...],
    dict[str, ComponentChoice],
    int,
] | None:
    """Extract state from a successful global search result."""
    if search_result.best is None:
        return None
    best = search_result.best
    evaluated = len(search_result.alternatives) + 1
    return (
        best.slider_result,
        best.design_score,
        best.why_selected,
        tuple(search_result.alternatives),
        dict(best.component_choices),
        evaluated,
    )


def _selected_choices_from_recommendations(
    choice_result: ComponentChoiceRecommendationResult,
    *,
    component_choice_mode: ComponentChoiceMode,
    manual_choices: dict[str, ComponentChoice] | None,
) -> dict[str, ComponentChoice]:
    if component_choice_mode == "manual":
        return dict(manual_choices or {})
    selected: dict[str, ComponentChoice] = {}
    for recommendation in choice_result.choices:
        if not is_reliable_auto_pick_status(recommendation.auto_pick_status):
            continue
        choice = recommendation.recommended_choice or recommendation.top_candidate
        if choice is not None:
            selected[recommendation.choice_type] = choice
    return selected


def _group_available_choices(
    available_choices: list[ComponentChoice],
) -> dict[str, list[ComponentChoice]]:
    grouped: dict[str, list[ComponentChoice]] = {}
    for choice in available_choices:
        if choice.choice_type == "unknown":
            continue
        grouped.setdefault(choice.choice_type, []).append(choice)
    return grouped


def build_fallback_component_choices(
    available_choices: list[ComponentChoice],
    *,
    vehicle_type: VehicleType,
    cost_mode: str,
    year: int,
) -> dict[str, ComponentChoice]:
    """Pick the best wiki-compatible candidate per choice type for formula fallback."""
    cost_mode_enum = parse_cost_mode(cost_mode)
    grouped = _group_available_choices(available_choices)
    selected: dict[str, ComponentChoice] = {}
    for choice_type, candidates in grouped.items():
        ranked = sorted(
            candidates,
            key=lambda choice: score_component_suitability(
                choice,
                vehicle_type=vehicle_type,
                cost_mode=cost_mode_enum,
                year=year,
                candidates=candidates,
            ).total_score,
            reverse=True,
        )
        for candidate in ranked:
            trial = dict(selected)
            trial[choice_type] = candidate
            if is_valid_partial_choices(trial):
                selected[choice_type] = candidate
                break
    return selected


def optimize_design(input_data: DesignOptimizationInput) -> DesignOptimizationResult:
    """Recommend component choices and slider controls for a design setup."""
    skills = {
        "chassis": input_data.chassis_skill,
        "engine": input_data.engine_skill,
        "gearbox": input_data.gearbox_skill,
        "vehicle": input_data.vehicle_skill,
    }
    available_choices = input_data.available_choices
    if available_choices is None:
        available_choices = get_available_component_choices(
            input_data.year,
            input_data.chassis_skill,
            input_data.engine_skill,
            input_data.gearbox_skill,
            input_data.vehicle_skill,
            quarter=input_data.quarter,
        )

    choice_result: ComponentChoiceRecommendationResult | None = None
    slider_guidance = None
    llm_validation: ValidatedLLMStrategyResult | None = None
    warnings: list[str] = []
    llm_config = input_data.llm_config or load_llm_config_from_env()
    design_objective = build_design_objective(input_data.vehicle_type, input_data.cost_mode)
    priority_explanation = tuple(
        build_priority_explanation(input_data.vehicle_type, design_objective)
    )

    manual_for_search: dict[str, ComponentChoice] | None = None
    if input_data.component_choice_mode == "manual":
        manual_for_search = dict(input_data.manual_choices or {})

    llm_phase_seconds: float | None = None
    search_phase_seconds: float | None = None
    search_depth = input_data.depth
    search_max_alternatives = 4
    used_llm_fast_path = False

    recommendation_phase_start = time.perf_counter()
    if available_choices:
        choice_result = recommend_component_choices(
            vehicle_type=input_data.vehicle_type,
            cost_mode=input_data.cost_mode,
            year=input_data.year,
            skills=skills,
            available_choices=available_choices,
            manual_selections=manual_for_search,
            component_choice_mode=input_data.component_choice_mode,
        )
        warnings.extend(choice_result.warnings)

        if input_data.recommendation_mode == "llm":
            warnings.append(LLM_ASSISTED_DISCLAIMER)
            llm_validation = run_llm_assisted_strategy(
                vehicle_type=input_data.vehicle_type,
                cost_mode=input_data.cost_mode,
                year=input_data.year,
                skills=skills,
                available_choices=available_choices,
                deterministic_result=choice_result,
                deterministic_warnings=warnings,
                config=llm_config,
            )
            warnings.extend(list(llm_validation.warnings))
            if llm_validation.accepted_choices:
                manual_for_search = dict(llm_validation.accepted_choices)
                search_depth = "llm"
                search_max_alternatives = 0
                used_llm_fast_path = True
                warnings.append(LLM_FAST_PATH_NOTE)
                warnings.append(LLM_AUTO_REPAIR_NOTE)
            slider_guidance = llm_validation.accepted_slider_guidance or None
    else:
        warnings.append(
            "Components.xml is required for component/dropdown recommendations. "
            "Slider optimization can still run, but component choices cannot be ranked."
        )
    recommendation_phase_seconds = time.perf_counter() - recommendation_phase_start

    search_result: GlobalDesignSearchResult | None = None
    slider_result: SliderOptimizationResult
    design_score: DesignScore | None = None
    best_summary = ""
    alternatives: tuple[CompleteDesignCandidate, ...] = ()
    selected_design_choices: dict[str, ComponentChoice] = {}
    evaluated_candidates = 0
    global_search_succeeded = False

    if available_choices:
        search_phase_start = time.perf_counter()
        search_result = search_best_complete_design(
            vehicle_type=input_data.vehicle_type,
            year=input_data.year,
            cost_mode=input_data.cost_mode,
            chassis_skill=input_data.chassis_skill,
            engine_skill=input_data.engine_skill,
            gearbox_skill=input_data.gearbox_skill,
            vehicle_skill=input_data.vehicle_skill,
            depth=search_depth,
            available_choices=available_choices,
            manual_choices=manual_for_search,
            slider_guidance=slider_guidance,
            max_alternatives=search_max_alternatives,
        )
        search_phase_seconds = time.perf_counter() - search_phase_start
        warnings.extend(search_result.warnings)

    if search_result is not None and search_result.best is not None:
        best = search_result.best
        slider_result = best.slider_result
        design_score = best.design_score
        best_summary = best.why_selected
        alternatives = tuple(search_result.alternatives)
        selected_design_choices = dict(best.component_choices)
        evaluated_candidates = len(search_result.alternatives) + 1
        global_search_succeeded = True
        warnings.extend(design_score.warnings)
    else:
        selected_choices: dict[str, ComponentChoice] = {}
        if manual_for_search:
            selected_choices = dict(manual_for_search)
        elif available_choices:
            selected_choices = build_fallback_component_choices(
                available_choices,
                vehicle_type=input_data.vehicle_type,
                cost_mode=input_data.cost_mode,
                year=input_data.year,
            )
            if selected_choices:
                warnings.append(
                    "Global component search did not return a best design. "
                    f"Using best-effort component set ({len(selected_choices)} types) "
                    "for formula-backed slider optimization."
                )
            else:
                warnings.append(
                    "Global component search failed and no fallback component set could be built."
                )
        elif choice_result is not None:
            selected_choices = _selected_choices_from_recommendations(
                choice_result,
                component_choice_mode=input_data.component_choice_mode,
                manual_choices=manual_for_search,
            )
        if not selected_choices and available_choices:
            warnings.append(
                "CRITICAL: Component choices are not reaching the formula pipeline. "
                "Predicted overall will stay near 30 until Components.xml choices are wired."
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
                slider_guidance=slider_guidance,
                available_choices_by_type=_group_available_choices(available_choices),
            )
        )
        if slider_result.predicted_outputs and not slider_result.optimization_disabled:
            if slider_result.adjusted_component_choices:
                selected_choices = dict(slider_result.adjusted_component_choices)
            design_score = score_complete_design(
                slider_result.predicted_outputs,
                selected_choices or None,
                slider_result.control_settings,
                design_objective,
                vehicle_type=input_data.vehicle_type,
                year=input_data.year,
                engine_result=slider_result.engine_result,
                chassis_result=slider_result.chassis_result,
                gearbox_result=slider_result.gearbox_result,
            )
            selected_design_choices = dict(selected_choices)
            warnings.extend(design_score.warnings)
            warnings.extend(list(slider_result.torque_repair_notes))

    llm_repair_attempts = 0
    llm_repair_notes: list[str] = []
    if (
        input_data.recommendation_mode == "llm"
        and is_llm_configured(llm_config)
        and available_choices
        and design_score is not None
    ):
        while (
            llm_repair_attempts < MAX_LLM_REPAIR_ATTEMPTS
            and _design_needs_llm_repair(design_score)
        ):
            llm_repair_attempts += 1
            repair = run_llm_design_repair(
                vehicle_type=input_data.vehicle_type,
                cost_mode=input_data.cost_mode,
                year=input_data.year,
                skills=skills,
                available_choices=available_choices,
                selected_choices=selected_design_choices,
                design_score=design_score,
                config=llm_config,
                repair_attempt=llm_repair_attempts,
                max_attempts=MAX_LLM_REPAIR_ATTEMPTS,
            )
            llm_repair_notes.append(repair.validation_summary)
            warnings.extend(list(repair.warnings))
            if not repair.llm_available:
                llm_repair_notes.append("Repair stopped: LLM unavailable.")
                break
            if not repair.accepted_choices and not repair.accepted_slider_guidance:
                llm_repair_notes.append(
                    f"Repair attempt {llm_repair_attempts}: no validated changes from LLM."
                )
                break

            if repair.accepted_choices:
                manual_for_search = dict(repair.accepted_choices)
            if repair.accepted_slider_guidance:
                slider_guidance = repair.accepted_slider_guidance

            repair_search = search_best_complete_design(
                vehicle_type=input_data.vehicle_type,
                year=input_data.year,
                cost_mode=input_data.cost_mode,
                chassis_skill=input_data.chassis_skill,
                engine_skill=input_data.engine_skill,
                gearbox_skill=input_data.gearbox_skill,
                vehicle_skill=input_data.vehicle_skill,
                depth="llm",
                available_choices=available_choices,
                manual_choices=manual_for_search,
                slider_guidance=slider_guidance,
                max_alternatives=0,
            )
            warnings.extend(repair_search.warnings)
            applied = _apply_search_best(repair_search)
            if applied is None:
                llm_repair_notes.append(
                    f"Repair attempt {llm_repair_attempts}: re-optimization returned no design."
                )
                continue

            (
                candidate_slider,
                candidate_score,
                candidate_summary,
                candidate_alts,
                candidate_choices,
                candidate_evaluated,
            ) = applied
            if _repair_candidate_is_better(candidate_score, design_score):
                slider_result = candidate_slider
                design_score = candidate_score
                best_summary = candidate_summary
                alternatives = candidate_alts
                selected_design_choices = candidate_choices
                evaluated_candidates = candidate_evaluated
                global_search_succeeded = True
                search_result = repair_search
                warnings.extend(design_score.warnings)
                llm_repair_notes.append(
                    f"Repair attempt {llm_repair_attempts} improved the design "
                    f"(score {design_score.total_score:.1f}, {design_score.quality_status})."
                )
            else:
                llm_repair_notes.append(
                    f"Repair attempt {llm_repair_attempts} did not beat the previous design."
                )

            if not _design_needs_llm_repair(design_score):
                llm_repair_notes.append(
                    f"Physical fit satisfied after repair attempt {llm_repair_attempts}."
                )
                break

        if _design_needs_llm_repair(design_score):
            warnings.append(
                "LLM auto-repair exhausted. Design still fails physical fit or scores poorly. "
                "Try manual component selection, lower optimization targets, or a different year."
            )

    diagnostics = build_design_run_diagnostics(
        available_choice_count=len(available_choices),
        searched_component_sets=search_result.searched_component_sets if search_result else 0,
        evaluated_candidates=evaluated_candidates,
        global_search_succeeded=global_search_succeeded,
        selected_design_choices=selected_design_choices,
        slider_result=slider_result,
        design_score=design_score,
        search_depth_used=search_depth,
        used_llm_fast_path=used_llm_fast_path,
        recommendation_phase_seconds=recommendation_phase_seconds,
        search_phase_seconds=search_phase_seconds,
    )
    warnings.extend(
        line for line in diagnostics.lines if line.startswith("ISSUE:")
    )

    objective: DesignObjectiveEvaluation | None = None
    if design_score is not None:
        objective = design_score_to_legacy(design_score)

    limitations = list(slider_result.limitations)
    limitations.insert(0, GLOBAL_SEARCH_LIMITATION)
    if choice_result is None:
        limitations.append(
            "Import Components.xml to enable component/dropdown candidate inspection."
        )
    elif input_data.recommendation_mode == "llm":
        limitations.append(
            "LLM-assisted mode is experimental. Deterministic formulas and validators remain "
            "the final authority for slider values and predicted outputs."
        )
        if llm_validation is not None:
            limitations.append(llm_validation.validation_summary)
    else:
        limitations.append(
            "Component rankings show suitability heuristics; the accepted design is chosen by "
            "global predicted-output scoring across complete design candidates."
        )

    if design_score is not None and design_score.quality_status in {"Poor", "Failed"}:
        limitations.insert(
            1,
            "Best design found is still "
            f"{design_score.quality_status}. Predicted outputs remain below vehicle-type targets. "
            "Manual component selection or improved source data may be required.",
        )

    return DesignOptimizationResult(
        component_choices=choice_result,
        slider_result=slider_result,
        available_choice_count=len(available_choices),
        component_choice_mode=input_data.component_choice_mode,
        recommendation_mode=input_data.recommendation_mode,
        llm_validation=llm_validation,
        objective=objective,
        design_score=design_score,
        design_objective=design_objective,
        selected_design_choices=selected_design_choices,
        best_design_summary=best_summary,
        alternative_designs=alternatives,
        priority_explanation=priority_explanation,
        searched_component_sets=search_result.searched_component_sets if search_result else 0,
        warnings=warnings + list(slider_result.warnings),
        limitations=limitations,
        diagnostics=diagnostics,
        llm_repair_attempts=llm_repair_attempts,
        llm_repair_notes=tuple(llm_repair_notes),
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
