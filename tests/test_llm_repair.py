"""Tests for LLM auto-repair when designs fail physical fit."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from gearcity_optimizer.core.models import VehicleType
from gearcity_optimizer.importers.components_xml import parse_components_xml
from gearcity_optimizer.llm.config import LLMConfig
from gearcity_optimizer.llm.strategy_client import parse_llm_strategy_response
from gearcity_optimizer.llm.strategy_models import ValidatedLLMStrategyResult
from gearcity_optimizer.reports.design_optimizer import (
    DesignOptimizationInput,
    _design_needs_llm_repair,
    _repair_candidate_is_better,
    optimize_design,
)
from gearcity_optimizer.reports.design_objective import DesignScore
from gearcity_optimizer.reports.design_physical_constraints import PhysicalFitAssessment


REPAIR_STRATEGY_JSON = json.dumps(
    {
        "component_choices": [
            {
                "section": "gearbox",
                "choice_type": "gear_count",
                "recommended_choice": "4Gear",
                "alternatives": [],
                "reason": "more gears for torque capacity",
                "confidence": "high",
            }
        ],
        "slider_guidance": [
            {
                "section": "engine",
                "slider_label": "Engine Torque",
                "direction": "lower",
                "suggested_range": [20, 40],
                "reason": "reduce engine torque to fit gearbox",
            },
            {
                "section": "gearbox",
                "slider_label": "Torque Max Input",
                "direction": "higher",
                "suggested_range": [60, 85],
                "reason": "raise gearbox torque support",
            },
        ],
        "expected_tradeoffs": ["less peak torque"],
        "risks": [],
        "explanation": "Lower engine torque and strengthen gearbox.",
    }
)


@pytest.fixture
def fixture_xml_path():
    from pathlib import Path

    return (
        Path(__file__).resolve().parent
        / "fixtures"
        / "components"
        / "sample_components.xml"
    )


@pytest.fixture
def sample_catalog(fixture_xml_path):
    return parse_components_xml(fixture_xml_path)


@pytest.fixture
def sedan_type() -> VehicleType:
    return VehicleType(
        name="Sedan",
        performance=0.4,
        drivability=0.4,
        luxury=0.45,
        safety=0.65,
        fuel=0.65,
        power=0.45,
        cargo=0.5,
        dependability=0.45,
        wealth_demo=4,
        military_fleet=False,
        civilian_fleet=True,
    )


def _failed_score() -> DesignScore:
    fit = PhysicalFitAssessment(
        engine_torque_lbft=27000.0,
        gearbox_max_torque_lbft=150.0,
        torque_margin_ratio=0.01,
        torque_ok=False,
        violations=(
            "Gearbox max torque support (150 lb-ft) is below predicted engine torque (27000 lb-ft).",
        ),
        penalty=50.0,
    )
    return DesignScore(
        total_score=0.0,
        weighted_stat_score=70.0,
        cost_penalty=0.0,
        complexity_penalty=0.0,
        mismatch_penalty=50.0,
        low_priority_stat_penalty=0.0,
        component_confidence_penalty=0.0,
        failed_thresholds=["Gearbox torque support"],
        warnings=list(fit.violations),
        quality_status="Failed",
        physical_fit=fit,
    )


def _fixed_score() -> DesignScore:
    fit = PhysicalFitAssessment(
        engine_torque_lbft=180.0,
        gearbox_max_torque_lbft=220.0,
        torque_margin_ratio=1.22,
        torque_ok=True,
        violations=(),
        penalty=0.0,
    )
    return DesignScore(
        total_score=55.0,
        weighted_stat_score=60.0,
        cost_penalty=0.0,
        complexity_penalty=0.0,
        mismatch_penalty=0.0,
        low_priority_stat_penalty=0.0,
        component_confidence_penalty=0.0,
        failed_thresholds=[],
        warnings=[],
        quality_status="Usable",
        physical_fit=fit,
    )


def test_design_needs_llm_repair_on_torque_violation():
    assert _design_needs_llm_repair(_failed_score())
    assert not _design_needs_llm_repair(_fixed_score())


def test_repair_candidate_prefers_fixed_physical_fit():
    assert _repair_candidate_is_better(_fixed_score(), _failed_score())
    assert not _repair_candidate_is_better(_failed_score(), _fixed_score())


def test_llm_mode_triggers_repair_when_design_fails(
    sedan_type, sample_catalog, monkeypatch, wiki_model_paths
):
    from gearcity_optimizer.importers.component_choices import get_available_component_choices

    available = get_available_component_choices(
        1920, 0.0, 100.0, 100.0, 0.0, catalog=sample_catalog
    )
    monkeypatch.setattr(
        "gearcity_optimizer.reports.design_optimizer.get_available_component_choices",
        lambda *args, **kwargs: available,
    )

    initial_strategy = parse_llm_strategy_response(REPAIR_STRATEGY_JSON)
    repair_strategy = parse_llm_strategy_response(REPAIR_STRATEGY_JSON)
    config = LLMConfig(enabled=True, backend="ollama", model="llama3.2")

    call_count = {"search": 0}

    def fake_search(**kwargs):
        call_count["search"] += 1
        from gearcity_optimizer.reports.design_search import (
            CompleteDesignCandidate,
            GlobalDesignSearchResult,
        )
        from gearcity_optimizer.reports.design_objective import build_design_objective
        from gearcity_optimizer.reports.slider_optimizer import SliderOptimizationResult

        score = _failed_score() if call_count["search"] == 1 else _fixed_score()
        slider = SliderOptimizationResult(
            control_settings=[],
            predicted_outputs=[],
            goals=[],
            tradeoffs=[],
            warnings=[],
            limitations=[],
            wiki_model_loaded=True,
            optimization_disabled=False,
        )
        candidate = CompleteDesignCandidate(
            component_choices=kwargs.get("manual_choices") or {},
            slider_result=slider,
            design_score=score,
            heuristic_score=0.0,
            why_selected="test",
        )
        return GlobalDesignSearchResult(
            best=candidate,
            alternatives=[],
            objective=build_design_objective(sedan_type, "balanced"),
            searched_component_sets=1,
            warnings=[],
        )

    repair_result = ValidatedLLMStrategyResult(
        strategy=repair_strategy,
        component_validations=(),
        slider_validations=(),
        accepted_choices={"gear_count": available[0]},
        accepted_slider_guidance=repair_strategy.slider_guidance,
        warnings=(),
        validation_summary="repair ok",
        llm_available=True,
    )

    with patch(
        "gearcity_optimizer.llm.strategy_validator.request_llm_strategy",
        return_value=initial_strategy,
    ), patch(
        "gearcity_optimizer.reports.design_optimizer.search_best_complete_design",
        side_effect=fake_search,
    ), patch(
        "gearcity_optimizer.llm.strategy_validator.request_llm_repair_strategy",
        return_value=repair_strategy,
    ), patch(
        "gearcity_optimizer.reports.design_optimizer.run_llm_design_repair",
        return_value=repair_result,
    ):
        result = optimize_design(
            DesignOptimizationInput(
                vehicle_type=sedan_type,
                year=1920,
                cost_mode="balanced",
                engine_skill=100.0,
                recommendation_mode="llm",
                llm_config=config,
                available_choices=available,
            )
        )

    assert result.llm_repair_attempts >= 1
    assert call_count["search"] >= 2
    assert result.design_score is not None
    assert result.design_score.physical_fit is not None
    assert result.design_score.physical_fit.torque_ok is True
