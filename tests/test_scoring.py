"""Tests for scoring formulas."""

from gearcity_optimizer.core.models import CandidateDesign, VehicleType
from gearcity_optimizer.core.scoring import (
    calculate_value_score,
    calculate_weighted_buyer_rating_proxy,
)


def _make_vehicle_type(**overrides) -> VehicleType:
    defaults = {
        "name": "Test",
        "performance": 0.4,
        "drivability": 0.4,
        "luxury": 0.45,
        "safety": 0.65,
        "fuel": 0.65,
        "power": 0.45,
        "cargo": 0.5,
        "dependability": 0.45,
        "wealth_demo": 4,
        "military_fleet": False,
        "civilian_fleet": True,
    }
    defaults.update(overrides)
    return VehicleType(**defaults)


def _make_candidate(**overrides) -> CandidateDesign:
    defaults = {
        "name": "Test",
        "vehicle_type": "Sedan",
        "performance": 20.0,
        "drivability": 20.0,
        "luxury": 20.0,
        "safety": 20.0,
        "fuel": 20.0,
        "power": 20.0,
        "cargo": 20.0,
        "dependability": 20.0,
        "quality": 30.0,
        "overall": 25.0,
        "unit_cost": 800.0,
        "design_cost": 15000.0,
    }
    defaults.update(overrides)
    return CandidateDesign(**defaults)


SEDAN = _make_vehicle_type(name="Sedan")
SPORTS = _make_vehicle_type(
    name="Sports",
    performance=0.9,
    drivability=0.85,
    luxury=0.1,
    safety=0.1,
    fuel=0.05,
    power=0.8,
    cargo=0.1,
    dependability=0.35,
    wealth_demo=5,
)
PICKUP = _make_vehicle_type(
    name="Pickup Truck",
    performance=0.4,
    drivability=0.15,
    luxury=0.15,
    safety=0.05,
    fuel=0.05,
    power=0.9,
    cargo=0.95,
    dependability=0.8,
    wealth_demo=3,
    military_fleet=True,
)


def test_sedan_high_safety_fuel_beats_high_performance():
    """Sedan candidate with high safety/fuel should beat high performance only."""
    practical = _make_candidate(
        name="Practical Sedan",
        safety=40,
        fuel=40,
        performance=15,
    )
    sporty = _make_candidate(
        name="Sporty Sedan",
        safety=15,
        fuel=15,
        performance=45,
    )

    practical_score = calculate_weighted_buyer_rating_proxy(practical, SEDAN)
    sporty_score = calculate_weighted_buyer_rating_proxy(sporty, SEDAN)

    assert practical_score > sporty_score


def test_sports_high_performance_beats_high_fuel_cargo():
    """Sports candidate with performance/drivability/power should beat fuel/cargo."""
    performance_focused = _make_candidate(
        name="Performance Sports",
        performance=50,
        drivability=50,
        power=45,
        fuel=10,
        cargo=10,
    )
    economy_focused = _make_candidate(
        name="Economy Sports",
        performance=15,
        drivability=15,
        power=15,
        fuel=45,
        cargo=45,
    )

    perf_score = calculate_weighted_buyer_rating_proxy(performance_focused, SPORTS)
    econ_score = calculate_weighted_buyer_rating_proxy(economy_focused, SPORTS)

    assert perf_score > econ_score


def test_pickup_high_cargo_power_dependability_scores_well():
    """Pickup candidate with cargo/power/dependability should score strongly."""
    workhorse = _make_candidate(
        name="Workhorse",
        cargo=55,
        power=50,
        dependability=50,
        performance=15,
        luxury=8,
    )

    score = calculate_weighted_buyer_rating_proxy(workhorse, PICKUP)
    baseline = calculate_weighted_buyer_rating_proxy(
        _make_candidate(cargo=15, power=15, dependability=15), PICKUP
    )

    assert score > baseline
