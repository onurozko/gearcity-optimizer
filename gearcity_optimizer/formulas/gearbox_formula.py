"""Deterministic GearCity gearbox formulas from wiki pseudo-code."""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any

import pandas as pd

from gearcity_optimizer.core.models import _parse_bool, _parse_optional_float, _parse_optional_str

YEAR_BASE = 1899
TORQUE_YEAR_BASE = 1.0225


def year_factor(base: float, year: int) -> float:
    """Return ``base ** (year - 1899)`` used by gearbox wiki formulas."""
    return base ** (year - YEAR_BASE)


def clamp(value: float, min_value: float = 0.0, max_value: float = 100.0) -> float:
    """Clamp a numeric value to an inclusive range."""
    return max(min_value, min(max_value, value))


def bool01(value: bool) -> int:
    """Convert a boolean to 0 or 1."""
    return 1 if value else 0


SLIDER_FIELDS = (
    "low_gear_ratio",
    "high_gear_ratio",
    "torque_max_input",
    "tech_material",
    "tech_components",
    "tech_technology",
    "tech_techniques",
    "design_ease",
    "design_dependability",
    "design_fuel_economy",
    "design_performance",
)


@dataclass
class GearboxFormulaInputs:
    """Inputs for GearCity gearbox wiki formulas."""

    name: str = "Unnamed Gearbox"
    year: int = 1901
    number_of_gears: int = 2
    has_limited_slip: bool = False
    has_overdrive: bool = False
    has_transaxle: bool = False
    has_reverse: bool = True
    low_gear_ratio: float = 0.5
    high_gear_ratio: float = 0.5
    torque_max_input: float = 0.3
    tech_material: float = 0.3
    tech_components: float = 0.3
    tech_technology: float = 0.3
    tech_techniques: float = 0.3
    design_ease: float = 0.3
    design_dependability: float = 0.3
    design_fuel_economy: float = 0.3
    design_performance: float = 0.3
    subcomponent_weight: float = 0.3
    subcomponent_complexity: float = 0.3
    subcomponent_smoothness: float = 0.3
    subcomponent_ease: float = 0.3
    subcomponent_fuel_rating: float = 0.3
    subcomponent_performance_rating: float = 0.3
    subcomponent_unit_costs: float = 1.0
    subcomponent_design_costs: float = 1.0
    marque_design_gearbox_skill: float = 0.0
    pre_research_gearbox_amount_effect: float = 0.0

    def __post_init__(self) -> None:
        if self.year < YEAR_BASE:
            raise ValueError(f"year must be >= {YEAR_BASE}, got {self.year}")
        if self.number_of_gears < 1:
            raise ValueError("number_of_gears must be >= 1")

        for field_name in SLIDER_FIELDS:
            value = getattr(self, field_name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(
                    f"{field_name} must be between 0 and 1, got {value}"
                )

        for field_name in (
            "subcomponent_weight",
            "subcomponent_complexity",
            "subcomponent_smoothness",
            "subcomponent_ease",
            "subcomponent_fuel_rating",
            "subcomponent_performance_rating",
            "subcomponent_unit_costs",
            "subcomponent_design_costs",
        ):
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} must be non-negative")


@dataclass
class GearboxFormulaResult:
    """Computed gearbox specs and ratings."""

    max_torque_support: float
    weight: float
    power_rating: float
    fuel_economy_rating: float
    performance_rating: float
    reliability_rating: float
    comfort_rating: float
    overall_rating: float
    manufacturing_requirements: float
    design_requirements: float
    warnings: list[str]


def _collect_warnings(inputs: GearboxFormulaInputs, max_torque: float) -> list[str]:
    """Build practical warnings for a gearbox design."""
    warnings: list[str] = []
    if inputs.number_of_gears < 2:
        warnings.append("Gearbox has fewer than 2 forward gears.")
    if inputs.year < 1920 and inputs.number_of_gears > 6:
        warnings.append(
            "More than 6 gears is unusual before 1920 for early-game designs."
        )
    if inputs.has_overdrive and inputs.year < 1930:
        warnings.append(
            "Overdrive is uncommon this early; verify it is intentional."
        )
    if max_torque < 40:
        warnings.append(
            "Maximum torque support is very low; engine torque may exceed gearbox capacity."
        )
    return warnings


def calculate_max_torque_support(inputs: GearboxFormulaInputs) -> float:
    """Calculate gearbox maximum torque support in lb-ft."""
    yf = year_factor(TORQUE_YEAR_BASE, inputs.year)
    torque = 10 * inputs.number_of_gears
    torque += 75 * yf * inputs.torque_max_input
    torque += 35 * yf * (1 - inputs.low_gear_ratio)
    torque += 15 * yf * (1 - inputs.high_gear_ratio)
    torque += 5 * yf * inputs.design_dependability
    torque += 5 * yf * inputs.tech_components
    torque += inputs.marque_design_gearbox_skill / 5.0
    return torque


