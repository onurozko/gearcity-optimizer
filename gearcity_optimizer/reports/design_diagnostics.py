"""Structured diagnostics for design optimization runs."""

from __future__ import annotations

from dataclasses import dataclass, field

from gearcity_optimizer.core.component_formula_bridge import count_wired_subcomponent_fields
from gearcity_optimizer.importers.component_choices import ComponentChoice
from gearcity_optimizer.reports.design_objective import DesignScore
from gearcity_optimizer.reports.design_physical_constraints import (
    PhysicalFitAssessment,
    assess_physical_fit,
    physical_fit_summary_lines,
)
from gearcity_optimizer.reports.slider_optimizer import SliderOptimizationResult


@dataclass(frozen=True)
class DesignRunDiagnostics:
    """Human-readable trace of what the optimizer did."""

    optimization_path: str
    available_choice_count: int
    searched_component_sets: int
    evaluated_candidates: int
    selected_choice_types: tuple[str, ...] = ()
    formula_fields_wired: int = 0
    wiki_model_loaded: bool = False
    global_search_succeeded: bool = False
    used_fallback_sliders: bool = False
    engine_overall: float | None = None
    vehicle_overall: float | None = None
    vehicle_quality: float | None = None
    design_status: str | None = None
    total_score: float | None = None
    search_depth_used: str | None = None
    used_llm_fast_path: bool = False
    recommendation_phase_seconds: float | None = None
    search_phase_seconds: float | None = None
    torque_margin_ratio: float | None = None
    engine_bay_ok: bool | None = None
    lines: tuple[str, ...] = ()

    def to_lines(self) -> list[str]:
        return list(self.lines)


def build_design_run_diagnostics(
    *,
    available_choice_count: int,
    searched_component_sets: int,
    evaluated_candidates: int,
    global_search_succeeded: bool,
    selected_design_choices: dict[str, ComponentChoice],
    slider_result: SliderOptimizationResult,
    design_score: DesignScore | None,
    search_depth_used: str | None = None,
    used_llm_fast_path: bool = False,
    recommendation_phase_seconds: float | None = None,
    search_phase_seconds: float | None = None,
) -> DesignRunDiagnostics:
    """Build a diagnostic summary for UI display."""
    wired, _ = count_wired_subcomponent_fields(selected_design_choices or None)
    wiki_loaded = slider_result.wiki_model_loaded and not slider_result.optimization_disabled

    if global_search_succeeded:
        path = "llm_fast_path" if used_llm_fast_path else "global_search"
    elif available_choice_count == 0:
        path = "slider_only_no_catalog"
    elif evaluated_candidates == 0:
        path = "fallback_sliders_search_empty"
    else:
        path = "fallback_sliders"

    engine_overall = None
    vehicle_overall = None
    vehicle_quality = None
    for output in slider_result.predicted_outputs:
        if output.output_key == "engine_overall":
            engine_overall = output.value
        elif output.output_key == "vehicle_overall":
            vehicle_overall = output.value
        elif output.output_key == "vehicle_quality":
            vehicle_quality = output.value
        elif output.output_key == "overall" and engine_overall is None:
            engine_overall = output.value

    if slider_result.vehicle_ratings is not None:
        vehicle_overall = vehicle_overall or slider_result.vehicle_ratings.overall
        vehicle_quality = vehicle_quality or slider_result.vehicle_ratings.quality

    physical_fit: PhysicalFitAssessment | None = None
    if design_score is not None and design_score.physical_fit is not None:
        physical_fit = design_score.physical_fit
    elif wiki_loaded:
        physical_fit = assess_physical_fit(
            engine=slider_result.engine_result,
            chassis=slider_result.chassis_result,
            gearbox=slider_result.gearbox_result,
            predicted_outputs=slider_result.predicted_outputs,
        )

    lines: list[str] = [
        f"Path: {path}",
        f"Components.xml choices available: {available_choice_count}",
        f"Component sets searched: {searched_component_sets}",
        f"Candidates evaluated: {evaluated_candidates}",
        f"Wiki formula model loaded: {'yes' if wiki_loaded else 'no'}",
        f"Selected component types ({len(selected_design_choices)}): "
        + (", ".join(sorted(selected_design_choices.keys())) if selected_design_choices else "(none)"),
        f"Formula subcomponent fields wired: {wired}",
    ]
    if search_depth_used:
        lines.append(f"Search depth used: {search_depth_used}")
    if recommendation_phase_seconds is not None:
        lines.append(f"Recommendation phase: {recommendation_phase_seconds:.2f}s")
    if search_phase_seconds is not None:
        lines.append(f"Search phase: {search_phase_seconds:.2f}s")
    if physical_fit is not None:
        lines.append("--- Physical fit (formula-backed) ---")
        lines.extend(physical_fit_summary_lines(physical_fit))
    if engine_overall is not None:
        lines.append(f"Predicted engine overall: {engine_overall:.1f}")
    if vehicle_overall is not None:
        lines.append(f"Predicted vehicle overall (proxy): {vehicle_overall:.1f}")
    if vehicle_quality is not None:
        lines.append(f"Predicted vehicle quality (proxy): {vehicle_quality:.1f}")
    if design_score is not None:
        lines.append(
            f"Design status: {design_score.quality_status} | Global score: {design_score.total_score:.1f}"
        )
        if design_score.failed_thresholds:
            lines.append("Failed thresholds: " + ", ".join(design_score.failed_thresholds))

    if path == "slider_only_no_catalog":
        lines.append(
            "ISSUE: Import Components.xml in Tech Availability. Without it, formulas use "
            "generic defaults and overall stays near 30."
        )
    elif not selected_design_choices:
        lines.append(
            "ISSUE: No component choices were passed into the formula pipeline. "
            "Predictions are generic placeholder values."
        )
    elif wired < 4:
        lines.append(
            "ISSUE: Very few subcomponent stats were mapped from selected parts. "
            "Check the component parsing audit for missing scoring attributes."
        )
    elif engine_overall is not None and engine_overall < 35.0 and vehicle_overall is not None and vehicle_overall >= 45.0:
        lines.append(
            "NOTE: Engine overall is low but assembled vehicle proxy is higher. "
            "Use vehicle overall rows when judging the complete design."
        )

    return DesignRunDiagnostics(
        optimization_path=path,
        available_choice_count=available_choice_count,
        searched_component_sets=searched_component_sets,
        evaluated_candidates=evaluated_candidates,
        selected_choice_types=tuple(sorted(selected_design_choices.keys())),
        formula_fields_wired=wired,
        wiki_model_loaded=wiki_loaded,
        global_search_succeeded=global_search_succeeded,
        used_fallback_sliders=path.startswith("fallback") or path == "slider_only_no_catalog",
        engine_overall=engine_overall,
        vehicle_overall=vehicle_overall,
        vehicle_quality=vehicle_quality,
        design_status=design_score.quality_status if design_score else None,
        total_score=design_score.total_score if design_score else None,
        search_depth_used=search_depth_used,
        used_llm_fast_path=used_llm_fast_path,
        recommendation_phase_seconds=recommendation_phase_seconds,
        search_phase_seconds=search_phase_seconds,
        torque_margin_ratio=physical_fit.torque_margin_ratio if physical_fit else None,
        engine_bay_ok=physical_fit.engine_bay_ok if physical_fit else None,
        lines=tuple(lines),
    )
