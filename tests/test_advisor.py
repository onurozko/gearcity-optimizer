"""Tests for rule-based advisor comments."""

from gearcity_optimizer.reports.advisor import explain_candidate
from gearcity_optimizer.core.models import CandidateDesign, VehicleType
from gearcity_optimizer.core.scoring import calculate_value_score


def test_explain_candidate_includes_fit_and_warnings():
    """Advisor should comment on fit and include penalty warnings."""
    vehicle_type = VehicleType(
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
    candidate = CandidateDesign(
        name="Overbuilt Fancy Sedan",
        vehicle_type="Sedan",
        performance=28,
        drivability=30,
        luxury=55,
        safety=45,
        fuel=25,
        power=30,
        cargo=35,
        dependability=30,
        quality=42,
        overall=44,
        unit_cost=1450,
        design_cost=32000,
        sale_price=2400,
        top_speed_kph=58,
        engine_torque=45,
        gearbox_max_torque=40,
        engine_smoothness=25,
    )
    score = calculate_value_score(candidate, vehicle_type, year=1901)
    comments = explain_candidate(candidate, vehicle_type, score)

    assert any("gearbox" in c.lower() for c in comments)
    assert len(comments) > 0
