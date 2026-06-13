"""Penalty rules for design mismatches and pricing issues."""

from __future__ import annotations

from gearcity_optimizer.core.models import CandidateDesign, VehicleType


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    """Clamp a value to the inclusive range [low, high]."""
    return max(low, min(high, value))


def apply_penalties(
    candidate: CandidateDesign,
    vehicle_type: VehicleType,
    year: int,
) -> tuple[float, list[str]]:
    """
    Apply design and pricing penalties.

    Returns:
        penalty_multiplier: cumulative multiplier starting at 1.0
        warnings: human-readable warning messages
    """
    penalty_multiplier = 1.0
    warnings: list[str] = []

    # 1. Gearbox torque mismatch
    if (
        candidate.engine_torque is not None
        and candidate.gearbox_max_torque is not None
        and candidate.gearbox_max_torque < candidate.engine_torque
    ):
        torque_ratio = _clamp(
            candidate.gearbox_max_torque / candidate.engine_torque
        )
        penalty_multiplier *= torque_ratio * 0.95
        warnings.append(
            "Gearbox max torque is below engine torque. "
            "This can hurt quality and dependability."
        )

    # 2. Low top speed penalty
    base = 10 + 1.05 * (year - 1899)
    min_top_speed = base + base * (vehicle_type.performance - 0.3)

    if (
        candidate.top_speed_kph is not None
        and candidate.top_speed_kph < min_top_speed
    ):
        speed_ratio = _clamp(candidate.top_speed_kph / min_top_speed)
        penalty_multiplier *= speed_ratio
        warnings.append(
            "Top speed is below the minimum expected for this vehicle type."
        )

    # 3. Low engine smoothness for luxury vehicles
    if (
        vehicle_type.luxury > 0.3
        and candidate.engine_smoothness is not None
        and candidate.engine_smoothness < vehicle_type.luxury * 35
        and candidate.engine_smoothness < 35
    ):
        smoothness_ratio = _clamp(
            candidate.engine_smoothness / (vehicle_type.luxury * 35)
        )
        penalty_multiplier *= smoothness_ratio
        warnings.append(
            "Engine smoothness is too low for a luxury-sensitive vehicle type."
        )

    # 4. Price gouging penalty
    if candidate.sale_price is not None and candidate.unit_cost > 0:
        max_reasonable_price = candidate.unit_cost * (
            3.5 + vehicle_type.wealth_demo / 5
        )
        if candidate.sale_price > max_reasonable_price:
            price_ratio = candidate.sale_price / max_reasonable_price
            price_penalty = _clamp(1 - (price_ratio / 2))
            penalty_multiplier *= price_penalty
            warnings.append(
                "Sale price may be too high compared to unit cost "
                "and wealth demographic."
            )

    # 5. Quality-to-price warning (no penalty)
    if candidate.sale_price is not None and candidate.unit_cost > 0:
        markup = candidate.sale_price / candidate.unit_cost
        if markup > 2.5 and candidate.quality < 30:
            warnings.append(
                "High markup with low quality may hurt buyer rating."
            )

    return penalty_multiplier, warnings
