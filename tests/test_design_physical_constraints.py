"""Tests for physical fit constraints in design scoring."""

from __future__ import annotations

from gearcity_optimizer.importers.components_xml import parse_components_xml  # noqa: F401
from gearcity_optimizer.core.models import VehicleType
from gearcity_optimizer.formulas.chassis_formula import ChassisFormulaResult
from gearcity_optimizer.formulas.engine_formula import EngineFormulaResult
from gearcity_optimizer.formulas.gearbox_formula import GearboxFormulaResult
from gearcity_optimizer.reports.design_objective import (
    build_design_objective,
    design_score_for_optimization,
    score_complete_design,
)
from gearcity_optimizer.reports.design_physical_constraints import assess_physical_fit
from gearcity_optimizer.reports.slider_optimizer import PredictedOutput


def _sedan() -> VehicleType:
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


def _good_outputs() -> list[PredictedOutput]:
    return [
        PredictedOutput("fuel", "Fuel", 75.0, 0.7, "test", False),
        PredictedOutput("vehicle_overall", "Vehicle overall", 72.0, 0.4, "test", True),
        PredictedOutput("overall", "Overall", 72.0, 0.4, "test", True),
        PredictedOutput("vehicle_dependability", "Dependability", 65.0, 0.5, "test", True),
    ]


def test_torque_mismatch_fails_design():
    assessment = assess_physical_fit(
        engine=EngineFormulaResult(
            horsepower=8000.0,
            torque=22819.0,
            fuel_economy=100.0,
            reliability_rating=0.0,
            smoothness_rating=100.0,
            performance_rating=100.0,
            overall_rating=66.0,
            weight=500.0,
            width=30.0,
            length=40.0,
            design_requirements=50.0,
            manufacturing_requirements=30.0,
            warnings=[],
        ),
        gearbox=GearboxFormulaResult(
            max_torque_support=139.0,
            weight=100.0,
            power_rating=50.0,
            fuel_economy_rating=50.0,
            performance_rating=50.0,
            reliability_rating=50.0,
            comfort_rating=50.0,
            overall_rating=50.0,
            manufacturing_requirements=30.0,
            design_requirements=30.0,
            warnings=[],
        ),
    )
    assert assessment.torque_ok is False
    assert assessment.has_violations
    assert assessment.penalty > 20.0

    objective = build_design_objective(_sedan(), "balanced")
    score = score_complete_design(
        _good_outputs(),
        None,
        None,
        objective,
        vehicle_type=_sedan(),
        engine_result=EngineFormulaResult(
            horsepower=8000.0,
            torque=22819.0,
            fuel_economy=100.0,
            reliability_rating=0.0,
            smoothness_rating=100.0,
            performance_rating=100.0,
            overall_rating=66.0,
            weight=500.0,
            width=30.0,
            length=40.0,
            design_requirements=50.0,
            manufacturing_requirements=30.0,
            warnings=[],
        ),
        gearbox_result=GearboxFormulaResult(
            max_torque_support=139.0,
            weight=100.0,
            power_rating=50.0,
            fuel_economy_rating=50.0,
            performance_rating=50.0,
            reliability_rating=50.0,
            comfort_rating=50.0,
            overall_rating=50.0,
            manufacturing_requirements=30.0,
            design_requirements=30.0,
            warnings=[],
        ),
    )
    assert score.quality_status == "Failed"
    assert "Gearbox torque support" in score.failed_thresholds
    assert score.total_score <= 30.0


