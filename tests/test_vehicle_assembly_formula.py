"""Tests for vehicle assembly formula module."""

from __future__ import annotations

from gearcity_optimizer.core.component_models import (
    ChassisCandidate,
    EngineCandidate,
    GearboxCandidate,
)
from gearcity_optimizer.formulas.vehicle_assembly_formula import (
    ComponentAssemblyInput,
    assemble_and_score_package,
    assemble_vehicle_ratings,
    calculate_vehicle_type_fit,
)
from gearcity_optimizer.core.vehicle_types import load_vehicle_types
from pathlib import Path


def _data_path(filename: str) -> str:
    return str(Path(__file__).resolve().parent.parent / "data" / filename)


def test_assemble_vehicle_ratings_returns_all_fields():
    """Assembly should populate all vehicle rating fields."""
    components = ComponentAssemblyInput(
        chassis=ChassisCandidate(
            name="C",
            comfort=30,
            performance=35,
            strength=40,
            durability=36,
            overall=34,
            unit_cost=0,
        ),
        engine=EngineCandidate(
            name="E",
            horsepower=14,
            torque=42,
            fuel_economy=38,
            reliability=42,
            smoothness=34,
            overall=36,
            unit_cost=0,
        ),
        gearbox=GearboxCandidate(
            name="G",
            power=26,
            fuel_economy=37,
            performance=34,
            reliability=54,
            comfort=37,
            overall=32,
            unit_cost=0,
            max_torque=88,
        ),
    )
    ratings = assemble_vehicle_ratings(components)
    assert 0 <= ratings.performance <= 100
    assert 0 <= ratings.fuel <= 100
    assert 0 <= ratings.overall <= 100
    assert ratings.dependability > 0


def test_assemble_and_score_package_returns_fit_and_buyer_proxy():
    """Assembly scoring should return fit and partial buyer-rating proxy."""
    sedan = load_vehicle_types(_data_path("vehicle_types.csv"))["Sedan"]
    components = ComponentAssemblyInput(
        chassis=ChassisCandidate(
            name="C", comfort=30, performance=35, strength=40, durability=36,
            overall=34, unit_cost=300,
        ),
        engine=EngineCandidate(
            name="E", horsepower=14, torque=42, fuel_economy=38, reliability=42,
            smoothness=34, overall=36, unit_cost=340,
        ),
        gearbox=GearboxCandidate(
            name="G", power=26, fuel_economy=37, performance=34, reliability=54,
            comfort=37, overall=32, unit_cost=340, max_torque=88,
        ),
    )
    ratings, fit, buyer_proxy = assemble_and_score_package(components, sedan, year=1901)
    assert fit == calculate_vehicle_type_fit(ratings, sedan)
    assert buyer_proxy > 0
