"""Tests for GearCity chassis formula calculations."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from gearcity_optimizer.formulas.chassis_formula import (
    ChassisFormulaInputs,
    ChassisFormulaResult,
    calculate_chassis,
    clamp,
    export_chassis_candidates_csv,
    load_chassis_formula_inputs,
)
from gearcity_optimizer.cli import main

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _base_inputs(**overrides) -> ChassisFormulaInputs:
    defaults = {
        "name": "Test Chassis",
        "year": 1901,
        "fd_length": 0.40,
        "fd_width": 0.35,
        "fd_height": 0.35,
        "fd_weight": 0.40,
        "fd_engine_width": 0.35,
        "fd_engine_length": 0.35,
        "sus_stability": 0.30,
        "sus_comfort": 0.30,
        "sus_performance": 0.25,
        "sus_braking": 0.25,
        "sus_durability": 0.35,
        "design_performance": 0.25,
        "design_control": 0.30,
        "design_strength": 0.40,
        "design_dependability": 0.40,
        "design_pace": 0.50,
        "tech_materials": 0.25,
        "tech_components": 0.25,
        "tech_techniques": 0.20,
        "tech_technology": 0.20,
        "frame_strength": 0.40,
        "frame_safety": 0.30,
        "frame_durability": 0.35,
        "frame_weight": 0.40,
        "frame_design": 0.30,
        "frame_manufacturing": 0.30,
        "frame_cost": 1.0,
        "frame_performance": 0.25,
        "front_suspension_steering": 0.25,
        "front_suspension_braking": 0.25,
        "front_suspension_comfort": 0.25,
        "front_suspension_performance": 0.20,
        "front_suspension_durability": 0.30,
        "front_suspension_manufacturing": 0.30,
        "front_suspension_design": 0.30,
        "front_suspension_cost": 1.0,
        "rear_suspension_braking": 0.25,
        "rear_suspension_steering": 0.25,
        "rear_suspension_performance": 0.20,
        "rear_suspension_comfort": 0.25,
        "rear_suspension_manufacturing": 0.30,
        "rear_suspension_durability": 0.30,
        "rear_suspension_cost": 1.0,
        "rear_suspension_design": 0.30,
        "drivetrain_ride_steering": 0.25,
        "drivetrain_ride_performance": 0.20,
        "drivetrain_durability": 0.35,
        "drivetrain_weight": 0.40,
        "drivetrain_car_performance": 0.20,
        "drivetrain_manufacturing": 0.30,
        "drivetrain_design": 0.30,
        "drivetrain_cost": 1.0,
        "drivetrain_engine_width": 1.0,
        "drivetrain_engine_length": 1.0,
        "marque_design_chassis_skill": 0.0,
        "pre_research_chassis_amount_effect": 0.0,
        "global_lengths": 100.0,
        "global_width": 100.0,
        "global_weight": 100.0,
    }
    defaults.update(overrides)
    return ChassisFormulaInputs(**defaults)


def test_basic_chassis_calculation_returns_all_fields():
    """Basic calculation should populate every result field."""
    result = calculate_chassis(_base_inputs())

    assert isinstance(result, ChassisFormulaResult)
    assert result.chassis_length > 0
    assert result.chassis_width > 0
    assert result.chassis_weight > 0
    assert result.max_engine_length > 0
    assert result.max_engine_width > 0
    assert 0 <= result.comfort_rating <= 100
    assert 0 <= result.performance_rating <= 100
    assert 0 <= result.strength_rating <= 100
    assert 0 <= result.durability_rating <= 100
    assert 0 <= result.overall_rating <= 100
    assert result.design_requirements > 0
    assert result.manufacturing_requirements > 0
    assert isinstance(result.warnings, list)


def test_increasing_fd_length_increases_chassis_length():
    """Higher length slider should increase chassis length."""
    low = calculate_chassis(_base_inputs(fd_length=0.2))
    high = calculate_chassis(_base_inputs(fd_length=0.8))
    assert high.chassis_length > low.chassis_length


def test_increasing_fd_width_increases_chassis_width():
    """Higher width slider should increase chassis width."""
    low = calculate_chassis(_base_inputs(fd_width=0.2))
    high = calculate_chassis(_base_inputs(fd_width=0.8))
    assert high.chassis_width > low.chassis_width


def test_increasing_fd_weight_or_frame_weight_increases_chassis_weight():
    """Heavier frame inputs should increase chassis weight."""
    low_fd = calculate_chassis(_base_inputs(fd_weight=0.2))
    high_fd = calculate_chassis(_base_inputs(fd_weight=0.8))
    assert high_fd.chassis_weight > low_fd.chassis_weight

    low_frame = calculate_chassis(_base_inputs(frame_weight=0.2))
    high_frame = calculate_chassis(_base_inputs(frame_weight=0.8))
    assert high_frame.chassis_weight > low_frame.chassis_weight


def test_increasing_design_strength_or_frame_strength_increases_strength_rating():
    """Strength-focused inputs should raise strength rating."""
    low_design = calculate_chassis(_base_inputs(design_strength=0.2))
    high_design = calculate_chassis(_base_inputs(design_strength=0.9))
    assert high_design.strength_rating > low_design.strength_rating

    low_frame = calculate_chassis(_base_inputs(frame_strength=0.2))
    high_frame = calculate_chassis(_base_inputs(frame_strength=0.9))
    assert high_frame.strength_rating > low_frame.strength_rating


def test_increasing_dependability_or_suspension_durability_increases_durability_rating():
    """Dependability and suspension durability should raise durability rating."""
    low_design = calculate_chassis(_base_inputs(design_dependability=0.2))
    high_design = calculate_chassis(_base_inputs(design_dependability=0.9))
    assert high_design.durability_rating > low_design.durability_rating

    low_sus = calculate_chassis(_base_inputs(sus_durability=0.2))
    high_sus = calculate_chassis(_base_inputs(sus_durability=0.9))
    assert high_sus.durability_rating > low_sus.durability_rating


def test_increasing_performance_inputs_increases_performance_rating():
    """Performance-focused inputs should raise performance rating."""
    low_design = calculate_chassis(_base_inputs(design_performance=0.2))
    high_design = calculate_chassis(_base_inputs(design_performance=0.9))
    assert high_design.performance_rating > low_design.performance_rating

    low_sus = calculate_chassis(_base_inputs(sus_performance=0.2))
    high_sus = calculate_chassis(_base_inputs(sus_performance=0.9))
    assert high_sus.performance_rating > low_sus.performance_rating


def test_increasing_comfort_inputs_increases_comfort_rating():
    """Comfort-related inputs should raise comfort rating."""
    low = calculate_chassis(
        _base_inputs(
            design_control=0.2,
            sus_comfort=0.2,
            front_suspension_comfort=0.2,
            rear_suspension_comfort=0.2,
        )
    )
    high = calculate_chassis(
        _base_inputs(
            design_control=0.9,
            sus_comfort=0.9,
            front_suspension_comfort=0.9,
            rear_suspension_comfort=0.9,
            drivetrain_ride_steering=0.9,
        )
    )
    assert high.comfort_rating > low.comfort_rating


def test_overall_rating_is_clamped_to_100():
    """Overall rating should never exceed 100."""
    result = calculate_chassis(
        _base_inputs(
            design_control=1.0,
            design_performance=1.0,
            design_strength=1.0,
            design_dependability=1.0,
            sus_comfort=1.0,
            sus_performance=1.0,
            marque_design_chassis_skill=100.0,
            pre_research_chassis_amount_effect=50.0,
        )
    )
    assert result.overall_rating == 100.0


def test_invalid_slider_above_one_raises_value_error():
    """Slider values above 1.0 should be rejected."""
    with pytest.raises(ValueError, match="fd_length"):
        _base_inputs(fd_length=1.5)


def test_csv_loader_loads_sample_chassis_formula_inputs():
    """Sample chassis design inputs CSV should load successfully."""
    inputs = load_chassis_formula_inputs(DATA_DIR / "chassis_design_inputs.csv")
    assert len(inputs) >= 5
    assert inputs[0].name == "Cheap Ladder Chassis Formula"
    assert inputs[0].year == 1901


def test_export_creates_package_compatible_csv(tmp_path: Path):
    """Export helper should write package-optimizer-compatible columns."""
    inputs = _base_inputs(name="Export Test")
    output = tmp_path / "chassis_candidates_from_formulas.csv"
    export_chassis_candidates_csv([inputs], str(output))

    df = pd.read_csv(output)
    expected_columns = {
        "name",
        "comfort",
        "performance",
        "strength",
        "durability",
        "overall",
        "unit_cost",
        "design_cost",
        "weight",
        "max_engine_width",
        "max_engine_length",
        "notes",
    }
    assert expected_columns.issubset(set(df.columns))
    assert "generated from chassis formula" in df.iloc[0]["notes"]


def test_calc_chassis_cli_runs_without_crashing(tmp_path: Path):
    """calc-chassis CLI should run and optionally export CSV."""
    output = tmp_path / "chassis_candidates_from_formulas.csv"
    input_file = DATA_DIR / "chassis_design_inputs.csv"
    exit_code = main(
        [
            "calc-chassis",
            "--input-file",
            str(input_file),
            "--output-file",
            str(output),
        ]
    )
    assert exit_code == 0
    assert output.exists()
