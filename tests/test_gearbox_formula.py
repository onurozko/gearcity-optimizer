"""Tests for GearCity gearbox formula calculations."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from gearcity_optimizer.formulas.gearbox_formula import (
    GearboxFormulaInputs,
    GearboxFormulaResult,
    calculate_gearbox,
    clamp,
    export_gearbox_candidates_csv,
    load_gearbox_formula_inputs,
)
from gearcity_optimizer.cli import main

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _base_inputs(**overrides) -> GearboxFormulaInputs:
    defaults = {
        "name": "Test Gearbox",
        "year": 1901,
        "number_of_gears": 3,
        "has_limited_slip": False,
        "has_overdrive": False,
        "has_transaxle": False,
        "has_reverse": True,
        "low_gear_ratio": 0.5,
        "high_gear_ratio": 0.5,
        "torque_max_input": 0.35,
        "tech_material": 0.35,
        "tech_components": 0.35,
        "tech_technology": 0.35,
        "tech_techniques": 0.35,
        "design_ease": 0.35,
        "design_dependability": 0.40,
        "design_fuel_economy": 0.35,
        "design_performance": 0.30,
        "subcomponent_weight": 0.35,
        "subcomponent_complexity": 0.35,
        "subcomponent_smoothness": 0.30,
        "subcomponent_ease": 0.35,
        "subcomponent_fuel_rating": 0.35,
        "subcomponent_performance_rating": 0.30,
    }
    defaults.update(overrides)
    return GearboxFormulaInputs(**defaults)


def test_basic_gearbox_calculation_returns_all_fields():
    """Basic calculation should populate every result field."""
    result = calculate_gearbox(_base_inputs())

    assert isinstance(result, GearboxFormulaResult)
    assert result.max_torque_support > 0
    assert result.weight > 0
    assert 0 <= result.power_rating <= 100
    assert 0 <= result.fuel_economy_rating <= 100
    assert 0 <= result.performance_rating <= 100
    assert 0 <= result.reliability_rating <= 100
    assert 0 <= result.comfort_rating <= 100
    assert 0 <= result.overall_rating <= 100
    assert result.manufacturing_requirements > 0
    assert result.design_requirements > 0
    assert isinstance(result.warnings, list)


def test_increasing_torque_max_input_increases_max_torque_support():
    """Higher torque max input slider should raise torque support."""
    low = calculate_gearbox(_base_inputs(torque_max_input=0.2))
    high = calculate_gearbox(_base_inputs(torque_max_input=0.8))
    assert high.max_torque_support > low.max_torque_support


def test_increasing_design_dependability_increases_reliability_rating():
    """Higher dependability focus should improve reliability rating."""
    low = calculate_gearbox(_base_inputs(design_dependability=0.2))
    high = calculate_gearbox(_base_inputs(design_dependability=0.9))
    assert high.reliability_rating > low.reliability_rating


def test_increasing_design_fuel_economy_increases_fuel_rating():
    """Higher fuel economy focus should improve fuel economy rating."""
    low = calculate_gearbox(_base_inputs(design_fuel_economy=0.2))
    high = calculate_gearbox(_base_inputs(design_fuel_economy=0.9))
    assert high.fuel_economy_rating > low.fuel_economy_rating


def test_increasing_design_performance_increases_performance_rating():
    """Higher performance focus should improve performance rating."""
    low = calculate_gearbox(_base_inputs(design_performance=0.2))
    high = calculate_gearbox(_base_inputs(design_performance=0.9))
    assert high.performance_rating > low.performance_rating


def test_increasing_design_ease_increases_comfort_rating():
    """Higher shifting ease focus should improve comfort rating."""
    low = calculate_gearbox(_base_inputs(design_ease=0.2))
    high = calculate_gearbox(_base_inputs(design_ease=0.9))
    assert high.comfort_rating > low.comfort_rating


def test_more_gears_increases_weight():
    """More forward gears should increase gearbox weight."""
    two_gear = calculate_gearbox(_base_inputs(number_of_gears=2))
    four_gear = calculate_gearbox(_base_inputs(number_of_gears=4))
    assert four_gear.weight > two_gear.weight


def test_overall_rating_is_clamped_to_100():
    """Overall rating should never exceed 100."""
    result = calculate_gearbox(
        _base_inputs(
            torque_max_input=1.0,
            design_ease=1.0,
            design_dependability=1.0,
            design_fuel_economy=1.0,
            design_performance=1.0,
            marque_design_gearbox_skill=100.0,
            pre_research_gearbox_amount_effect=50.0,
        )
    )
    assert result.overall_rating == 100.0


def test_invalid_slider_above_one_raises_value_error():
    """Slider values above 1.0 should be rejected."""
    with pytest.raises(ValueError, match="torque_max_input"):
        _base_inputs(torque_max_input=1.5)


def test_csv_loader_loads_sample_gearbox_formula_inputs():
    """Sample gearbox design inputs CSV should load successfully."""
    inputs = load_gearbox_formula_inputs(DATA_DIR / "gearbox_design_inputs.csv")
    assert len(inputs) >= 5
    assert inputs[0].name == "Cheap 2 Speed Formula"
    assert inputs[0].number_of_gears == 2


def test_calc_gearboxes_exports_package_compatible_csv(tmp_path: Path):
    """calc-gearboxes should export gearbox candidates compatible with packages."""
    output = tmp_path / "gearbox_candidates_from_formulas.csv"
    input_file = DATA_DIR / "gearbox_design_inputs.csv"
    exit_code = main(
        [
            "calc-gearboxes",
            "--input-file",
            str(input_file),
            "--output-file",
            str(output),
        ]
    )
    assert exit_code == 0
    assert output.exists()

    df = pd.read_csv(output)
    expected_columns = {
        "name",
        "power",
        "fuel_economy",
        "performance",
        "reliability",
        "comfort",
        "overall",
        "unit_cost",
        "design_cost",
        "max_torque",
        "weight",
        "gears",
        "notes",
    }
    assert expected_columns.issubset(set(df.columns))
    assert "generated from gearbox formula" in df.iloc[0]["notes"]


def test_export_gearbox_candidates_csv_direct(tmp_path: Path):
    """Direct export helper should write expected columns."""
    inputs = _base_inputs(name="Export Test")
    result = calculate_gearbox(inputs)
    output = tmp_path / "exported.csv"
    export_gearbox_candidates_csv([(inputs, result)], str(output))
    df = pd.read_csv(output)
    assert df.iloc[0]["name"] == "Export Test"
    assert df.iloc[0]["max_torque"] == pytest.approx(result.max_torque_support, rel=1e-3)


def test_clamp_helper():
    """Clamp helper should bound values."""
    assert clamp(150) == 100
    assert clamp(-5) == 0
    assert clamp(42) == 42
