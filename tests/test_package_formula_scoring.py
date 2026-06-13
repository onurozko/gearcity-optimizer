"""Tests for formula-first package scoring (no name-based heuristics)."""

from __future__ import annotations

from pathlib import Path

import pytest

from gearcity_optimizer.reports.advisor import explain_package
from gearcity_optimizer.core.component_models import (
    ChassisCandidate,
    EngineCandidate,
    GearboxCandidate,
)
from gearcity_optimizer.core.component_optimizer import (
    COMPONENT_FORMULA_OBJECTIVES,
    PACKAGE_OBJECTIVES,
    rank_component_packages,
    score_chassis_for_vehicle_type,
)
from gearcity_optimizer.formulas.vehicle_assembly_formula import (
    ComponentAssemblyInput,
    assemble_vehicle_ratings,
    calculate_final_formula_fit_score,
)
from gearcity_optimizer.core.vehicle_types import load_vehicle_types


def _data_path(filename: str) -> str:
    return str(Path(__file__).resolve().parent.parent / "data" / filename)


def _sedan():
    return load_vehicle_types(_data_path("vehicle_types.csv"))["Sedan"]


def _chassis(**kwargs) -> ChassisCandidate:
    defaults = {
        "name": "Test Chassis",
        "comfort": 30.0,
        "performance": 35.0,
        "strength": 38.0,
        "durability": 36.0,
        "overall": 34.0,
        "unit_cost": 0.0,
        "weight": 165.0,
        "max_engine_width": 30.0,
        "max_engine_length": 38.0,
    }
    defaults.update(kwargs)
    return ChassisCandidate(**defaults)


def _engine(**kwargs) -> EngineCandidate:
    defaults = {
        "name": "Test Engine",
        "horsepower": 14.0,
        "torque": 42.0,
        "fuel_economy": 38.0,
        "reliability": 42.0,
        "smoothness": 34.0,
        "overall": 36.0,
        "unit_cost": 0.0,
        "weight": 150.0,
        "width": 22.0,
        "length": 28.0,
    }
    defaults.update(kwargs)
    return EngineCandidate(**defaults)


def _gearbox(**kwargs) -> GearboxCandidate:
    defaults = {
        "name": "Test Gearbox",
        "power": 26.0,
        "fuel_economy": 37.0,
        "performance": 34.0,
        "reliability": 54.0,
        "comfort": 37.0,
        "overall": 32.0,
        "unit_cost": 0.0,
        "max_torque": 88.0,
        "weight": 166.0,
        "gears": 3,
    }
    defaults.update(kwargs)
    return GearboxCandidate(**defaults)


def test_formula_objectives_are_available():
    """Formula-backed objectives should be registered."""
    for objective in (
        "component_fit",
        "formula_fit",
        "formula_value",
        "formula_balanced",
    ):
        assert objective in PACKAGE_OBJECTIVES
    assert COMPONENT_FORMULA_OBJECTIVES == frozenset(
        {"component_fit", "formula_fit", "formula_value", "formula_balanced"}
    )


def test_formula_fit_ranks_by_assembly_vehicle_type_fit_primarily():
    """formula_fit should prefer higher assembly fit over higher component fit."""
    sedan = _sedan()

    sporty_chassis = _chassis(
        name="Sporty",
        performance=38.38,
        strength=29.91,
        durability=29.75,
        comfort=32.9,
        overall=27.19,
        weight=129.0,
    )
    workhorse_chassis = _chassis(
        name="Workhorse",
        performance=11.07,
        strength=42.49,
        durability=38.25,
        comfort=28.56,
        overall=24.07,
        weight=197.0,
    )
    luxury_engine = _engine(
        name="Luxury",
        horsepower=15.0,
        torque=78.4,
        fuel_economy=4.85,
        reliability=44.61,
        smoothness=59.78,
        overall=27.07,
        weight=224.0,
    )
    sport_gearbox = _gearbox(
        name="Sport GB",
        performance=52.65,
        fuel_economy=31.1,
        reliability=50.0,
        comfort=45.0,
        overall=36.94,
        max_torque=108.84,
        weight=164.5,
    )

    packages = rank_component_packages(
        [sporty_chassis, workhorse_chassis],
        [luxury_engine],
        [sport_gearbox],
        sedan,
        objective="formula_fit",
        top=2,
    )
    sporty_pkg = next(p for p in packages if p.chassis_name == "Sporty")
    workhorse_pkg = next(p for p in packages if p.chassis_name == "Workhorse")

    assert sporty_pkg.component_package_score > workhorse_pkg.component_package_score
    assert workhorse_pkg.assembly_vehicle_type_fit > sporty_pkg.assembly_vehicle_type_fit
    assert workhorse_pkg.final_formula_fit_score > sporty_pkg.final_formula_fit_score
    assert packages[0].chassis_name == "Workhorse"
    assert packages[0].package_score == pytest.approx(packages[0].final_formula_fit_score)


