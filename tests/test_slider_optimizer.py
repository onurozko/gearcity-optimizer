"""Tests for real slider registry and optimizer."""

from __future__ import annotations

import pytest

from gearcity_optimizer.cli import SUBCOMMANDS, main
from gearcity_optimizer.core.models import VehicleType
from gearcity_optimizer.core.slider_registry import (
    OUTPUT_STAT_KEYS,
    REAL_SLIDERS,
    is_output_stat_key,
    list_sliders,
    validate_registry,
)
from gearcity_optimizer.core.vehicle_types import load_vehicle_types
from gearcity_optimizer.reports.slider_optimizer import (
    SliderOptimizationInput,
    optimize_real_slider_settings,
)


def _vehicle_type(name: str) -> VehicleType:
    return load_vehicle_types("data/vehicle_types.csv")[name]


def test_slider_registry_contains_only_real_controllable_inputs():
    assert REAL_SLIDERS
    warnings = validate_registry()
    assert not warnings
    for slider in REAL_SLIDERS:
        assert not is_output_stat_key(slider.field_name)
        assert slider.field_name not in OUTPUT_STAT_KEYS


def test_output_stats_are_not_control_settings():
    sedan = _vehicle_type("Sedan")
    result = optimize_real_slider_settings(
        SliderOptimizationInput(
            vehicle_type=sedan,
            year=1913,
            cost_mode="cheap",
        )
    )
    control_keys = {item.slider_key for item in result.control_settings}
    forbidden = {"torque", "horsepower", "cargo", "fuel_economy", "power_rating"}
    assert forbidden.isdisjoint(control_keys)
    labels = " ".join(item.label.lower() for item in result.control_settings)
    assert "torque slider" not in labels
    assert "horsepower slider" not in labels


def test_optimizer_returns_controls_and_predicted_outputs_separately():
    sedan = _vehicle_type("Sedan")
    result = optimize_real_slider_settings(
        SliderOptimizationInput(
            vehicle_type=sedan,
            year=1913,
            cost_mode="balanced",
        )
    )
    assert result.control_settings
    assert result.predicted_outputs
    assert any(item.output_key == "engine_torque" for item in result.predicted_outputs)
    assert any(item.slider_key == "engine.bore" for item in result.control_settings)
    assert result.goals
    assert result.tradeoffs
    assert result.limitations


def test_same_input_produces_deterministic_output():
    sedan = _vehicle_type("Sedan")
    input_data = SliderOptimizationInput(
        vehicle_type=sedan,
        year=1913,
        cost_mode="cheap",
        chassis_skill=15,
        engine_skill=0,
        gearbox_skill=0,
        vehicle_skill=0,
    )
    first = optimize_real_slider_settings(input_data)
    second = optimize_real_slider_settings(input_data)
    assert first.control_settings == second.control_settings
    assert first.predicted_outputs == second.predicted_outputs


def test_all_control_values_within_min_max():
    truck = _vehicle_type("Pickup Truck")
    result = optimize_real_slider_settings(
        SliderOptimizationInput(
            vehicle_type=truck,
            year=1905,
            cost_mode="balanced",
        )
    )
    slider_by_key = {slider.key: slider for slider in list_sliders()}
    for setting in result.control_settings:
        slider = slider_by_key[setting.slider_key]
        if slider.max_value <= 1.0 and slider.min_value >= 0.0 and slider.field_name not in {
            "cylinders",
            "number_of_gears",
        } and not slider.field_name.startswith(("has_", "is_")):
            assert 0.0 <= setting.value <= 100.0
        else:
            assert slider.min_value <= setting.value <= slider.max_value


def test_cli_slider_audit_and_optimize_sliders_registered():
    assert "slider-audit" in SUBCOMMANDS
    assert "optimize-sliders" in SUBCOMMANDS


def test_cli_optimize_sliders_separates_controls_and_outputs(capsys):
    exit_code = main(
        [
            "optimize-sliders",
            "--vehicle-type",
            "Sedan",
            "--year",
            "1913",
            "--cost-mode",
            "cheap",
            "--chassis-skill",
            "15",
            "--engine-skill",
            "0",
            "--gearbox-skill",
            "0",
            "--vehicle-skill",
            "0",
            "--depth",
            "balanced",
        ]
    )
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Actual controls to set" in output
    assert "Predicted output stats" in output
    assert "Bore" in output or "bore" in output.lower()
    assert "Engine torque" in output or "torque" in output.lower()


def test_cli_slider_audit_lists_engine_section(capsys):
    exit_code = main(["slider-audit", "--section", "engine"])
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "design_fuel_economy" in output or "Engine design focus" in output
    assert "bore" in output.lower()