def test_engine_bay_oversize_fails_design():
    objective = build_design_objective(_sedan(), "balanced")
    score = score_complete_design(
        _good_outputs(),
        None,
        None,
        objective,
        vehicle_type=_sedan(),
        engine_result=EngineFormulaResult(
            horsepower=100.0,
            torque=200.0,
            fuel_economy=60.0,
            reliability_rating=60.0,
            smoothness_rating=60.0,
            performance_rating=60.0,
            overall_rating=60.0,
            weight=400.0,
            width=50.0,
            length=60.0,
            design_requirements=50.0,
            manufacturing_requirements=30.0,
            warnings=[],
        ),
        chassis_result=ChassisFormulaResult(
            chassis_length=400.0,
            chassis_width=180.0,
            chassis_weight=1000.0,
            max_engine_length=40.0,
            max_engine_width=35.0,
            comfort_rating=50.0,
            performance_rating=50.0,
            strength_rating=50.0,
            durability_rating=50.0,
            overall_rating=50.0,
            design_requirements=40.0,
            manufacturing_requirements=30.0,
            warnings=[],
        ),
        gearbox_result=GearboxFormulaResult(
            max_torque_support=500.0,
            weight=100.0,
            power_rating=50.0,
            fuel_economy_rating=50.0,
            performance_rating=50.0,
            reliability_rating=50.0,
            comfort_rating=50.0,
            overall_rating=50.0,
            manufacturing_requirements=30.0,
            design_requirements=30.0,
            warnings=[],
        ),
    )
    assert score.quality_status == "Failed"
    assert score.physical_fit is not None
    assert score.physical_fit.engine_bay_ok is False


def test_matching_torque_and_bay_passes():
    assessment = assess_physical_fit(
        engine=EngineFormulaResult(
            horsepower=80.0,
            torque=150.0,
            fuel_economy=60.0,
            reliability_rating=60.0,
            smoothness_rating=60.0,
            performance_rating=60.0,
            overall_rating=60.0,
            weight=400.0,
            width=20.0,
            length=25.0,
            design_requirements=50.0,
            manufacturing_requirements=30.0,
            warnings=[],
        ),
        chassis=ChassisFormulaResult(
            chassis_length=400.0,
            chassis_width=180.0,
            chassis_weight=1000.0,
            max_engine_length=40.0,
            max_engine_width=35.0,
            comfort_rating=50.0,
            performance_rating=50.0,
            strength_rating=50.0,
            durability_rating=50.0,
            overall_rating=50.0,
            design_requirements=40.0,
            manufacturing_requirements=30.0,
            warnings=[],
        ),
        gearbox=GearboxFormulaResult(
            max_torque_support=200.0,
            weight=100.0,
            power_rating=50.0,
            fuel_economy_rating=50.0,
            performance_rating=50.0,
            reliability_rating=50.0,
            comfort_rating=50.0,
            overall_rating=50.0,
            manufacturing_requirements=30.0,
            design_requirements=30.0,
            warnings=[],
        ),
    )
    assert assessment.torque_ok is True
    assert assessment.engine_bay_ok is True
    assert not assessment.has_violations


def test_optimization_score_prefers_torque_fit_over_raw_stats():
    objective = build_design_objective(_sedan(), "balanced")
    bad = score_complete_design(
        _good_outputs(),
        None,
        None,
        objective,
        vehicle_type=_sedan(),
        engine_result=EngineFormulaResult(
            horsepower=8000.0,
            torque=22819.0,
            fuel_economy=100.0,
            reliability_rating=0.0,
            smoothness_rating=100.0,
            performance_rating=100.0,
            overall_rating=66.0,
            weight=500.0,
            width=20.0,
            length=25.0,
            design_requirements=50.0,
            manufacturing_requirements=30.0,
            warnings=[],
        ),
        gearbox_result=GearboxFormulaResult(
            max_torque_support=139.0,
            weight=100.0,
            power_rating=50.0,
            fuel_economy_rating=50.0,
            performance_rating=50.0,
            reliability_rating=50.0,
            comfort_rating=50.0,
            overall_rating=50.0,
            manufacturing_requirements=30.0,
            design_requirements=30.0,
            warnings=[],
        ),
    )
    better_margin = score_complete_design(
        _good_outputs(),
        None,
        None,
        objective,
        vehicle_type=_sedan(),
        engine_result=EngineFormulaResult(
            horsepower=80.0,
            torque=180.0,
            fuel_economy=60.0,
            reliability_rating=60.0,
            smoothness_rating=60.0,
            performance_rating=60.0,
            overall_rating=60.0,
            weight=400.0,
            width=20.0,
            length=25.0,
            design_requirements=50.0,
            manufacturing_requirements=30.0,
            warnings=[],
        ),
        gearbox_result=GearboxFormulaResult(
            max_torque_support=200.0,
            weight=100.0,
            power_rating=50.0,
            fuel_economy_rating=50.0,
            performance_rating=50.0,
            reliability_rating=50.0,
            comfort_rating=50.0,
            overall_rating=50.0,
            manufacturing_requirements=30.0,
            design_requirements=30.0,
            warnings=[],
        ),
    )
    assert design_score_for_optimization(better_margin) > design_score_for_optimization(bad)