def calculate_weight(inputs: GearboxFormulaInputs) -> float:
    """Calculate gearbox weight in lbs."""
    weight = 20 + 15 * (inputs.number_of_gears + bool01(inputs.has_reverse))
    weight += 25 * inputs.subcomponent_complexity
    weight += 15 * bool01(inputs.has_overdrive)
    weight += 15 * bool01(inputs.has_limited_slip)
    weight += 50 * inputs.torque_max_input
    weight -= 50 * inputs.design_performance
    weight += 140 * inputs.subcomponent_weight
    weight += 30 * (1 - inputs.tech_material)
    weight -= 20 * bool01(inputs.has_transaxle)
    return weight


def calculate_power_rating(max_torque_support: float, year: int) -> float:
    """Calculate gearbox power rating from torque support."""
    yf = year_factor(TORQUE_YEAR_BASE, year)
    denominator = 80 + 150 * yf + 90 * yf
    return clamp(100 * (max_torque_support / denominator))


def calculate_fuel_economy_rating(inputs: GearboxFormulaInputs) -> float:
    """Calculate gearbox fuel economy rating."""
    rating = 15 * inputs.design_fuel_economy
    rating += 15 * inputs.subcomponent_fuel_rating
    rating += 13 * inputs.low_gear_ratio
    rating += 10 * inputs.high_gear_ratio
    rating += 5 * (1 - inputs.design_performance)
    rating += 6 * bool01(inputs.has_overdrive)
    rating += 2 * inputs.number_of_gears
    rating += 5 * inputs.tech_components
    rating += 6 * inputs.tech_material
    rating += 6 * inputs.tech_technology
    rating += inputs.marque_design_gearbox_skill / 10.0
    return clamp(rating)


def calculate_performance_rating(inputs: GearboxFormulaInputs) -> float:
    """Calculate gearbox performance rating."""
    rating = 10 * inputs.design_performance
    rating += 13 * inputs.subcomponent_performance_rating
    rating += 2 * inputs.number_of_gears
    rating += 7 * inputs.tech_technology
    rating += 6 * inputs.tech_material
    rating += 7 * inputs.tech_components
    rating += 6 * inputs.tech_techniques
    rating += 15 * (1 - inputs.low_gear_ratio)
    rating += 10 * inputs.high_gear_ratio
    rating += 4 * bool01(inputs.has_limited_slip)
    rating += 2 * bool01(inputs.has_transaxle)
    rating += inputs.marque_design_gearbox_skill / 10.0
    return clamp(rating)


def calculate_reliability_rating(inputs: GearboxFormulaInputs) -> float:
    """Calculate gearbox reliability rating."""
    rating = 20 * abs(1.0 - inputs.subcomponent_complexity)
    rating += 15 * inputs.torque_max_input
    rating -= inputs.number_of_gears + bool01(inputs.has_reverse)
    rating += 10 * inputs.tech_material
    rating += 10 * inputs.tech_components
    rating += 10 * inputs.design_dependability
    rating += 5 * (1 - inputs.subcomponent_complexity)
    rating += 5 * (1 - inputs.design_ease)
    rating += 5 * abs(bool01(inputs.has_limited_slip) - 1)
    rating += 5 * abs(bool01(inputs.has_overdrive) - 1)
    rating += 5 * abs(bool01(inputs.has_transaxle) - 1)
    rating += 10 * (1 - inputs.tech_technology)
    rating += inputs.marque_design_gearbox_skill / 10.0
    return clamp(rating)


def calculate_comfort_rating(inputs: GearboxFormulaInputs) -> float:
    """Calculate gearbox comfort rating."""
    rating = 10 * bool01(inputs.has_limited_slip)
    rating += 10 * bool01(inputs.has_reverse)
    rating += 40 * inputs.design_ease
    rating += 20 * inputs.subcomponent_ease
    rating += 20 * inputs.subcomponent_smoothness
    rating += inputs.marque_design_gearbox_skill / 10.0
    return clamp(rating)


def calculate_overall_rating(
    power_rating: float,
    fuel_economy_rating: float,
    performance_rating: float,
    reliability_rating: float,
    comfort_rating: float,
    inputs: GearboxFormulaInputs,
) -> float:
    """Calculate overall gearbox rating."""
    overall = (
        power_rating
        + fuel_economy_rating
        + performance_rating
        + reliability_rating
        + comfort_rating
        + inputs.marque_design_gearbox_skill
    ) / 6.0
    overall += 2.5 * inputs.pre_research_gearbox_amount_effect
    return clamp(overall)


