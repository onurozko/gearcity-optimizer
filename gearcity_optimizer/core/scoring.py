"""Deterministic scoring formulas for vehicle type fit and buyer rating proxy."""

from __future__ import annotations

from gearcity_optimizer.core.models import (
    RATING_ATTRIBUTES,
    CandidateDesign,
    ScoreResult,
    VehicleType,
)
from gearcity_optimizer.core.penalties import apply_penalties


def calculate_vehicle_type_fit(
    candidate: CandidateDesign,
    vehicle_type: VehicleType,
) -> float:
    """
    Compute normalized vehicle type fit (0–100).

    Weighted dot product of candidate ratings and vehicle type importance weights,
    normalized against the theoretical maximum score.
    """
    raw_score = sum(
        getattr(candidate, attr) * getattr(vehicle_type, attr)
        for attr in RATING_ATTRIBUTES
    )
    max_score = 100 * sum(getattr(vehicle_type, attr) for attr in RATING_ATTRIBUTES)

    if max_score == 0:
        return 0.0

    return 100 * raw_score / max_score


def calculate_weighted_buyer_rating_proxy(
    candidate: CandidateDesign,
    vehicle_type: VehicleType,
    year: int = 1901,
    city_fuel_rate: float = 0.0,
    global_fuel_rate: float = 1.0,
) -> float:
    """
    Compute a practical buyer-rating proxy focused on vehicle design choices.

    Does not include company image, staffing, dealerships, or buyer pool effects.
    """
    fuel_multiplier = (
        (1 + vehicle_type.fuel)
        * (1 + city_fuel_rate)
        * (global_fuel_rate**2)
        * 5
    )

    score = (
        candidate.cargo * (1 + vehicle_type.cargo) * 5
        + candidate.dependability * (1 + vehicle_type.dependability) * 5
        + candidate.drivability * (1 + vehicle_type.drivability) * 5
        + candidate.fuel * fuel_multiplier
        + candidate.luxury * (1 + vehicle_type.luxury) * 5
        + candidate.performance * (1 + vehicle_type.performance) * 5
        + candidate.power * (1 + vehicle_type.power) * 5
        + candidate.quality * 8 * 5
        + candidate.safety * (1 + vehicle_type.safety) * 5
        + candidate.overall * 25
    )

    return score


def calculate_value_score(
    candidate: CandidateDesign,
    vehicle_type: VehicleType,
    year: int = 1901,
) -> ScoreResult:
    """Compute full score result including penalties and value per cost."""
    vehicle_type_fit = calculate_vehicle_type_fit(candidate, vehicle_type)
    buyer_rating_proxy_before_penalties = calculate_weighted_buyer_rating_proxy(
        candidate, vehicle_type, year=year
    )
    penalty_multiplier, warnings = apply_penalties(candidate, vehicle_type, year)
    final_buyer_rating_proxy = (
        buyer_rating_proxy_before_penalties * penalty_multiplier
    )
    value_per_cost = (
        final_buyer_rating_proxy / candidate.unit_cost
        if candidate.unit_cost > 0
        else 0.0
    )

    return ScoreResult(
        vehicle_type_fit=vehicle_type_fit,
        buyer_rating_proxy_before_penalties=buyer_rating_proxy_before_penalties,
        final_buyer_rating_proxy=final_buyer_rating_proxy,
        value_per_cost=value_per_cost,
        penalty_multiplier=penalty_multiplier,
        warnings=warnings,
    )
