"""Cost mode weights for future part recommendation scoring."""

from __future__ import annotations

from enum import Enum


class CostMode(str, Enum):
    """Design budget philosophy for recommendations."""

    CHEAP = "cheap"
    BALANCED = "balanced"
    LUXURY = "luxury"


COST_MODE_DESCRIPTIONS: dict[CostMode, str] = {
    CostMode.CHEAP: (
        "Prioritize low cost, reliability, manufacture ease, and acceptable "
        "performance. Avoid expensive or over-advanced tech unless the vehicle "
        "type needs it."
    ),
    CostMode.BALANCED: (
        "Prioritize buyer-rating-per-cost. Spend on the stats the vehicle type "
        "cares about most."
    ),
    CostMode.LUXURY: (
        "Allow expensive materials, smoother engines, comfort, safety, luxury, "
        "and performance where useful."
    ),
}


def parse_cost_mode(value: str) -> CostMode:
    """Parse a cost mode string, raising ValueError when invalid."""
    normalized = value.strip().lower()
    try:
        return CostMode(normalized)
    except ValueError as exc:
        valid = ", ".join(mode.value for mode in CostMode)
        raise ValueError(f"Cost mode must be one of: {valid}. Got {value!r}.") from exc
