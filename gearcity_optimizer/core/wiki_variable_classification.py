"""Classify wiki mechanics variables as inputs (controls) vs outputs."""

from __future__ import annotations

import re

OUTPUT_STAT_KEYS = frozenset(
    {
        "displacement",
        "horsepower",
        "horsepower_rating",
        "torque",
        "torque_output",
        "power",
        "power_output",
        "rpm",
        "cargo",
        "cargo_volume",
        "cargo_rating",
        "fuel_rating",
        "fuel_economy_rating",
        "fuel_consumption",
        "fuel_consumption_mpg",
        "smoothness",
        "reliability",
        "reliability_rating",
        "dependability",
        "dependability_rating",
        "overall",
        "overall_rating",
        "safety",
        "safety_rating",
        "luxury",
        "luxury_rating",
        "driveability",
        "driveability_rating",
        "design_requirements",
        "manufacturing_requirements",
        "unit_costs",
        "design_costs",
        "finish_time",
        "employees_required",
        "cylinders",
        "number_of_gears",
        "max_torque_support",
        "weight",
        "length",
        "width",
        "height",
        "drag_coefficient",
        "estimated_surface_area",
        "top_speed",
        "acceleration",
        "braking",
        "towing",
        "roadhold",
        "performance_rating",
        "comfort_rating",
        "strength_rating",
        "durability_rating",
        "quality_rating",
        "rating_performance",
        "rating_fuel",
        "rating_power",
        "rating_cargo",
        "rating_overall",
        "rating_dependability",
        "rating_luxury",
        "rating_safety",
        "rating_drivability",
    }
)

OUTPUT_SECTION_KEYWORDS = frozenset(
    {
        "horsepower",
        "torque",
        "displacement",
        "fuel consumption",
        "fuel rating",
        "fuel economy rating",
        "power rating",
        "performance rating",
        "comfort rating",
        "strength rating",
        "durability rating",
        "reliability rating",
        "smoothness",
        "overall rating",
        "cargo rating",
        "driveability",
        "safety rating",
        "dependability rating",
        "quality rating",
        "design requirements",
        "manufacturing requirements",
        "unit costs",
        "design costs",
        "finish time",
        "employees required",
        "maximum torque support",
        "weight",
        "length",
        "width",
        "height",
        "top speed",
        "acceleration",
        "braking",
        "towing",
        "roadhold",
        "drag coefficient",
        "cargo volume",
        "estimated surface area",
    }
)

SLIDER_CONTROL_PREFIXES = ("Slider_", "Sliders_")
COMPONENT_CONTROL_PREFIXES = ("SubComponent_", "Selected_")


def normalize_key(value: str) -> str:
    cleaned = re.sub(r"[^\w\s]", " ", value.strip())
    return re.sub(r"\s+", "_", cleaned).lower()


def is_wiki_output_section(section_title: str) -> bool:
    """Return True when a wiki section title describes a calculated output."""
    normalized = normalize_key(section_title)
    if normalized in OUTPUT_STAT_KEYS:
        return True
    for keyword in OUTPUT_SECTION_KEYWORDS:
        key = keyword.replace(" ", "_")
        if normalized == key:
            return True
    return False


def is_wiki_output_variable(variable: str) -> bool:
    """Return True when a variable name represents an output stat, not a control."""
    if variable.startswith(SLIDER_CONTROL_PREFIXES):
        return False
    if variable.startswith(COMPONENT_CONTROL_PREFIXES):
        return False
    normalized = normalize_key(variable)
    if normalized in OUTPUT_STAT_KEYS:
        return True
    if normalized.endswith("_rating") or normalized.endswith("_requirements"):
        return True
    return is_wiki_output_section(variable)


def is_wiki_control_variable(variable: str, *, control_type: str | None = None) -> bool:
    """Return True when a wiki variable is a documented input control."""
    if control_type in {"derived"}:
        return False
    if control_type in {"slider", "dropdown", "checkbox"}:
        return True
    if variable.startswith(SLIDER_CONTROL_PREFIXES):
        return True
    return False


def is_output_stat_key(key: str) -> bool:
    """Return True when a key names an output stat, not a wiki control."""
    return is_wiki_output_variable(key)
