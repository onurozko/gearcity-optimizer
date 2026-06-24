"""Tests for design run diagnostics."""

from __future__ import annotations

from gearcity_optimizer.reports.design_diagnostics import build_design_run_diagnostics
from gearcity_optimizer.reports.slider_optimizer import (
    PredictedOutput,
    SliderOptimizationResult,
)


def test_diagnostics_flags_missing_components():
    result = SliderOptimizationResult(
        control_settings=[],
        predicted_outputs=[
            PredictedOutput("overall", "Overall", 29.5, 0.4, "test", True),
        ],
        goals=[],
        tradeoffs=[],
        warnings=[],
        limitations=[],
        wiki_model_loaded=True,
        optimization_disabled=False,
    )
    diag = build_design_run_diagnostics(
        available_choice_count=0,
        searched_component_sets=0,
        evaluated_candidates=0,
        global_search_succeeded=False,
        selected_design_choices={},
        slider_result=result,
        design_score=None,
    )
    assert diag.optimization_path == "slider_only_no_catalog"
    assert any(line.startswith("ISSUE:") for line in diag.lines)