def test_feasible_design_beats_infeasible_high_stats():
    """Physical fit should dominate hill-climb scoring over raw stat totals."""
    objective = build_design_objective(_sedan(), "balanced")
    good_stats = score_complete_design(
        [
            PredictedOutput("vehicle_overall", "Vehicle overall", 85.0, 0.4, "test", True),
            PredictedOutput("overall", "Overall", 85.0, 0.4, "test", True),
        ],
        None,
        None,
        objective,
        vehicle_type=_sedan(),
        engine_result=EngineFormulaResult(
            horsepower=80.0,
            torque=180.0,
            fuel_economy=60.0,
            reliability_rating=60.0,
            smoothness_rating=60.0,
            performance_rating=60.0,
            overall_rating=60.0,
            weight=400.0,
            width=20.0,
            length=25.0,
            design_requirements=50.0,
            manufacturing_requirements=30.0,
            warnings=[],
        ),
        gearbox_result=GearboxFormulaResult(
            max_torque_support=220.0,
            weight=100.0,
            power_rating=50.0,
            fuel_economy_rating=50.0,
            performance_rating=50.0,
            reliability_rating=50.0,
            comfort_rating=50.0,
            overall_rating=50.0,
            manufacturing_requirements=30.0,
            design_requirements=30.0,
            warnings=[],
        ),
        chassis_result=ChassisFormulaResult(
            comfort_rating=60.0,
            performance_rating=60.0,
            strength_rating=60.0,
            durability_rating=60.0,
            overall_rating=60.0,
            chassis_weight=1000.0,
            chassis_length=400.0,
            chassis_width=180.0,
            max_engine_length=40.0,
            max_engine_width=30.0,
            design_requirements=50.0,
            manufacturing_requirements=30.0,
            warnings=[],
        ),
    )
    flashy_infeasible = score_complete_design(
        [
            PredictedOutput("vehicle_overall", "Vehicle overall", 95.0, 0.4, "test", True),
            PredictedOutput("overall", "Overall", 95.0, 0.4, "test", True),
        ],
        None,
        None,
        objective,
        vehicle_type=_sedan(),
        engine_result=EngineFormulaResult(
            horsepower=8000.0,
            torque=22819.0,
            fuel_economy=100.0,
            reliability_rating=0.0,
            smoothness_rating=100.0,
            performance_rating=100.0,
            overall_rating=95.0,
            weight=500.0,
            width=30.0,
            length=40.0,
            design_requirements=50.0,
            manufacturing_requirements=30.0,
            warnings=[],
        ),
        gearbox_result=GearboxFormulaResult(
            max_torque_support=139.0,
            weight=100.0,
            power_rating=50.0,
            fuel_economy_rating=50.0,
            performance_rating=50.0,
            reliability_rating=50.0,
            comfort_rating=50.0,
            overall_rating=50.0,
            manufacturing_requirements=30.0,
            design_requirements=30.0,
            warnings=[],
        ),
    )
    assert good_stats.physical_fit is not None
    assert not good_stats.physical_fit.has_violations
    assert flashy_infeasible.physical_fit is not None
    assert flashy_infeasible.physical_fit.has_violations
    assert design_score_for_optimization(good_stats) > design_score_for_optimization(flashy_infeasible)
