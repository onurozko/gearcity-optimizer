"""Tests for component package scoring and ranking."""

from pathlib import Path

from gearcity_optimizer.core.component_models import (
    ChassisCandidate,
    EngineCandidate,
    GearboxCandidate,
    load_chassis_candidates,
    load_engine_candidates,
    load_gearbox_candidates,
)
from gearcity_optimizer.core.component_optimizer import (
    rank_component_packages,
    score_gearbox_for_vehicle_type,
)
from gearcity_optimizer.core.vehicle_types import load_vehicle_types


def _data_path(filename: str) -> str:
    return str(Path(__file__).resolve().parent.parent / "data" / filename)


def _load_type(name: str):
    return load_vehicle_types(_data_path("vehicle_types.csv"))[name]


def test_gearbox_torque_warning_penalizes_but_does_not_skip():
    """Torque mismatch should warn and penalize without excluding the package."""
    pickup = _load_type("Pickup Truck")
    chassis = load_chassis_candidates(_data_path("chassis_candidates.csv"))
    engines = load_engine_candidates(_data_path("engine_candidates.csv"))
    gearboxes = load_gearbox_candidates(_data_path("gearbox_candidates.csv"))

    work_engine = next(e for e in engines if e.name == "Torquey Work Engine")
    weak_gearbox = GearboxCandidate(
        name="Weak Test Gearbox",
        power=20,
        fuel_economy=20,
        performance=20,
        reliability=30,
        comfort=20,
        overall=25,
        unit_cost=100,
        max_torque=50,
    )

    result = score_gearbox_for_vehicle_type(
        weak_gearbox, pickup, engine=work_engine
    )
    assert result.fit_score < 30
    assert any("torque" in w.lower() for w in result.warnings)

    packages = rank_component_packages(
        chassis_list=chassis[:1],
        engine_list=[work_engine],
        gearbox_list=[weak_gearbox],
        vehicle_type=pickup,
        objective="best_fit",
        top=5,
    )
    assert len(packages) == 1
    assert packages[0].warnings


def test_engine_fit_constraint_skips_oversized_engine():
    """Packages with engines too large for the chassis should be skipped."""
    sedan = _load_type("Sedan")
    small_chassis = ChassisCandidate(
        name="Tiny Chassis",
        comfort=20,
        performance=20,
        strength=20,
        durability=20,
        overall=25,
        unit_cost=200,
        max_engine_width=20,
        max_engine_length=20,
    )
    large_engine = EngineCandidate(
        name="Huge Engine",
        horsepower=30,
        torque=60,
        fuel_economy=20,
        reliability=30,
        smoothness=20,
        overall=30,
        unit_cost=400,
        width=30,
        length=30,
    )
    gearbox = GearboxCandidate(
        name="Test Gearbox",
        power=30,
        fuel_economy=30,
        performance=30,
        reliability=30,
        comfort=30,
        overall=30,
        unit_cost=100,
        max_torque=80,
    )

    packages = rank_component_packages(
        chassis_list=[small_chassis],
        engine_list=[large_engine],
        gearbox_list=[gearbox],
        vehicle_type=sedan,
        objective="best_fit",
        top=5,
    )
    assert packages == []


def test_pickup_package_ranks_workhorse_combo_high():
    """Pickup Truck should rank workhorse chassis + torque engine + heavy gearbox high."""
    pickup = _load_type("Pickup Truck")
    chassis = load_chassis_candidates(_data_path("chassis_candidates.csv"))
    engines = load_engine_candidates(_data_path("engine_candidates.csv"))
    gearboxes = load_gearbox_candidates(_data_path("gearbox_candidates.csv"))

    packages = rank_component_packages(
        chassis_list=chassis,
        engine_list=engines,
        gearbox_list=gearboxes,
        vehicle_type=pickup,
        objective="balanced",
        top=10,
    )

    top_names = {
        (p.chassis_name, p.engine_name, p.gearbox_name) for p in packages[:3]
    }
    assert (
        "Workhorse Truck Chassis",
        "Torquey Work Engine",
        "Heavy Duty 3 Speed",
    ) in top_names


def test_phaeton_prefers_cheap_fuel_focused_components():
    """Phaeton should favor cheap, fuel-focused packages over sporty luxury."""
    phaeton = _load_type("Phaeton")
    chassis = load_chassis_candidates(_data_path("chassis_candidates.csv"))
    engines = load_engine_candidates(_data_path("engine_candidates.csv"))
    gearboxes = load_gearbox_candidates(_data_path("gearbox_candidates.csv"))

    packages = rank_component_packages(
        chassis_list=chassis,
        engine_list=engines,
        gearbox_list=gearboxes,
        vehicle_type=phaeton,
        objective="value",
        top=5,
    )

    top_package = packages[0]
    assert top_package.total_unit_cost <= 1100
    assert top_package.chassis_name in {
        "Light Phaeton Chassis",
        "Cheap Ladder Chassis",
    }
    assert top_package.engine_name in {
        "Tiny Cheap Single",
        "Efficient Reliable Engine",
        "Balanced Early Two",
    }
