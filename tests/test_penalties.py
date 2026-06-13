"""Tests for penalty rules."""

from gearcity_optimizer.core.models import CandidateDesign, VehicleType
from gearcity_optimizer.core.penalties import apply_penalties


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


def test_gearbox_torque_mismatch_penalty():
    """Engine torque above gearbox max should reduce multiplier and warn."""
    candidate = _make_candidate(engine_torque=80, gearbox_max_torque=50)
    vehicle_type = _make_vehicle_type()

    multiplier, warnings = apply_penalties(candidate, vehicle_type, year=1901)

    assert multiplier < 1.0
    assert any("gearbox" in w.lower() for w in warnings)


def test_top_speed_penalty_for_slow_sports_car():
    """A very slow sports car should receive top speed warning and penalty."""
    candidate = _make_candidate(top_speed_kph=10)
    sports = _make_vehicle_type(
        name="Sports",
        performance=0.9,
        drivability=0.85,
        luxury=0.1,
        safety=0.1,
        fuel=0.05,
        power=0.8,
        cargo=0.1,
        dependability=0.35,
    )

    multiplier, warnings = apply_penalties(candidate, sports, year=1901)

    assert multiplier < 1.0
    assert any("top speed" in w.lower() for w in warnings)


def test_luxury_smoothness_penalty():
    """Luxury sedan with low engine smoothness should be penalized."""
    candidate = _make_candidate(engine_smoothness=10)
    luxury_sedan = _make_vehicle_type(
        name="Luxury Sedan",
        luxury=0.9,
        performance=0.55,
        drivability=0.5,
        safety=0.75,
        fuel=0.35,
        power=0.6,
        cargo=0.68,
        dependability=0.7,
        wealth_demo=6,
    )

    multiplier, warnings = apply_penalties(candidate, luxury_sedan, year=1901)

    assert multiplier < 1.0
    assert any("smoothness" in w.lower() for w in warnings)


def test_price_gouging_penalty():
    """Absurd sale price relative to unit cost should trigger penalty."""
    candidate = _make_candidate(unit_cost=500, sale_price=10000)
    vehicle_type = _make_vehicle_type(wealth_demo=1)

    multiplier, warnings = apply_penalties(candidate, vehicle_type, year=1901)

    assert multiplier < 1.0
    assert any("sale price" in w.lower() for w in warnings)
