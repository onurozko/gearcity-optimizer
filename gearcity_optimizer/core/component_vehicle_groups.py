"""Vehicle groups for component suitability scoring."""

from __future__ import annotations

from gearcity_optimizer.core.component_priorities import get_adjusted_vehicle_weights
from gearcity_optimizer.core.models import VehicleType
from gearcity_optimizer.importers.component_choices import ComponentChoice
from gearcity_optimizer.reports.part_recommender import is_work_or_utility_focused

VehicleGroup = str

MAINSTREAM_PASSENGER = "mainstream_passenger"
ECONOMY_PASSENGER = "economy_passenger"
SPORT_PERFORMANCE = "sport_performance"
LUXURY_PASSENGER = "luxury_passenger"
HEAVY_UTILITY = "heavy_utility"
COMMERCIAL = "commercial"
GENERAL = "general"

SPORT_NAME_HINTS = ("sport", "roadster", "race", "hot rod", "muscle")
LUXURY_NAME_HINTS = ("luxury", "limousine", "executive", "premium")
ECONOMY_NAME_HINTS = ("economy", "compact", "subcompact", "mini")
COMMERCIAL_NAME_HINTS = ("commercial", "van", "bus", "taxi", "fleet")
HEAVY_NAME_HINTS = ("truck", "pickup", "hauler", "semi", "tractor", "heavy")


def classify_vehicle_group(vehicle_type: VehicleType) -> VehicleGroup:
    """Map a vehicle type into a coarse suitability group."""
    name = vehicle_type.name.lower()
    weights = get_adjusted_vehicle_weights(vehicle_type)

    if any(hint in name for hint in HEAVY_NAME_HINTS) or is_work_or_utility_focused(vehicle_type):
        if weights.get("cargo", 0.0) >= 0.55 or weights.get("power", 0.0) >= 0.6:
            return HEAVY_UTILITY

    if any(hint in name for hint in COMMERCIAL_NAME_HINTS):
        return COMMERCIAL

    if any(hint in name for hint in SPORT_NAME_HINTS) or (
        weights.get("performance", 0.0) >= 0.65 and weights.get("power", 0.0) >= 0.6
    ):
        return SPORT_PERFORMANCE

    if any(hint in name for hint in LUXURY_NAME_HINTS) or weights.get("luxury", 0.0) >= 0.65:
        return LUXURY_PASSENGER

    if any(hint in name for hint in ECONOMY_NAME_HINTS) or (
        weights.get("fuel", 0.0) >= 0.65 and weights.get("luxury", 0.0) < 0.45
    ):
        return ECONOMY_PASSENGER

    if weights.get("performance", 0.0) >= 0.55 or weights.get("drivability", 0.0) >= 0.5:
        return MAINSTREAM_PASSENGER

    return GENERAL


PASSENGER_GROUPS = frozenset(
    {MAINSTREAM_PASSENGER, ECONOMY_PASSENGER, LUXURY_PASSENGER, GENERAL}
)

PRIMITIVE_LAYOUT_TOKENS = frozenset(
    {
        "singlelayout",
        "single layout",
        "single-cylinder",
        "singlecylinder",
        "primitive",
    }
)

MAINSTREAM_LAYOUT_TOKENS = frozenset(
    {
        "straightlayout",
        "straight layout",
        "ilayout",
        "i layout",
        "inline",
        "flatlayout",
        "flat layout",
        "vlayout",
        "v layout",
        "v6",
        "v8",
    }
)

SPECIALTY_LAYOUT_TOKENS = frozenset(
    {
        "boxer",
        "radial",
        "w layout",
        "wlayout",
        "x layout",
        "rotary",
    }
)

LUXURY_LAYOUT_TOKENS = frozenset({"vlayout", "v layout", "smooth", "refined"})
PERFORMANCE_LAYOUT_TOKENS = frozenset({"vlayout", "v layout", "sport", "performance"})

PRIMITIVE_VALVETRAIN_TOKENS = frozenset(
    {
        "novalve",
        "no valve",
        "no_valve",
        "atmospheric",
    }
)


def _name_tokens(name: str) -> str:
    return name.lower().replace("_", "").replace("-", "")


def filter_engine_layout_candidates(
    candidates: list[ComponentChoice],
    *,
    vehicle_type: VehicleType,
) -> list[ComponentChoice]:
    """Drop primitive single-cylinder layouts when mainstream layouts are available."""
    group = classify_vehicle_group(vehicle_type)
    if group not in PASSENGER_GROUPS:
        return candidates
    mainstream = [item for item in candidates if is_mainstream_layout(item.display_name)]
    if not mainstream:
        return candidates
    filtered = [
        item
        for item in candidates
        if not is_primitive_layout(item.display_name)
    ]
    return filtered or candidates


def is_primitive_layout(name: str) -> bool:
    lowered = _name_tokens(name)
    return any(token.replace(" ", "") in lowered for token in PRIMITIVE_LAYOUT_TOKENS)


def is_mainstream_layout(name: str) -> bool:
    lowered = _name_tokens(name)
    return any(token.replace(" ", "") in lowered for token in MAINSTREAM_LAYOUT_TOKENS)


def is_specialty_layout(name: str) -> bool:
    lowered = _name_tokens(name)
    return any(token.replace(" ", "") in lowered for token in SPECIALTY_LAYOUT_TOKENS)


def is_primitive_valvetrain(name: str) -> bool:
    lowered = _name_tokens(name)
    return any(token.replace(" ", "") in lowered for token in PRIMITIVE_VALVETRAIN_TOKENS)
