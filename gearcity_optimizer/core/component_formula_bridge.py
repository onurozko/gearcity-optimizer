"""Map Components.xml choices onto wiki formula subcomponent inputs."""

from __future__ import annotations

import re

from gearcity_optimizer.core.layout_reference import layout_reference_for_choice
from gearcity_optimizer.core.wiki_component_compatibility import (
    layout_cylinder_bank_arrangement,
    parse_cylinder_count,
)
from gearcity_optimizer.importers.component_choices import ComponentChoice

# Typical Components.xml rating scale (0-100). Used when a part is selected but attrs are missing.
DEFAULT_COMPONENT_RATING = 42.0

# Wiki formula subcomponent inputs use 0-1 normalized values (defaults ~0.3), not 0-100 game stats.
FORMULA_SUBCOMPONENT_DEFAULT = DEFAULT_COMPONENT_RATING / 100.0

STAT_ALIASES: dict[str, tuple[str, ...]] = {
    "reliability": ("reliability", "reliablity", "dependability", "durability"),
    "performance": ("performance", "power", "perf"),
    "fueleconomy": ("fueleconomy", "fuelecon", "fuelefficiency", "fuel", "economy"),
    "smoothness": ("smoothness", "smooth", "comfort"),
    "weight": ("weight",),
    "design": ("design", "designcost", "designrequirements"),
    "manufacturing": ("manufacturing", "manu", "manufacturingrequirements"),
    "complexity": ("complexity", "complex"),
    "length": ("length", "enginelength", "engine_length"),
    "width": ("width", "enginewidth", "engine_width"),
}


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _lookup_stat(stats: dict[str, float], *aliases: str) -> float | None:
    normalized_stats = {_normalize_key(key): value for key, value in stats.items()}
    for alias in aliases:
        key = _normalize_key(alias)
        if key in normalized_stats:
            return normalized_stats[key]
    for canonical, alias_group in STAT_ALIASES.items():
        if any(_normalize_key(alias) in {_normalize_key(item) for item in aliases} for alias in alias_group):
            for alias in alias_group:
                key = _normalize_key(alias)
                if key in normalized_stats:
                    return normalized_stats[key]
    return None


def component_rating(stats: dict[str, float], *aliases: str, default: float = DEFAULT_COMPONENT_RATING) -> float:
    """Return a game-scale rating from choice stats, with a safe default."""
    value = _lookup_stat(stats, *aliases)
    if value is None:
        return default
    if value <= 1.0 and "cylinders" not in aliases and "gears" not in aliases:
        # Normalized 0-1 exports from some parsers.
        return max(0.0, min(100.0, value * 100.0))
    return max(0.0, min(100.0, value))


def formula_subcomponent_value(
    stats: dict[str, float],
    *aliases: str,
    default: float = DEFAULT_COMPONENT_RATING,
) -> float:
    """Map 0-100 Components.xml stats onto 0-1 wiki formula subcomponent inputs."""
    rating = component_rating(stats, *aliases, default=default)
    if rating > 1.0:
        return max(0.0, min(1.0, rating / 100.0))
    return max(0.0, min(1.0, rating))


def layout_dimension_subcomponent_value(
    stats: dict[str, float],
    *aliases: str,
    default: float = DEFAULT_COMPONENT_RATING,
) -> float:
    """Layout length/width subcomponents may exceed 1.0 in game data (e.g. 1.3 for W layout)."""
    value = _lookup_stat(stats, *aliases)
    if value is None:
        rating = default
    elif value <= 1.0:
        rating = value
    elif value <= 100.0:
        rating = value / 100.0
    else:
        rating = value
    return max(0.0, rating)


def _valvetrain_flags(choice: ComponentChoice) -> dict[str, bool]:
    text = " ".join(
        [
            choice.display_name,
            choice.name,
            choice.raw_attributes.get("picture", ""),
        ]
    ).lower()
    tokens = _normalize_key(text)
    return {
        "has_overhead_cam": any(token in tokens for token in ("ohv", "dohc", "sohc", "overhead")),
        "has_fuel_injection": "injection" in tokens or "fuelinjection" in tokens,
        "is_supercharged": "supercharg" in tokens,
        "is_turbocharged": "turbo" in tokens and "twin" not in tokens,
    }