def test_component_fit_still_ranks_by_component_package_score():
    """component_fit should sort by weighted component fits."""
    sedan = _sedan()
    low = rank_component_packages(
        [_chassis(performance=20.0)],
        [_engine()],
        [_gearbox()],
        sedan,
        objective="component_fit",
        top=1,
    )[0]
    high = rank_component_packages(
        [_chassis(performance=55.0)],
        [_engine()],
        [_gearbox()],
        sedan,
        objective="component_fit",
        top=1,
    )[0]
    assert high.component_package_score > low.component_package_score
    assert high.package_score == pytest.approx(high.component_package_score)


def test_formula_value_uses_cost_after_formula_score():
    """formula_value should rank by value without changing formula fit scores."""
    sedan = _sedan()
    cheap = rank_component_packages(
        [_chassis(unit_cost=200.0)],
        [_engine(unit_cost=200.0)],
        [_gearbox(unit_cost=200.0)],
        sedan,
        objective="formula_value",
        top=1,
    )[0]
    expensive = rank_component_packages(
        [_chassis(unit_cost=2000.0)],
        [_engine(unit_cost=2000.0)],
        [_gearbox(unit_cost=2000.0)],
        sedan,
        objective="formula_value",
        top=1,
    )[0]

    assert cheap.final_formula_fit_score == pytest.approx(
        expensive.final_formula_fit_score, rel=1e-6
    )
    assert cheap.package_value_score > expensive.package_value_score


def test_formula_balanced_combines_normalized_fit_and_value():
    """formula_balanced should blend normalized formula fit and value."""
    sedan = _sedan()
    packages = rank_component_packages(
        [
            _chassis(unit_cost=100.0),
            _chassis(unit_cost=5000.0, performance=55.0),
        ],
        [_engine(unit_cost=100.0), _engine(unit_cost=5000.0, horsepower=40.0)],
        [_gearbox(unit_cost=100.0), _gearbox(unit_cost=5000.0, performance=50.0)],
        sedan,
        objective="formula_balanced",
        top=4,
    )
    assert len(packages) == 4
    assert all(0 <= p.package_score <= 1.0 for p in packages)


def test_debug_output_includes_component_and_assembly_scores():
    """Package debug should expose both component and assembly scores."""
    sedan = _sedan()
    package = rank_component_packages(
        [_chassis()],
        [_engine()],
        [_gearbox()],
        sedan,
        objective="formula_fit",
        top=1,
    )[0]
    assert package.fit_debug is not None
    assert "component_package_score" in package.fit_debug
    assert "assembly_vehicle_type_fit" in package.fit_debug
    assert package.final_formula_fit_score is not None


def test_advisor_comments_for_formula_fit_mention_assembly_weaknesses():
    """Advisor should comment on assembly weaknesses for important vehicle stats."""
    sedan = _sedan()
    package = rank_component_packages(
        [
            _chassis(
                performance=55.0,
                strength=20.0,
                durability=20.0,
                comfort=20.0,
            )
        ],
        [_engine(fuel_economy=5.0, horsepower=50.0)],
        [_gearbox(fuel_economy=5.0, performance=50.0)],
        sedan,
        objective="formula_fit",
        top=1,
    )[0]
    comments = explain_package(package, sedan)
    joined = " ".join(comments).lower()
    assert "assembly" in joined
    assert "fuel" in joined or "safety" in joined


