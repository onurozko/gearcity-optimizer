"""Tests for component priority calculation."""

from gearcity_optimizer.core.component_priorities import (
    calculate_component_priorities,
    format_stat_label,
)
from gearcity_optimizer.core.models import VehicleType
from gearcity_optimizer.core.vehicle_types import load_vehicle_types
from pathlib import Path


def _vehicle_types_path() -> str:
    return str(Path(__file__).resolve().parent.parent / "data" / "vehicle_types.csv")


def _load_type(name: str) -> VehicleType:
    return load_vehicle_types(_vehicle_types_path())[name]


def _top_stats(priorities: dict, component: str, n: int = 5) -> list[str]:
    return [item.stat for item in priorities[component][:n]]


def _priority_rank(priorities: dict, component: str, stat: str) -> int:
    stats = [item.stat for item in priorities[component]]
    return stats.index(stat) + 1


def test_sedan_priorities_favor_strength_fuel_reliability():
    """Sedan should prioritize strength/durability, fuel economy, and reliability."""
    sedan = _load_type("Sedan")
    priorities = calculate_component_priorities(sedan)

    chassis_top = _top_stats(priorities, "chassis", 3)
    assert "strength" in chassis_top or "durability" in chassis_top

    engine_top = _top_stats(priorities, "engine", 3)
    assert "fuel_economy" in engine_top

    gearbox_top = _top_stats(priorities, "gearbox", 3)
    assert "reliability" in gearbox_top or "fuel_economy" in gearbox_top

    design_top = _top_stats(priorities, "vehicle_design", 3)
    assert "safety_focus" in design_top or "testing_fuel" in design_top


def test_pickup_priorities_favor_strength_torque_max_torque():
    """Pickup Truck should prioritize strength, torque, and max torque."""
    pickup = _load_type("Pickup Truck")
    priorities = calculate_component_priorities(pickup)

    chassis_top = _top_stats(priorities, "chassis", 5)
    assert "strength" in chassis_top or "durability" in chassis_top
    assert "durability" in _top_stats(priorities, "chassis", 3)

    engine_top = _top_stats(priorities, "engine", 3)
    assert "torque" in engine_top

    gearbox_top = _top_stats(priorities, "gearbox", 3)
    assert "max_torque" in gearbox_top
    assert "reliability" in gearbox_top


def test_roadster_priorities_favor_performance():
    """Roadster should prioritize chassis performance, horsepower, gearbox performance."""
    roadster = _load_type("Roadster")
    priorities = calculate_component_priorities(roadster)

    chassis_top = _top_stats(priorities, "chassis", 4)
    assert "performance" in chassis_top
    assert "low_weight" in chassis_top

    engine_top = _top_stats(priorities, "engine", 3)
    assert "horsepower" in engine_top

    gearbox_top = _top_stats(priorities, "gearbox", 3)
    assert "performance" in gearbox_top


def test_luxury_sedan_priorities_favor_comfort_smoothness():
    """Luxury Sedan should rank comfort, smoothness, and gearbox comfort highly."""
    luxury_sedan = _load_type("Luxury Sedan")
    priorities = calculate_component_priorities(luxury_sedan)

    assert _priority_rank(priorities, "chassis", "comfort") <= 5
    assert _priority_rank(priorities, "engine", "smoothness") <= 3
    assert _priority_rank(priorities, "gearbox", "comfort") <= 5


def test_format_stat_label_readable():
    """Stat labels should use terminology-aware display labels."""
    assert format_stat_label("engine", "fuel_economy") == "Fuel Economy Rating"
    assert format_stat_label("engine", "reliability") == "Engine Reliability Rating"
    assert format_stat_label("vehicle_design", "testing_fuel") == "Testing: Fuel Economy"
    assert "Durability Rating" in format_stat_label("chassis", "durability")