def calculate_manufacturing_requirements(inputs: GearboxFormulaInputs) -> float:
    """Calculate gearbox manufacturing requirements."""
    gears_reverse = inputs.number_of_gears + bool01(inputs.has_reverse)
    design_avg = (
        inputs.design_ease
        + inputs.design_fuel_economy
        + inputs.design_performance
    ) / 3.0
    sub_avg = (
        inputs.subcomponent_ease
        + inputs.subcomponent_fuel_rating
        + inputs.subcomponent_performance_rating
        + inputs.subcomponent_smoothness
    ) / 4.0
    tech_avg = (
        inputs.tech_material + inputs.tech_components + inputs.tech_technology
    ) / 3.0

    return (
        10 * (gears_reverse / 6.0)
        + 20 * inputs.subcomponent_complexity
        + 15 * inputs.torque_max_input
        + 5 * bool01(inputs.has_overdrive)
        + 5 * bool01(inputs.has_transaxle)
        + 5 * bool01(inputs.has_limited_slip)
        + 7 * inputs.tech_techniques
        + 13 * inputs.design_dependability
        + 5 * design_avg
        + 5 * sub_avg
        + 10 * tech_avg
    )


def calculate_design_requirements(inputs: GearboxFormulaInputs) -> float:
    """Calculate gearbox design requirements."""
    gears_reverse = inputs.number_of_gears + bool01(inputs.has_reverse)
    return (
        9 * (gears_reverse / 6.0)
        + 7 * inputs.subcomponent_complexity
        + 3 * bool01(inputs.has_overdrive)
        + 3 * bool01(inputs.has_limited_slip)
        + 3 * inputs.tech_technology
        + 3 * inputs.subcomponent_performance_rating
        + 3 * inputs.subcomponent_fuel_rating
        + 3 * inputs.subcomponent_ease
        + 3 * inputs.subcomponent_smoothness
        + 3 * inputs.tech_material
        + 2 * inputs.tech_components
        + 3 * inputs.torque_max_input
        + 11 * inputs.design_ease
        + 14 * inputs.design_dependability
        + 15 * inputs.design_fuel_economy
        + 15 * inputs.design_performance
    )


def calculate_gearbox(inputs: GearboxFormulaInputs) -> GearboxFormulaResult:
    """Calculate all implemented gearbox specs and ratings."""
    max_torque = calculate_max_torque_support(inputs)
    weight = calculate_weight(inputs)
    power = calculate_power_rating(max_torque, inputs.year)
    fuel = calculate_fuel_economy_rating(inputs)
    performance = calculate_performance_rating(inputs)
    reliability = calculate_reliability_rating(inputs)
    comfort = calculate_comfort_rating(inputs)
    overall = calculate_overall_rating(
        power, fuel, performance, reliability, comfort, inputs
    )
    manufacturing = calculate_manufacturing_requirements(inputs)
    design = calculate_design_requirements(inputs)
    warnings = _collect_warnings(inputs, max_torque)

    return GearboxFormulaResult(
        max_torque_support=max_torque,
        weight=weight,
        power_rating=power,
        fuel_economy_rating=fuel,
        performance_rating=performance,
        reliability_rating=reliability,
        comfort_rating=comfort,
        overall_rating=overall,
        manufacturing_requirements=manufacturing,
        design_requirements=design,
        warnings=warnings,
    )


def _row_to_inputs(row: pd.Series) -> GearboxFormulaInputs:
    """Convert one CSV row to gearbox formula inputs."""
    kwargs: dict[str, Any] = {"name": str(row["name"])}
    for field in fields(GearboxFormulaInputs):
        if field.name == "name":
            continue
        raw = row.get(field.name)
        if field.type is bool or field.type == "bool":
            kwargs[field.name] = _parse_bool(raw)
        elif field.type is int:
            kwargs[field.name] = int(raw)
        else:
            kwargs[field.name] = float(raw)
    return GearboxFormulaInputs(**kwargs)


def load_gearbox_formula_inputs(path: str) -> list[GearboxFormulaInputs]:
    """Load gearbox formula input rows from CSV."""
    df = pd.read_csv(path)
    return [_row_to_inputs(row) for _, row in df.iterrows()]


def export_gearbox_candidates_csv(
    rows: list[tuple[GearboxFormulaInputs, GearboxFormulaResult]],
    output_path: str,
) -> None:
    """Export formula results to package-optimizer-compatible gearbox CSV."""
    records = []
    for inputs, result in rows:
        records.append(
            {
                "name": inputs.name,
                "power": round(result.power_rating, 2),
                "fuel_economy": round(result.fuel_economy_rating, 2),
                "performance": round(result.performance_rating, 2),
                "reliability": round(result.reliability_rating, 2),
                "comfort": round(result.comfort_rating, 2),
                "overall": round(result.overall_rating, 2),
                "unit_cost": 0,
                "design_cost": 0,
                "max_torque": round(result.max_torque_support, 2),
                "weight": round(result.weight, 2),
                "gears": inputs.number_of_gears,
                "notes": "generated from gearbox formula",
            }
        )
    pd.DataFrame(records).to_csv(output_path, index=False)
