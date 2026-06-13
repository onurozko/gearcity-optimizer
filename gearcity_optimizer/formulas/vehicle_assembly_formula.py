"""Vehicle assembly formulas: combine component stats into vehicle ratings.

Uses GearCity Wiki buyer-rating structure (dynamic_reports) as reference.
Component-to-vehicle mapping is an approximation until full body/design sliders exist.
"""

from __future__ import annotations

from dataclasses import dataclass

from gearcity_optimizer.core.component_models import (
    ChassisCandidate,
    EngineCandidate,
    GearboxCandidate,
)
from gearcity_optimizer.core.models import RATING_ATTRIBUTES, VehicleType


def clamp(value: float, min_value: float = 0.0, max_value: float = 100.0) -> float:
    """Clamp a numeric value to an inclusive range."""
    return max(min_value, min(max_value, value))


def scale_horsepower_to_rating(horsepower: float) -> float:
    """Map raw horsepower to a 0–100 rating scale for assembly weighting."""
    return clamp(horsepower / 0.5)


def scale_torque_to_rating(torque: float) -> float:
    """Map raw torque (lb-ft) to a 0–100 rating scale for assembly weighting."""
    return clamp(torque / 1.2)


def scale_max_torque_to_rating(max_torque: float) -> float:
    """Map gearbox max torque (lb-ft) to a 0–100 rating scale."""
    return clamp(max_torque / 1.5)


@dataclass
class ComponentAssemblyInput:
    """Chassis, engine, and gearbox candidates for assembly."""

    chassis: ChassisCandidate
    engine: EngineCandidate
    gearbox: GearboxCandidate


@dataclass
class VehicleAssemblyRatings:
    """Proxy finished-vehicle ratings derived from component formula outputs."""

    performance: float
    drivability: float
    luxury: float
    safety: float
    fuel: float
    power: float
    cargo: float
    dependability: float
    quality: float
    overall: float


def assemble_vehicle_ratings(components: ComponentAssemblyInput) -> VehicleAssemblyRatings:
    """
    Approximate finished-vehicle ratings from component stats.

    TODO: replace with full vehicle body/design slider formulas when available.
    """
    chassis = components.chassis
    engine = components.engine
    gearbox = components.gearbox

    hp_rating = scale_horsepower_to_rating(engine.horsepower)
    torque_rating = scale_torque_to_rating(engine.torque)
    max_torque_rating = (
        scale_max_torque_to_rating(gearbox.max_torque)
        if gearbox.max_torque is not None
        else torque_rating
    )

    performance = clamp(
        0.30 * chassis.performance
        + 0.35 * hp_rating
        + 0.20 * torque_rating
        + 0.15 * gearbox.performance
    )
    drivability = clamp(
        0.35 * chassis.comfort
        + 0.35 * engine.smoothness
        + 0.30 * gearbox.comfort
    )
    luxury = clamp(
        0.30 * chassis.comfort
        + 0.50 * engine.smoothness
        + 0.20 * gearbox.comfort
    )
    safety = clamp(0.70 * chassis.strength + 0.30 * chassis.durability)
    fuel = clamp(
        0.45 * engine.fuel_economy
        + 0.45 * gearbox.fuel_economy
        + 0.10 * (100.0 - min(100.0, (chassis.weight or 150.0) / 3.0))
    )
    power = clamp(
        0.40 * torque_rating
        + 0.35 * hp_rating
        + 0.25 * max_torque_rating
    )
    cargo = clamp(0.55 * chassis.strength + 0.45 * chassis.durability)
    dependability = clamp(
        0.30 * chassis.durability
        + 0.35 * engine.reliability
        + 0.35 * gearbox.reliability
    )
    quality = clamp(
        (chassis.overall + engine.overall + gearbox.overall) / 3.0
    )
    overall = clamp(
        0.35 * chassis.overall
        + 0.40 * engine.overall
        + 0.25 * gearbox.overall
    )

    return VehicleAssemblyRatings(
        performance=performance,
        drivability=drivability,
        luxury=luxury,
        safety=safety,
        fuel=fuel,
        power=power,
        cargo=cargo,
        dependability=dependability,
        quality=quality,
        overall=overall,
    )


def calculate_vehicle_type_fit(
    ratings: VehicleAssemblyRatings,
    vehicle_type: VehicleType,
) -> float:
    """Vehicle type fit from assembled ratings (same structure as finished designs)."""
    raw_score = sum(
        getattr(ratings, attr) * getattr(vehicle_type, attr)
        for attr in RATING_ATTRIBUTES
    )
    max_score = 100 * sum(getattr(vehicle_type, attr) for attr in RATING_ATTRIBUTES)
    if max_score == 0:
        return 0.0
    return 100 * raw_score / max_score


def calculate_partial_buyer_rating_proxy(
    ratings: VehicleAssemblyRatings,
    vehicle_type: VehicleType,
    year: int = 1901,
    city_fuel_rate: float = 0.0,
    global_fuel_rate: float = 1.0,
) -> float:
    """
    Buyer-rating proxy from wiki dynamic_reports vehicle-rating rows only.

    Excludes company image, branch staffing, marketing, penalties, and pricing.
    """
    fuel_multiplier = (
        (1 + vehicle_type.fuel)
        * (1 + city_fuel_rate)
        * (global_fuel_rate**2)
        * 5
    )

    return (
        ratings.cargo * (1 + vehicle_type.cargo) * 5
        + ratings.dependability * (1 + vehicle_type.dependability) * 5
        + ratings.drivability * (1 + vehicle_type.drivability) * 5
        + ratings.fuel * fuel_multiplier
        + ratings.luxury * (1 + vehicle_type.luxury) * 5
        + ratings.performance * (1 + vehicle_type.performance) * 5
        + ratings.power * (1 + vehicle_type.power) * 5
        + ratings.quality * 8 * 5
        + ratings.safety * (1 + vehicle_type.safety) * 5
        + ratings.overall * 25
    )


def assemble_and_score_package(
    components: ComponentAssemblyInput,
    vehicle_type: VehicleType,
    year: int = 1901,
) -> tuple[VehicleAssemblyRatings, float, float]:
    """Return assembled ratings, vehicle type fit, and partial buyer-rating proxy."""
    ratings = assemble_vehicle_ratings(components)
    fit = calculate_vehicle_type_fit(ratings, vehicle_type)
    buyer_proxy = calculate_partial_buyer_rating_proxy(
        ratings, vehicle_type, year=year
    )
    return ratings, fit, buyer_proxy


def calculate_final_formula_fit_score(
    assembly_vehicle_type_fit: float,
    assembly_overall: float,
    assembly_quality: float,
) -> float:
    """
    Assembly-first package score for formula_fit objectives.

    Vehicle type fit from assembled ratings dominates; component fits are debug-only.
    """
    return (
        0.80 * assembly_vehicle_type_fit
        + 0.10 * assembly_overall
        + 0.10 * assembly_quality
    )
