"""Tests for recommendation preview logic."""

from __future__ import annotations

import pytest

from gearcity_optimizer.core.cost_mode import CostMode, parse_cost_mode
from gearcity_optimizer.core.models import VehicleType
from gearcity_optimizer.core.vehicle_types import load_vehicle_types
from gearcity_optimizer.reports.part_recommender import (
    RecommendationInput,
    build_recommendation_result,
    is_work_or_utility_focused,
    normalize_focus_labels,
    parse_cost_mode_display,
)


def _vehicle_type(name: str) -> VehicleType:
    return load_vehicle_types("data/vehicle_types.csv")[name]


def test_cost_mode_accepts_only_cheap_balanced_luxury():
    assert parse_cost_mode("cheap") is CostMode.CHEAP
    assert parse_cost_mode_display("Cheap") == "cheap"
    assert parse_cost_mode_display("Balanced") == "balanced"
    assert parse_cost_mode_display("Luxury") == "luxury"
    with pytest.raises(ValueError, match="Cost mode must be one of"):
        parse_cost_mode("premium")


def test_recommendation_preview_does_not_duplicate_equivalent_labels():
    labels = normalize_focus_labels(
        [
            "Maximum Torque Support",
            "max torque",
            "Design Focus: Dependability",
            "dependability",
            "Fuel Economy Rating",
            "fuel economy",
        ]
    )
    assert labels == [
        "Maximum Torque Support",
        "Design Focus: Dependability",
        "Fuel Economy Rating",
    ]


def test_sedan_cheap_recommendation_excludes_workhorse_note():
    sedan = _vehicle_type("Sedan")
    result = build_recommendation_result(
        vehicle_type=sedan,
        inputs=RecommendationInput(
            vehicle_type_name="Sedan",
            year=1901,
            cost_mode="cheap",
            chassis_skill=10,
            engine_skill=10,
            gearbox_skill=10,
            vehicle_skill=10,
        ),
        catalog=None,
    )
    combined = " ".join(
        [
            result.strategy_summary,
            result.gearbox_guidance,
            " ".join(result.recommended_focus),
        ]
    ).lower()
    assert "work-focused vehicle type" not in combined
    assert "overbuild it unnecessarily" in result.gearbox_guidance.lower()


def test_work_vehicle_recommendation_can_include_workhorse_note():
    truck = _vehicle_type("Pickup Truck")
    assert is_work_or_utility_focused(truck) is True

    result = build_recommendation_result(
        vehicle_type=truck,
        inputs=RecommendationInput(
            vehicle_type_name="Pickup Truck",
            year=1901,
            cost_mode="cheap",
            chassis_skill=10,
            engine_skill=10,
            gearbox_skill=10,
            vehicle_skill=10,
        ),
        catalog=None,
    )
    assert "work-focused vehicle type" in result.gearbox_guidance.lower()


def test_sedan_is_not_work_or_utility_focused():
    sedan = _vehicle_type("Sedan")
    assert is_work_or_utility_focused(sedan) is False


def test_recommendation_result_includes_structured_sections():
    sedan = _vehicle_type("Sedan")
    result = build_recommendation_result(
        vehicle_type=sedan,
        inputs=RecommendationInput(
            vehicle_type_name="Sedan",
            year=1901,
            cost_mode="balanced",
            chassis_skill=10,
            engine_skill=10,
            gearbox_skill=10,
            vehicle_skill=10,
        ),
        catalog=None,
    )
    assert result.strategy_summary
    assert result.chassis_section.top_priorities
    assert result.engine_section.top_priorities
    assert result.gearbox_section.top_priorities
    assert result.design_testing_focus
    assert result.avoid
    assert result.limitations
    assert any("experimental" in note.lower() for note in result.limitations)


def test_cost_mode_changes_strategy_summary():
    sedan = _vehicle_type("Sedan")
    cheap = build_recommendation_result(
        vehicle_type=sedan,
        inputs=RecommendationInput(
            vehicle_type_name="Sedan",
            year=1901,
            cost_mode="cheap",
            chassis_skill=0,
            engine_skill=0,
            gearbox_skill=0,
            vehicle_skill=0,
        ),
        catalog=None,
    )
    luxury = build_recommendation_result(
        vehicle_type=sedan,
        inputs=RecommendationInput(
            vehicle_type_name="Sedan",
            year=1901,
            cost_mode="luxury",
            chassis_skill=0,
            engine_skill=0,
            gearbox_skill=0,
            vehicle_skill=0,
        ),
        catalog=None,
    )
    assert cheap.strategy_summary != luxury.strategy_summary
    assert "low-cost" in cheap.strategy_summary.lower()
    assert "luxury" in luxury.strategy_summary.lower() or "higher-end" in luxury.strategy_summary.lower()
