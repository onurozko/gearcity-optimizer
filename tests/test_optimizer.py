"""Tests for candidate ranking."""

from gearcity_optimizer.core.models import CandidateDesign, VehicleType
from gearcity_optimizer.core.optimizer import rank_candidates


def _sedan_type() -> VehicleType:
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


def test_balanced_ranking_prefers_balanced_over_overbuilt():
    """Balanced sedan should rank above overbuilt high-cost sedan."""
    balanced = CandidateDesign(
        name="Balanced Early Sedan",
        vehicle_type="Sedan",
        performance=16,
        drivability=24,
        luxury=16,
        safety=35,
        fuel=40,
        power=20,
        cargo=32,
        dependability=42,
        quality=38,
        overall=36,
        unit_cost=860,
        design_cost=18000,
        sale_price=1300,
        top_speed_kph=52,
        engine_torque=42,
        gearbox_max_torque=60,
        engine_smoothness=36,
    )
    overbuilt = CandidateDesign(
        name="Overbuilt Fancy Sedan",
        vehicle_type="Sedan",
        performance=28,
        drivability=30,
        luxury=55,
        safety=35,
        fuel=20,
        power=32,
        cargo=32,
        dependability=28,
        quality=40,
        overall=42,
        unit_cost=2000,
        design_cost=32000,
        sale_price=4500,
        top_speed_kph=58,
        engine_torque=50,
        gearbox_max_torque=35,
        engine_smoothness=25,
    )

    vehicle_types = {"Sedan": _sedan_type()}
    results = rank_candidates(
        [overbuilt, balanced],
        vehicle_types,
        vehicle_type_name="Sedan",
        year=1901,
        objective="balanced",
    )

    assert results[0]["name"] == "Balanced Early Sedan"
    assert results[1]["name"] == "Overbuilt Fancy Sedan"
