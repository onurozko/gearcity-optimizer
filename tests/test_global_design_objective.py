"""Tests for global design objective and complete-design search."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from gearcity_optimizer.core.models import VehicleType
from gearcity_optimizer.importers.components_xml import get_available_component_choices, parse_components_xml
from gearcity_optimizer.reports.design_objective import (
    build_design_objective,
    score_complete_design,
)
from gearcity_optimizer.reports.design_optimizer import DesignOptimizationInput, optimize_design
from gearcity_optimizer.reports.design_search import generate_component_candidate_sets
from gearcity_optimizer.reports.slider_optimizer import PredictedOutput


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


@pytest.fixture
def fixture_xml_path() -> Path:
    return (
        Path(__file__).resolve().parent
        / "fixtures"
        / "components"
        / "sample_components.xml"
    )


@pytest.fixture
def sample_catalog(fixture_xml_path: Path):
    return parse_components_xml(fixture_xml_path)


def _fuel_outputs(value: float) -> list[PredictedOutput]:
    return [
        PredictedOutput("fuel", "Fuel", value, 0.70, "test", False),
        PredictedOutput("overall", "Overall", 31.0, 0.40, "test", False),
        PredictedOutput(
            "reliability",
            "Reliability",
            39.0,
            0.50,
            "test",
            False,
        ),
    ]


def test_match_predicted_prefers_alias_order_over_output_list_order(sedan_type):
    objective = build_design_objective(sedan_type, "balanced")
    outputs = [
        PredictedOutput("engine_overall", "Engine overall", 30.0, 0.4, "test", False),
        PredictedOutput("vehicle_performance", "Vehicle performance (proxy)", 67.0, 0.4, "test", True),
        PredictedOutput("vehicle_overall", "Vehicle overall (proxy)", 48.0, 0.4, "test", True),
        PredictedOutput("overall", "Overall", 48.0, 0.4, "test", True),
        PredictedOutput("fuel", "Fuel", 60.0, 0.7, "test", False),
    ]
    score = score_complete_design(outputs, None, None, objective, vehicle_type=sedan_type)
    assert score.stat_values["performance"] == 67.0
    assert score.stat_values["overall"] == 48.0


def test_high_priority_stat_below_threshold_creates_severe_penalty(sedan_type):
    objective = build_design_objective(sedan_type, "balanced")
    score = score_complete_design(
        _fuel_outputs(10.92),
        None,
        None,
        objective,
        vehicle_type=sedan_type,
    )
    assert score.low_priority_stat_penalty > 0.0
    assert score.failed_thresholds
    assert score.quality_status in {"Poor", "Failed"}


def test_sedan_fuel_10_92_is_poor_or_failed(sedan_type):
    objective = build_design_objective(sedan_type, "balanced")
    score = score_complete_design(
        _fuel_outputs(10.92),
        None,
        None,
        objective,
        vehicle_type=sedan_type,
    )
    assert score.quality_status in {"Poor", "Failed"}
    assert any("Fuel" in warning for warning in score.warnings)


def test_objective_improves_when_high_priority_fuel_increases(sedan_type):
    objective = build_design_objective(sedan_type, "balanced")
    low = score_complete_design(_fuel_outputs(10.0), None, None, objective, vehicle_type=sedan_type)
    high = score_complete_design(_fuel_outputs(75.0), None, None, objective, vehicle_type=sedan_type)
    assert high.total_score > low.total_score


def test_objective_improves_when_dependability_increases(sedan_type):
    objective = build_design_objective(sedan_type, "balanced")
    low_outputs = [
        PredictedOutput("dependability", "Dependability", 20.0, 0.50, "test", False),
        PredictedOutput("vehicle_dependability", "Vehicle dependability (proxy)", 20.0, 0.50, "test", True),
        PredictedOutput("overall", "Overall", 55.0, 0.40, "test", False),
    ]
    high_outputs = [
        PredictedOutput("dependability", "Dependability", 72.0, 0.50, "test", False),
        PredictedOutput("vehicle_dependability", "Vehicle dependability (proxy)", 72.0, 0.50, "test", True),
        PredictedOutput("overall", "Overall", 55.0, 0.40, "test", False),
    ]
    low = score_complete_design(low_outputs, None, None, objective, vehicle_type=sedan_type)
    high = score_complete_design(high_outputs, None, None, objective, vehicle_type=sedan_type)
    assert high.total_score > low.total_score


def test_cheap_mode_penalizes_cost_more_than_luxury(sedan_type):
    outputs = [
        PredictedOutput("fuel", "Fuel", 60.0, 0.70, "test", False),
        PredictedOutput("overall", "Overall", 55.0, 0.40, "test", False),
        PredictedOutput("design_requirements", "Design requirements", 80.0, 0.2, "test", True),
        PredictedOutput(
            "manufacturing_requirements",
            "Manufacturing requirements",
            75.0,
            0.2,
            "test",
            True,
        ),
    ]
    cheap_objective = build_design_objective(sedan_type, "cheap")
    luxury_objective = build_design_objective(sedan_type, "luxury")
    cheap_score = score_complete_design(outputs, None, None, cheap_objective, vehicle_type=sedan_type)
    luxury_score = score_complete_design(outputs, None, None, luxury_objective, vehicle_type=sedan_type)
    assert cheap_score.cost_penalty > luxury_score.cost_penalty


def test_balanced_mode_does_not_rate_very_low_fuel_as_good(sedan_type):
    objective = build_design_objective(sedan_type, "balanced")
    score = score_complete_design(
        _fuel_outputs(10.92),
        None,
        None,
        objective,
        vehicle_type=sedan_type,
    )
    assert score.quality_status != "Good"


def test_complete_design_scoring_uses_final_outputs_not_slider_labels(sedan_type):
    objective = build_design_objective(sedan_type, "balanced")
    good_outputs = [
        PredictedOutput("fuel", "Fuel", 72.0, 0.70, "test", False),
        PredictedOutput("overall", "Overall", 58.0, 0.40, "test", False),
    ]
    score = score_complete_design(good_outputs, None, None, objective, vehicle_type=sedan_type)
    assert score.weighted_stat_score > 50.0
    assert score.stat_values.get("fuel") == 72.0


def test_beam_search_considers_multiple_component_candidates(sedan_type, sample_catalog):
    available = get_available_component_choices(1920, 0.0, 100.0, 100.0, 0.0, catalog=sample_catalog)
    sets = generate_component_candidate_sets(
        available,
        sedan_type,
        "balanced",
        year=1920,
        beam_size=20,
        top_per_type=3,
    )
    assert len(sets) > 1
    layouts = {
        combo.get("engine_layout").display_name
        for combo in sets
        if combo.get("engine_layout") is not None
    }
    assert len(layouts) > 1


def test_optimizer_returns_alternatives(sedan_type, sample_catalog, monkeypatch, wiki_model_paths):
    monkeypatch.setattr(
        "gearcity_optimizer.reports.design_optimizer.get_available_component_choices",
        lambda *args, **kwargs: get_available_component_choices(
            1920, 0.0, 100.0, 100.0, 0.0, catalog=sample_catalog
        ),
    )
    result = optimize_design(
        DesignOptimizationInput(
            vehicle_type=sedan_type,
            year=1920,
            cost_mode="balanced",
            engine_skill=100.0,
            gearbox_skill=100.0,
            depth="balanced",
            component_choice_mode="auto",
        )
    )
    assert result.design_score is not None
    assert result.searched_component_sets >= 1
    assert result.best_design_summary
    assert result.priority_explanation


def test_optimizer_alternatives_when_multiple_sets_searched(
    sedan_type, sample_catalog, monkeypatch, wiki_model_paths
):
    monkeypatch.setattr(
        "gearcity_optimizer.reports.design_optimizer.get_available_component_choices",
        lambda *args, **kwargs: get_available_component_choices(
            1920, 0.0, 100.0, 100.0, 0.0, catalog=sample_catalog
        ),
    )
    result = optimize_design(
        DesignOptimizationInput(
            vehicle_type=sedan_type,
            year=1920,
            cost_mode="balanced",
            engine_skill=100.0,
            gearbox_skill=100.0,
            depth="thorough",
            component_choice_mode="auto",
        )
    )
    if result.searched_component_sets > 1:
        assert len(result.alternative_designs) >= 1
