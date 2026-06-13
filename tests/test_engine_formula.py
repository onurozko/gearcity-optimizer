"""Tests for GearCity engine formula calculations."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from gearcity_optimizer.formulas.engine_formula import (
    EngineFormulaInputs,
    EngineFormulaResult,
    calculate_engine,
    clamp,
    export_engine_candidates_csv,
    load_engine_formula_inputs,
)
from gearcity_optimizer.cli import main

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _base_inputs(**overrides) -> EngineFormulaInputs:
    defaults = {
        "name": "Test Engine",
        "year": 1901,
        "cylinders": 2,
        "displacement": 900.0,
        "bore": None,
        "stroke": None,
        "is_supercharged": False,
        "is_turbocharged": False,
        "has_fuel_injection": False,
        "has_overhead_cam": False,
        "design_performance": 0.30,
        "design_fuel_economy": 0.35,
        "design_dependability": 0.40,
        "design_smoothness": 0.35,
        "design_pace": 0.50,
        "tech_materials": 0.25,
        "tech_components": 0.25,
        "tech_techniques": 0.20,
        "tech_technology": 0.20,
        "fuel_system_quality": 0.30,
        "aspiration_quality": 0.25,
        "layout_weight": 0.30,
        "layout_width": 0.30,
        "layout_length": 0.30,
        "layout_smoothness": 0.30,
        "layout_reliability": 0.35,
        "layout_performance": 0.25,
        "layout_manufacturing": 0.30,
        "layout_design": 0.30,
        "fuel_system_performance": 0.25,
        "fuel_system_fuel_economy": 0.35,
        "fuel_system_reliability": 0.35,
        "aspiration_performance": 0.20,
        "aspiration_fuel_economy": 0.30,
        "aspiration_reliability": 0.35,
        "marque_design_engine_skill": 0.0,
        "pre_research_engine_amount_effect": 0.0,
        "cylinder_bank_arrangement": 1,
    }
    defaults.update(overrides)
    return EngineFormulaInputs(**defaults)


def test_basic_engine_calculation_returns_all_fields():
    """Basic calculation should populate every result field."""
    result = calculate_engine(_base_inputs())

    assert isinstance(result, EngineFormulaResult)
    assert result.horsepower >= 0
    assert result.torque >= 0
    assert 0 <= result.fuel_economy <= 100
    assert 0 <= result.reliability_rating <= 100
    assert 0 <= result.smoothness_rating <= 100
    assert 0 <= result.performance_rating <= 100
    assert 0 <= result.overall_rating <= 100
    assert result.weight > 0
    assert result.width > 0
    assert result.length > 0
    assert result.design_requirements > 0
    assert result.manufacturing_requirements > 0
    assert isinstance(result.warnings, list)


def test_increasing_displacement_increases_torque():
    """Larger displacement should increase torque."""
    low = calculate_engine(_base_inputs(displacement=500.0))
    high = calculate_engine(_base_inputs(displacement=2000.0))
    assert high.torque > low.torque


def test_increasing_performance_focus_increases_horsepower_or_performance_rating():
    """Higher performance focus should improve power output."""
    low = calculate_engine(_base_inputs(design_performance=0.15))
    high = calculate_engine(_base_inputs(design_performance=0.85))
    assert (
        high.horsepower > low.horsepower
        or high.performance_rating > low.performance_rating
    )


def test_increasing_fuel_economy_focus_increases_fuel_economy():
    """Higher fuel economy focus should improve fuel economy rating."""
    low = calculate_engine(_base_inputs(design_fuel_economy=0.15))
    high = calculate_engine(_base_inputs(design_fuel_economy=0.90))
    assert high.fuel_economy > low.fuel_economy


def test_increasing_dependability_focus_increases_reliability_rating():
    """Higher dependability focus should improve reliability rating."""
    low = calculate_engine(_base_inputs(design_dependability=0.15))
    high = calculate_engine(_base_inputs(design_dependability=0.90))
    assert high.reliability_rating > low.reliability_rating


def test_increasing_smoothness_focus_increases_smoothness_rating():
    """Higher smoothness focus should improve smoothness rating."""
    low = calculate_engine(_base_inputs(design_smoothness=0.15))
    high = calculate_engine(_base_inputs(design_smoothness=0.90))
    assert high.smoothness_rating > low.smoothness_rating


def test_increasing_technology_sliders_improves_ratings():
    """Better technology sliders should improve relevant ratings."""
    low = calculate_engine(
        _base_inputs(
            tech_materials=0.10,
            tech_components=0.10,
            tech_technology=0.10,
            tech_techniques=0.10,
        )
    )
    high = calculate_engine(
        _base_inputs(
            tech_materials=0.90,
            tech_components=0.90,
            tech_technology=0.90,
            tech_techniques=0.90,
        )
    )
    assert (
        high.reliability_rating > low.reliability_rating
        or high.smoothness_rating > low.smoothness_rating
        or high.overall_rating > low.overall_rating
    )


def test_overall_rating_is_clamped_to_100():
    """Overall rating should never exceed 100."""
    result = calculate_engine(
        _base_inputs(
            design_performance=1.0,
            design_fuel_economy=1.0,
            design_dependability=1.0,
            design_smoothness=1.0,
            marque_design_engine_skill=100.0,
            pre_research_engine_amount_effect=50.0,
        )
    )
    assert result.overall_rating == 100.0


def test_invalid_slider_above_one_raises_value_error():
    """Slider values above 1.0 should be rejected."""
    with pytest.raises(ValueError, match="design_performance"):
        _base_inputs(design_performance=1.5)


def test_invalid_displacement_raises_value_error():
    """Non-positive displacement should be rejected."""
    with pytest.raises(ValueError, match="displacement"):
        _base_inputs(displacement=0)


def test_csv_loader_loads_sample_engine_formula_inputs():
    """Sample engine design inputs CSV should load successfully."""
    inputs = load_engine_formula_inputs(DATA_DIR / "engine_design_inputs.csv")
    assert len(inputs) >= 6
    assert inputs[0].name == "Tiny Cheap Single Formula"
    assert inputs[0].cylinders == 1


def test_export_creates_package_compatible_csv(tmp_path: Path):
    """Export helper should write package-optimizer-compatible columns."""
    inputs = _base_inputs(name="Export Test")
    output = tmp_path / "engine_candidates_from_formulas.csv"
    export_engine_candidates_csv([inputs], str(output))

    df = pd.read_csv(output)
    expected_columns = {
        "name",
        "horsepower",
        "torque",
        "fuel_economy",
        "reliability",
        "smoothness",
        "overall",
        "unit_cost",
        "design_cost",
        "weight",
        "width",
        "length",
        "notes",
    }
    assert expected_columns.issubset(set(df.columns))
    assert "generated from engine formula" in df.iloc[0]["notes"]


def test_calc_engines_cli_runs_without_crashing(tmp_path: Path):
    """calc-engines CLI should run and optionally export CSV."""
    output = tmp_path / "engine_candidates_from_formulas.csv"
    input_file = DATA_DIR / "engine_design_inputs.csv"
    exit_code = main(
        [
            "calc-engines",
            "--input-file",
            str(input_file),
            "--output-file",
            str(output),
        ]
    )
    assert exit_code == 0
    assert output.exists()


def test_clamp_helper():
    """Clamp helper should bound values."""
    assert clamp(150) == 100
    assert clamp(-5) == 0
    assert clamp(42) == 42