def subcomponent_values_from_choices(
    selected_choices: dict[str, ComponentChoice] | None,
) -> dict[str, dict[str, float | int | bool]]:
    """Map selected choices to chassis/engine/gearbox formula extras."""
    if not selected_choices:
        return {"engine": {}, "chassis": {}, "gearbox": {}}

    engine: dict[str, float | int | bool] = {}
    chassis: dict[str, float] = {}
    gearbox: dict[str, float] = {}

    layout = selected_choices.get("engine_layout")
    if layout is not None:
        stats = layout.stats
        layout_ref = layout_reference_for_choice(layout)
        engine["layout_weight"] = formula_subcomponent_value(stats, "weight")

        length_stat = _lookup_stat(stats, "length", "engine_length")
        if length_stat is not None:
            layout_length = layout_dimension_subcomponent_value(stats, "length", "engine_length")
        elif layout_ref is not None:
            layout_length = layout_ref.engine_length
        else:
            layout_length = FORMULA_SUBCOMPONENT_DEFAULT
        engine["layout_length"] = layout_length

        width_stat = _lookup_stat(stats, "width", "engine_width")
        if width_stat is not None:
            layout_width = layout_dimension_subcomponent_value(stats, "width", "engine_width")
        elif layout_ref is not None:
            layout_width = layout_ref.engine_width
        else:
            layout_width = FORMULA_SUBCOMPONENT_DEFAULT
        engine["layout_width"] = layout_width

        engine["wiki_subcomponent_layout_length"] = layout_length
        engine["wiki_subcomponent_layout_width"] = layout_width

        perf_stat = _lookup_stat(stats, "performance", "power", "powerratings")
        if perf_stat is not None:
            engine["layout_performance"] = formula_subcomponent_value(stats, "performance", "power")
        elif layout_ref is not None:
            engine["layout_performance"] = layout_ref.layout_power
        else:
            engine["layout_performance"] = FORMULA_SUBCOMPONENT_DEFAULT

        smooth_stat = _lookup_stat(stats, "smoothness", "smooth")
        if smooth_stat is not None:
            engine["layout_smoothness"] = formula_subcomponent_value(stats, "smoothness")
        elif layout_ref is not None:
            engine["layout_smoothness"] = layout_ref.layout_smooth
        else:
            engine["layout_smoothness"] = FORMULA_SUBCOMPONENT_DEFAULT

        engine["layout_reliability"] = formula_subcomponent_value(stats, "reliability")
        engine["layout_manufacturing"] = formula_subcomponent_value(stats, "manufacturing")
        engine["layout_design"] = formula_subcomponent_value(stats, "design")
        engine["cylinder_bank_arrangement"] = layout_cylinder_bank_arrangement(layout)

    fuel = selected_choices.get("fuel_type")
    if fuel is not None:
        stats = fuel.stats
        engine["fuel_system_performance"] = formula_subcomponent_value(stats, "performance")
        engine["fuel_system_fuel_economy"] = formula_subcomponent_value(stats, "fueleconomy", "fuel")
        engine["fuel_system_reliability"] = formula_subcomponent_value(stats, "reliability")

    induction = selected_choices.get("forced_induction")
    if induction is not None:
        stats = induction.stats
        engine["aspiration_performance"] = formula_subcomponent_value(stats, "performance")
        engine["aspiration_fuel_economy"] = formula_subcomponent_value(stats, "fueleconomy", "fuel")
        engine["aspiration_reliability"] = formula_subcomponent_value(stats, "reliability")
        flags = _valvetrain_flags(induction)
        if flags["is_supercharged"]:
            engine["is_supercharged"] = True
        if flags["is_turbocharged"]:
            engine["is_turbocharged"] = True

    valvetrain = selected_choices.get("valvetrain")
    if valvetrain is not None:
        engine.update(_valvetrain_flags(valvetrain))

    cylinder = selected_choices.get("cylinder_count")
    if cylinder is not None:
        count = parse_cylinder_count(cylinder)
        if count is not None:
            engine["cylinders"] = count
    elif layout is not None and "single" in _normalize_key(layout.display_name):
        engine["cylinders"] = 1
    elif "cylinders" not in engine:
        engine["cylinders"] = 4

    frame = selected_choices.get("frame")
    if frame is not None:
        stats = frame.stats
        chassis["frame_strength"] = formula_subcomponent_value(stats, "strength", "reliability")
        chassis["frame_safety"] = formula_subcomponent_value(stats, "safety", "strength", "reliability")
        chassis["frame_durability"] = formula_subcomponent_value(stats, "reliability", "durability")
        chassis["frame_weight"] = formula_subcomponent_value(stats, "weight")
        chassis["frame_design"] = formula_subcomponent_value(stats, "design")
        chassis["frame_manufacturing"] = formula_subcomponent_value(stats, "manufacturing")
        chassis["frame_performance"] = formula_subcomponent_value(stats, "performance")

    for suspension_key, prefix in (
        ("suspension_front", "front_suspension"),
        ("suspension_rear", "rear_suspension"),
        ("suspension", "front_suspension"),
    ):
        suspension = selected_choices.get(suspension_key)
        if suspension is None:
            continue
        stats = suspension.stats
        chassis[f"{prefix}_comfort"] = formula_subcomponent_value(stats, "comfort", "smoothness")
        chassis[f"{prefix}_performance"] = formula_subcomponent_value(stats, "performance")
        chassis[f"{prefix}_durability"] = formula_subcomponent_value(stats, "reliability", "durability")
        chassis[f"{prefix}_design"] = formula_subcomponent_value(stats, "design")
        chassis[f"{prefix}_manufacturing"] = formula_subcomponent_value(stats, "manufacturing")

    drivetrain = selected_choices.get("drivetrain")
    if drivetrain is not None:
        stats = drivetrain.stats
        chassis["drivetrain_car_performance"] = formula_subcomponent_value(stats, "performance")
        chassis["drivetrain_durability"] = formula_subcomponent_value(stats, "reliability", "durability")
        chassis["drivetrain_design"] = formula_subcomponent_value(stats, "design")
        chassis["drivetrain_manufacturing"] = formula_subcomponent_value(stats, "manufacturing")

    gearbox_type = selected_choices.get("gearbox_type")
    if gearbox_type is not None:
        stats = gearbox_type.stats
        gearbox["subcomponent_performance_rating"] = formula_subcomponent_value(stats, "performance")
        gearbox["subcomponent_fuel_rating"] = formula_subcomponent_value(stats, "fueleconomy", "fuel")
        gearbox["subcomponent_durability"] = formula_subcomponent_value(stats, "reliability", "durability")
        gearbox["subcomponent_smoothness"] = formula_subcomponent_value(stats, "smoothness", "comfort")
        gearbox["subcomponent_weight"] = formula_subcomponent_value(stats, "weight")
        gearbox["subcomponent_complexity"] = formula_subcomponent_value(stats, "complexity")

    gear_count = selected_choices.get("gear_count")
    if gear_count is not None:
        from gearcity_optimizer.core.wiki_component_compatibility import parse_gear_count

        gears = parse_gear_count(gear_count)
        if gears is not None:
            gearbox["number_of_gears"] = gears

    return {"engine": engine, "chassis": chassis, "gearbox": gearbox}


def count_wired_subcomponent_fields(
    selected_choices: dict[str, ComponentChoice] | None,
) -> tuple[int, int]:
    """Return (fields_set, choice_types_present) for diagnostics."""
    if not selected_choices:
        return 0, 0
    mapped = subcomponent_values_from_choices(selected_choices)
    field_count = sum(len(section) for section in mapped.values())
    return field_count, len(selected_choices)
