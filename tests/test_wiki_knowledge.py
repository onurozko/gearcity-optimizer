"""Tests for wiki-backed slider registry and formula influence parsing."""

from __future__ import annotations

from pathlib import Path

import pytest

from gearcity_optimizer.core.models import VehicleType
from gearcity_optimizer.core.slider_registry import (
    WIKI_LOADED_MESSAGE,
    WIKI_MISSING_WARNING,
    get_outputs_affected_by_slider,
    get_slider_by_variable,
    load_slider_registry,
    registry_status_message,
    wiki_model_available,
)
from gearcity_optimizer.core.vehicle_types import load_vehicle_types
from gearcity_optimizer.core.wiki_variable_classification import is_output_stat_key, is_wiki_output_section
from gearcity_optimizer.importers.wiki_formula_effects import build_formula_effects
from gearcity_optimizer.importers.wiki_knowledge_builder import build_wiki_knowledge
from gearcity_optimizer.importers.wiki_parser import parse_wiki_page
from gearcity_optimizer.importers.wiki_slider_parser import parse_sliders_from_wiki_text
from gearcity_optimizer.reports.slider_optimizer import (
    SliderOptimizationInput,
    optimize_real_slider_settings,
)

FIXTURES = Path(__file__).parent / "fixtures" / "wiki"


def _read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _vehicle_type(name: str) -> VehicleType:
    return load_vehicle_types("data/vehicle_types.csv")[name]


def _parsed_page(name: str, fixture: str) -> dict:
    return parse_wiki_page(name, _read_fixture(fixture), "raw")


def test_slider_registry_built_from_wiki_fixture_not_screenshots(
    wiki_model_paths: Path,
) -> None:
    registry = load_slider_registry()
    assert registry.source_mode == "wiki"
    assert registry.sliders
    assert all(item.source_page.endswith("_game_mechanics") for item in registry.sliders)


def test_engine_slider_parser_extracts_revolutions_and_torque() -> None:
    sliders = parse_sliders_from_wiki_text(
        _read_fixture("engine_sliders_sample.txt"),
        page="engine_game_mechanics",
    )
    variables = {item.formula_variable for item in sliders}
    assert "Slider_Performance_Revolutions" in variables
    assert "Slider_Performance_Torque" in variables


def test_chassis_slider_parser_extracts_fd_length() -> None:
    sliders = parse_sliders_from_wiki_text(
        _read_fixture("chassis_sliders_sample.txt"),
        page="chassis_game_mechanics",
    )
    assert any(item.formula_variable == "Slider_FD_Length" for item in sliders)


def test_gearbox_slider_parser_extracts_torque_max_input() -> None:
    sliders = parse_sliders_from_wiki_text(
        _read_fixture("gearbox_sliders_sample.txt"),
        page="gearbox_game_mechanics",
    )
    assert any(item.formula_variable == "Sliders_Torque_Max_Input" for item in sliders)


def test_vehicle_slider_parser_extracts_testing_fuel_economy() -> None:
    sliders = parse_sliders_from_wiki_text(
        _read_fixture("vehicle_sliders_sample.txt"),
        page="vehicle_game_mechanics",
    )
    assert any(item.formula_variable == "Slider_Testing_FuelEconomy" for item in sliders)


def test_vehicle_demographic_controls_are_dropdowns() -> None:
    sliders = parse_sliders_from_wiki_text(
        _read_fixture("vehicle_sliders_sample.txt"),
        page="vehicle_game_mechanics",
    )
    by_variable = {item.formula_variable: item for item in sliders}
    assert by_variable["Slider_Demographics_Gender"].control_type == "dropdown"
    assert by_variable["Slider_Demographics_Wealth"].control_type == "dropdown"
    assert by_variable["Slider_Demographics_Age"].control_type == "dropdown"
    assert by_variable["Slider_Testing_FuelEconomy"].control_type == "slider"


def test_formula_influence_links_engine_torque_to_performance_torque_slider() -> None:
    parsed_pages = {
        "engine_game_mechanics": _parsed_page(
            "engine_game_mechanics",
            "engine_sliders_sample.txt",
        )
    }
    effects = build_formula_effects(parsed_pages)
    torque_effects = [
        effect
        for effect in effects
        if "Slider_Performance_Torque" in effect.slider_variables
    ]
    assert torque_effects
    assert any("torque" in effect.output_key for effect in torque_effects)


def test_formula_influence_links_gearbox_fuel_rating_to_design_fuel_economy() -> None:
    parsed_pages = {
        "gearbox_game_mechanics": _parsed_page(
            "gearbox_game_mechanics",
            "gearbox_sliders_sample.txt",
        )
    }
    effects = build_formula_effects(parsed_pages)
    fuel_effects = [
        effect
        for effect in effects
        if "Sliders_Design_FuelEconomy" in effect.slider_variables
    ]
    assert fuel_effects
    assert any("fuel" in effect.output_key for effect in fuel_effects)


def test_output_stats_classified_as_outputs_not_controls() -> None:
    outputs = [
        "Horsepower",
        "Displacement",
        "Torque",
        "Cargo Rating",
        "Overall Rating",
        "Fuel Economy Rating",
        "Smoothness",
        "Reliability Rating",
        "Driveability Rating",
    ]
    for title in outputs:
        assert is_wiki_output_section(title)
        assert is_output_stat_key(title.replace(" ", "_").lower())


def test_missing_wiki_model_warns_and_disables_optimizer(missing_wiki_model) -> None:
    registry = load_slider_registry()
    assert registry.source_mode == "missing"
    assert WIKI_MISSING_WARNING in registry.warnings
    assert registry_status_message() == WIKI_MISSING_WARNING
    assert not wiki_model_available()

    sedan = _vehicle_type("Sedan")
    result = optimize_real_slider_settings(
        SliderOptimizationInput(
            vehicle_type=sedan,
            year=1913,
            cost_mode="balanced",
        )
    )
    assert result.optimization_disabled
    assert not result.control_settings


def test_loaded_wiki_model_shows_source_backed_status(wiki_model_paths: Path) -> None:
    assert wiki_model_available()
    assert registry_status_message() == WIKI_LOADED_MESSAGE


def test_optimizer_uses_influence_map_for_reasons(wiki_model_paths: Path) -> None:
    sedan = _vehicle_type("Sedan")
    result = optimize_real_slider_settings(
        SliderOptimizationInput(
            vehicle_type=sedan,
            year=1913,
            cost_mode="balanced",
        )
    )
    reasons = [item.reason for item in result.control_settings]
    assert any("Formula-model" in reason for reason in reasons)


def test_get_outputs_affected_by_slider_uses_loaded_effects(wiki_model_paths: Path) -> None:
    effects = get_outputs_affected_by_slider("Slider_Performance_Torque")
    assert effects

    slider = get_slider_by_variable("Slider_Performance_Torque")
    assert slider is not None
    assert slider.ui_label == "Engine Torque"
