"""Tests for real slider registry and optimizer."""

from __future__ import annotations

import pytest

from gearcity_optimizer.cli import SUBCOMMANDS, main
from gearcity_optimizer.core.models import VehicleType
from gearcity_optimizer.core.slider_registry import (
    list_sliders,
    validate_registry,
    wiki_model_available,
)
from gearcity_optimizer.core.vehicle_types import load_vehicle_types
from gearcity_optimizer.core.wiki_variable_classification import is_output_stat_key
from gearcity_optimizer.reports.slider_optimizer import (
    SliderOptimizationInput,
    optimize_real_slider_settings,
)
from gearcity_optimizer.ui.slider_audit import screenshot_label_sections


def _vehicle_type(name: str) -> VehicleType:
    return load_vehicle_types("data/vehicle_types.csv")[name]


def test_optimizer_refuses_exact_optimization_without_wiki_model(missing_wiki_model) -> None:
    sedan = _vehicle_type("Sedan")
    result = optimize_real_slider_settings(
        SliderOptimizationInput(
            vehicle_type=sedan,
            year=1913,
            cost_mode="cheap",
        )
    )
    assert result.optimization_disabled
    assert not result.control_settings
    assert not result.predicted_outputs
    assert not wiki_model_available()


def test_wiki_registry_builds_controls_not_screenshot_labels(wiki_model_paths) -> None:
    assert wiki_model_available()
    labels = [slider.label for slider in list_sliders(section="engine")]
    assert "Engine Torque" in labels
    assert labels != list(screenshot_label_sections()["engine"])


def test_registry_contains_only_wiki_controls(wiki_model_paths) -> None:
    sliders = list_sliders()
    assert sliders
    warnings = validate_registry()
    blocking = [warning for warning in warnings if "incorrectly registered" in warning]
    assert not blocking
    for slider in sliders:
        assert not is_output_stat_key(slider.wiki_formula_variable)
        assert slider.wiki_formula_variable.startswith(("Slider_", "Sliders_"))


def test_output_stats_are_not_slider_values(wiki_model_paths) -> None:
    sedan = _vehicle_type("Sedan")
    result = optimize_real_slider_settings(
        SliderOptimizationInput(
            vehicle_type=sedan,
            year=1913,
            cost_mode="cheap",
        )
    )
    control_labels = {item.label.lower() for item in result.control_settings}
    forbidden = {
        "displacement",
        "horsepower",
        "cargo",
        "torque output",
        "power output",
        "overall",
        "driveability",
        "luxury",
    }
    assert forbidden.isdisjoint(control_labels)
    assert result.wiki_model_loaded


def test_optimizer_returns_slider_values_and_predicted_outputs_separately(
    wiki_model_paths,
) -> None:
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
    assert any(item.label == "Torque (lb-ft)" for item in result.predicted_outputs)
    assert any("Formula-model" in item.reason for item in result.control_settings)
    assert result.tradeoffs
    assert result.limitations


def test_same_input_produces_deterministic_output(wiki_model_paths) -> None:
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


def test_all_slider_values_within_expected_ranges(wiki_model_paths) -> None:
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
        if slider.scale == "percent":
            assert 1.0 <= setting.value <= 100.0
        else:
            assert slider.min_value <= setting.value <= slider.max_value


def test_cli_slider_audit_and_optimize_sliders_registered() -> None:
    assert "slider-audit" in SUBCOMMANDS
    assert "formula-effects-audit" in SUBCOMMANDS
    assert "optimize-sliders" in SUBCOMMANDS


def test_cli_optimize_sliders_without_wiki_reports_missing(capsys, missing_wiki_model) -> None:
    exit_code = main(
        [
            "optimize-sliders",
            "--vehicle-type",
            "Sedan",
            "--year",
            "1913",
            "--cost-mode",
            "cheap",
        ]
    )
    assert exit_code == 1
    output = capsys.readouterr().out
    assert "setup-sources" in output.lower()


def test_cli_slider_audit_lists_missing_model_message(capsys, missing_wiki_model) -> None:
    exit_code = main(["slider-audit"])
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "missing" in output.lower() or "setup-sources" in output.lower()