def test_package_scoring_is_deterministic():
    """Repeated scoring with the same inputs should match exactly."""
    sedan = _sedan()
    kwargs = dict(
        chassis_list=[_chassis()],
        engine_list=[_engine()],
        gearbox_list=[_gearbox()],
        vehicle_type=sedan,
        objective="formula_fit",
        top=1,
    )
    first = rank_component_packages(**kwargs)
    second = rank_component_packages(**kwargs)
    assert first[0].package_score == second[0].package_score


def test_identical_stats_same_score_regardless_of_name():
    """Component names must not affect formula_fit package score."""
    sedan = _sedan()
    roadster_named = _chassis(name="Sporty Roadster Chassis Formula", performance=38.0)
    sedan_named = _chassis(name="Balanced Sedan Chassis Formula", performance=38.0)
    engine = _engine()
    gearbox = _gearbox()

    roadster_pkg = rank_component_packages(
        [roadster_named], [engine], [gearbox], sedan, objective="formula_fit", top=1
    )[0]
    sedan_pkg = rank_component_packages(
        [sedan_named], [engine], [gearbox], sedan, objective="formula_fit", top=1
    )[0]

    assert roadster_pkg.final_formula_fit_score == pytest.approx(
        sedan_pkg.final_formula_fit_score
    )


def test_formula_outputs_not_modified_by_package_scoring():
    """Scoring must read component stats without mutating candidates."""
    sedan = _sedan()
    chassis = _chassis(performance=41.0)
    engine = _engine(horsepower=18.0)
    gearbox = _gearbox(performance=40.0)

    before = (
        chassis.performance,
        engine.horsepower,
        gearbox.performance,
        chassis.overall,
        engine.overall,
        gearbox.overall,
    )

    rank_component_packages(
        [chassis], [engine], [gearbox], sedan, objective="formula_fit", top=1
    )

    after = (
        chassis.performance,
        engine.horsepower,
        gearbox.performance,
        chassis.overall,
        engine.overall,
        gearbox.overall,
    )
    assert before == after


def test_chassis_scoring_does_not_read_notes():
    """Component scoring functions should not use notes fields."""
    sedan = _sedan()
    with_notes = _chassis(notes="sporty roadster performance focused")
    without_notes = _chassis(notes=None)
    assert (
        score_chassis_for_vehicle_type(with_notes, sedan, formula_fit=True).fit_score
        == score_chassis_for_vehicle_type(without_notes, sedan, formula_fit=True).fit_score
    )


def test_calculate_final_formula_fit_score_weights_assembly_dominant():
    """Final formula fit score should weight assembly vehicle type fit highest."""
    score = calculate_final_formula_fit_score(
        assembly_vehicle_type_fit=40.0,
        assembly_overall=30.0,
        assembly_quality=25.0,
    )
    assert score == pytest.approx(0.80 * 40 + 0.10 * 30 + 0.10 * 25)


def test_assemble_vehicle_ratings_uses_component_stats_only():
    """Vehicle assembly should depend on numeric stats, not names."""
    stats = dict(
        comfort=30.0,
        performance=35.0,
        strength=38.0,
        durability=36.0,
        overall=34.0,
        unit_cost=0.0,
        weight=165.0,
        max_engine_width=30.0,
        max_engine_length=38.0,
    )
    a = assemble_vehicle_ratings(
        ComponentAssemblyInput(
            _chassis(name="Roadster Name", **stats),
            _engine(name="Sport Name"),
            _gearbox(name="Sport Gearbox"),
        )
    )
    b = assemble_vehicle_ratings(
        ComponentAssemblyInput(
            _chassis(name="Sedan Name", **stats),
            _engine(name="Sedan Name"),
            _gearbox(name="Sedan Gearbox"),
        )
    )
    assert a.performance == pytest.approx(b.performance)
    assert a.overall == pytest.approx(b.overall)
