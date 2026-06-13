"""Deterministic GearCity chassis formulas from wiki pseudo-code."""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from typing import Any

import pandas as pd

YEAR_BASE = 1899
WEIGHT_YEAR_BASE = 0.9962
WEIGHT_YEAR_DIVISOR_LATE = 1.469262941607760500229789005264
WEIGHT_YEAR_CUTOFF = 1981


def year_factor(base: float, year: int) -> float:
    """Return ``base ** (year - 1899)`` used by chassis wiki formulas."""
    return base ** (year - YEAR_BASE)


def clamp(value: float, min_value: float = 0.0, max_value: float = 100.0) -> float:
    """Clamp a numeric value to an inclusive range."""
    return max(min_value, min(max_value, value))


def validate_slider(name: str, value: float) -> None:
    """Raise ValueError if a slider is outside 0..1."""
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1, got {value}")


SLIDER_FIELDS = (
    "fd_length",
    "fd_width",
    "fd_height",
    "fd_weight",
    "fd_engine_width",
    "fd_engine_length",
    "sus_stability",
    "sus_comfort",
    "sus_performance",
    "sus_braking",
    "sus_durability",
    "design_performance",
    "design_control",
    "design_strength",
    "design_dependability",
    "design_pace",
    "tech_materials",
    "tech_components",
    "tech_techniques",
    "tech_technology",
)

SUBCOMPONENT_FIELDS = (
    "frame_strength",
    "frame_safety",
    "frame_durability",
    "frame_weight",
    "frame_design",
    "frame_manufacturing",
    "frame_cost",
    "frame_performance",
    "front_suspension_steering",
    "front_suspension_braking",
    "front_suspension_comfort",
    "front_suspension_performance",
    "front_suspension_durability",
    "front_suspension_manufacturing",
    "front_suspension_design",
    "front_suspension_cost",
    "rear_suspension_braking",
    "rear_suspension_steering",
    "rear_suspension_performance",
    "rear_suspension_comfort",
    "rear_suspension_manufacturing",
    "rear_suspension_durability",
    "rear_suspension_cost",
    "rear_suspension_design",
    "drivetrain_ride_steering",
    "drivetrain_ride_performance",
    "drivetrain_durability",
    "drivetrain_weight",
    "drivetrain_car_performance",
    "drivetrain_manufacturing",
    "drivetrain_design",
    "drivetrain_cost",
    "drivetrain_engine_width",
    "drivetrain_engine_length",
)


@dataclass
class ChassisFormulaInputs:
    """Inputs for GearCity chassis wiki formulas."""

    name: str = "Unnamed Chassis"
    year: int = 1901
    fd_length: float = 0.5
    fd_width: float = 0.5
    fd_height: float = 0.5
    fd_weight: float = 0.5
    fd_engine_width: float = 0.5
    fd_engine_length: float = 0.5
    sus_stability: float = 0.5
    sus_comfort: float = 0.5
    sus_performance: float = 0.5
    sus_braking: float = 0.5
    sus_durability: float = 0.5
    design_performance: float = 0.5
    design_control: float = 0.5
    design_strength: float = 0.5
    design_dependability: float = 0.5
    design_pace: float = 0.5
    tech_materials: float = 0.5
    tech_components: float = 0.5
    tech_techniques: float = 0.5
    tech_technology: float = 0.5
    frame_strength: float = 0.3
    frame_safety: float = 0.3
    frame_durability: float = 0.3
    frame_weight: float = 0.3
    frame_design: float = 0.3
    frame_manufacturing: float = 0.3
    frame_cost: float = 1.0
    frame_performance: float = 0.3
    front_suspension_steering: float = 0.3
    front_suspension_braking: float = 0.3
    front_suspension_comfort: float = 0.3
    front_suspension_performance: float = 0.3
    front_suspension_durability: float = 0.3
    front_suspension_manufacturing: float = 0.3
    front_suspension_design: float = 0.3
    front_suspension_cost: float = 1.0
    rear_suspension_braking: float = 0.3
    rear_suspension_steering: float = 0.3
    rear_suspension_performance: float = 0.3
    rear_suspension_comfort: float = 0.3
    rear_suspension_manufacturing: float = 0.3
    rear_suspension_durability: float = 0.3
    rear_suspension_cost: float = 1.0
    rear_suspension_design: float = 0.3
    drivetrain_ride_steering: float = 0.3
    drivetrain_ride_performance: float = 0.3
    drivetrain_durability: float = 0.3
    drivetrain_weight: float = 0.3
    drivetrain_car_performance: float = 0.3
    drivetrain_manufacturing: float = 0.3
    drivetrain_design: float = 0.3
    drivetrain_cost: float = 1.0
    drivetrain_engine_width: float = 1.0
    drivetrain_engine_length: float = 1.0
    marque_design_chassis_skill: float = 0.0
    pre_research_chassis_amount_effect: float = 0.0
    global_lengths: float = 100.0
    global_width: float = 100.0
    global_weight: float = 100.0

    def __post_init__(self) -> None:
        if self.year < YEAR_BASE:
            raise ValueError(f"year must be >= {YEAR_BASE}, got {self.year}")

        for field_name in SLIDER_FIELDS:
            validate_slider(field_name, getattr(self, field_name))

        for field_name in SUBCOMPONENT_FIELDS:
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} must be non-negative")

        for field_name in ("global_lengths", "global_width", "global_weight"):
            if getattr(self, field_name) <= 0:
                raise ValueError(f"{field_name} must be positive")


@dataclass
class ChassisFormulaResult:
    """Computed chassis specs and ratings."""

    chassis_length: float
    chassis_width: float
    chassis_weight: float
    max_engine_length: float
    max_engine_width: float
    comfort_rating: float
    performance_rating: float
    strength_rating: float
    durability_rating: float
    overall_rating: float
    design_requirements: float
    manufacturing_requirements: float
    warnings: list[str]


def calculate_chassis_length(inputs: ChassisFormulaInputs) -> float:
    """Calculate chassis length in cm."""
    return (
        145
        + inputs.global_lengths * (2.3 * inputs.fd_length)
        - (inputs.global_lengths * 0.5) / 5.0
    )


def calculate_chassis_width(inputs: ChassisFormulaInputs) -> float:
    """Calculate chassis width in cm."""
    return (
        100
        + inputs.global_width * inputs.fd_width
        + 20 * inputs.fd_length
    )


def calculate_chassis_weight(inputs: ChassisFormulaInputs) -> float:
    """Calculate chassis weight in kg."""
    gw = inputs.global_weight
    weight = 40.0
    weight += gw * (1.25 * inputs.fd_weight + 0.1)
    weight += (gw * 0.5) * (6 * inputs.fd_length + 0.1)
    weight += (gw / 15.0) * (3.3 * inputs.fd_width + 0.1)
    weight += (gw / 20.0) * (2 * inputs.fd_height + 0.1)
    weight += (gw / 5.0) * (5 * inputs.frame_weight + 0.1)
    weight += (gw / 10.0) * (3 * inputs.drivetrain_weight + 0.1)
    weight -= (gw / 5.0) * inputs.tech_materials
    weight -= (gw / 8.0) * inputs.design_performance
    weight -= (gw / 11.0) * inputs.tech_techniques

    if inputs.year < WEIGHT_YEAR_CUTOFF:
        weight /= 2.0 * year_factor(WEIGHT_YEAR_BASE, inputs.year)
    else:
        weight /= WEIGHT_YEAR_DIVISOR_LATE

    return weight


def calculate_max_engine_length(inputs: ChassisFormulaInputs) -> float:
    """Calculate maximum engine length in inches."""
    length_term = (inputs.global_lengths * 2.25) / 24.0
    inner = (
        length_term * ((inputs.fd_length + 0.1) * 2.5)
        + length_term * (inputs.fd_engine_length + 0.1)
    )
    return (8.0 + inner) * inputs.drivetrain_engine_length


def calculate_max_engine_width(inputs: ChassisFormulaInputs) -> float:
    """Calculate maximum engine width in inches."""
    inner = (
        12.0 * ((inputs.fd_width + 0.1) * 2.5)
        + 13.0 * (1.25 * inputs.fd_engine_width + 0.1)
    )
    return (8.0 + inner) * inputs.drivetrain_engine_width


def calculate_comfort_rating(inputs: ChassisFormulaInputs) -> float:
    """Calculate chassis comfort rating."""
    rating = inputs.design_control
    rating += inputs.drivetrain_ride_steering
    rating += inputs.fd_weight
    rating += (
        inputs.front_suspension_braking
        + inputs.rear_suspension_braking
        + inputs.sus_braking * 4.5
    )
    rating += (
        inputs.front_suspension_comfort
        + inputs.rear_suspension_comfort
        + inputs.sus_comfort * 6.0
    )
    rating += (
        inputs.front_suspension_steering
        + inputs.rear_suspension_steering
        + inputs.sus_stability * 4.5
    )
    rating += (
        inputs.tech_components
        + inputs.tech_materials
        + inputs.tech_technology
        + inputs.tech_techniques
    ) / 2.0

    rating /= 2.6
    rating *= 10.0
    rating += 10.0 * (inputs.marque_design_chassis_skill / 100.0)
    return clamp(rating)


def calculate_performance_rating(inputs: ChassisFormulaInputs) -> float:
    """Calculate chassis performance rating."""
    rating = inputs.sus_braking * 2.0
    rating += inputs.design_performance
    rating -= inputs.fd_weight * 2.0
    rating += inputs.sus_performance * 4.0
    rating += inputs.front_suspension_steering
    rating += inputs.rear_suspension_steering
    rating += (
        inputs.tech_components
        + inputs.tech_materials * 2.0
        + inputs.tech_technology
        + inputs.tech_techniques
    ) / 2.0
    rating += inputs.front_suspension_performance
    rating += inputs.rear_suspension_performance
    rating += inputs.frame_performance
    rating += inputs.drivetrain_car_performance * 2.0
    rating -= inputs.fd_length + inputs.fd_width
    rating += 1.0 - inputs.sus_stability

    rating /= 2.0
    rating *= 10.0
    rating += 10.0 * (inputs.marque_design_chassis_skill / 100.0)
    return clamp(rating)


def calculate_strength_rating(inputs: ChassisFormulaInputs) -> float:
    """Calculate chassis strength rating."""
    rating = (
        inputs.drivetrain_weight + inputs.frame_weight
    ) / 4.0
    rating += inputs.fd_weight * 2.0
    rating += (
        inputs.drivetrain_durability
        + inputs.frame_durability
        + inputs.rear_suspension_durability
        + inputs.front_suspension_durability
    ) / 6.0
    rating += inputs.fd_height * 5.0
    rating += inputs.frame_strength * 8.0
    rating += inputs.design_strength
    rating += (
        inputs.tech_components * 2.0
        + inputs.tech_materials * 2.0
        + inputs.tech_technology * 2.0
        + inputs.tech_techniques * 2.0
    ) / 2.0
    rating += inputs.fd_length

    rating /= 2.6
    rating *= 10.0
    rating += 10.0 * (inputs.marque_design_chassis_skill / 100.0)
    return clamp(rating)


def calculate_durability_rating(inputs: ChassisFormulaInputs) -> float:
    """Calculate chassis durability rating."""
    rating = inputs.design_dependability * 0.5
    rating += inputs.drivetrain_durability * 1.5
    rating += inputs.frame_durability * 1.5
    rating += (
        inputs.front_suspension_durability + inputs.rear_suspension_durability
    ) / 2.0
    rating += inputs.sus_durability * 2.5
    rating += (
        inputs.tech_components
        + inputs.tech_materials
        + inputs.tech_techniques
        - inputs.tech_technology
    )

    rating *= 10.0
    rating += 10.0 * (inputs.marque_design_chassis_skill / 100.0)
    return clamp(rating)


def calculate_overall_rating(
    comfort: float,
    performance: float,
    strength: float,
    durability: float,
    inputs: ChassisFormulaInputs,
) -> float:
    """Calculate overall chassis rating."""
    overall = (
        comfort
        + performance
        + strength
        + durability
        + inputs.marque_design_chassis_skill
    ) / 5.0
    overall += 5.0 * inputs.pre_research_chassis_amount_effect
    return clamp(overall)


def calculate_design_requirements(inputs: ChassisFormulaInputs) -> float:
    """Calculate chassis design requirements."""
    design_req = (
        inputs.design_control
        + inputs.design_dependability
        + inputs.design_performance
        + inputs.design_strength
        + inputs.drivetrain_design
        + inputs.frame_design
        + inputs.front_suspension_design
        + inputs.rear_suspension_design
    )
    design_req += (
        inputs.fd_engine_length
        + inputs.fd_engine_width
        + (1.0 - inputs.fd_weight)
        + inputs.sus_braking
        + inputs.sus_comfort
        + inputs.sus_durability
        + inputs.sus_performance
        + inputs.tech_technology
    ) / 4.0
    return (design_req - inputs.tech_techniques) * 10.0


def calculate_manufacturing_requirements(inputs: ChassisFormulaInputs) -> float:
    """Calculate chassis manufacturing requirements."""
    manufacturing_req = (
        inputs.frame_weight / 2.0
        + inputs.sus_durability
        + inputs.design_dependability
        + inputs.tech_components
        + inputs.tech_materials
        + inputs.tech_technology
        + inputs.tech_techniques * 1.5
        + inputs.frame_manufacturing
        + inputs.drivetrain_manufacturing
        + inputs.front_suspension_manufacturing
        + inputs.rear_suspension_manufacturing
    )
    return manufacturing_req * 10.0 + 0.01


def _collect_warnings(
    inputs: ChassisFormulaInputs,
    result: ChassisFormulaResult,
) -> list[str]:
    """Build practical warnings for a chassis design."""
    warnings: list[str] = []
    if inputs.year <= 1920 and result.chassis_weight > 280:
        warnings.append(
            "Chassis weight is very high for early years; verify frame dimensions."
        )
    if result.max_engine_width < 22 or result.max_engine_length < 22:
        warnings.append(
            "Engine bay is very small; many engines may not fit."
        )
    if result.durability_rating < 20:
        warnings.append("Durability rating is very low.")
    if result.strength_rating < 20:
        warnings.append("Strength rating is very low.")
    if inputs.design_performance > 0.5 and result.performance_rating < 20:
        warnings.append(
            "Performance rating is very low for a performance-oriented design."
        )
    return warnings


def calculate_chassis(inputs: ChassisFormulaInputs) -> ChassisFormulaResult:
    """Calculate all implemented chassis specs and ratings."""
    chassis_length = calculate_chassis_length(inputs)
    chassis_width = calculate_chassis_width(inputs)
    chassis_weight = calculate_chassis_weight(inputs)
    max_engine_length = calculate_max_engine_length(inputs)
    max_engine_width = calculate_max_engine_width(inputs)
    comfort = calculate_comfort_rating(inputs)
    performance = calculate_performance_rating(inputs)
    strength = calculate_strength_rating(inputs)
    durability = calculate_durability_rating(inputs)
    overall = calculate_overall_rating(
        comfort, performance, strength, durability, inputs
    )
    design = calculate_design_requirements(inputs)
    manufacturing = calculate_manufacturing_requirements(inputs)

    result = ChassisFormulaResult(
        chassis_length=chassis_length,
        chassis_width=chassis_width,
        chassis_weight=chassis_weight,
        max_engine_length=max_engine_length,
        max_engine_width=max_engine_width,
        comfort_rating=comfort,
        performance_rating=performance,
        strength_rating=strength,
        durability_rating=durability,
        overall_rating=overall,
        design_requirements=design,
        manufacturing_requirements=manufacturing,
        warnings=[],
    )
    result.warnings = _collect_warnings(inputs, result)
    return result


def _row_to_inputs(row: pd.Series) -> ChassisFormulaInputs:
    """Convert one CSV row to chassis formula inputs."""
    kwargs: dict[str, Any] = {"name": str(row["name"])}
    for field in fields(ChassisFormulaInputs):
        if field.name == "name":
            continue
        raw = row.get(field.name)
        if field.type is int:
            kwargs[field.name] = int(raw)
        else:
            kwargs[field.name] = float(raw)
    return ChassisFormulaInputs(**kwargs)


def load_chassis_formula_inputs(path: str) -> list[ChassisFormulaInputs]:
    """Load chassis formula input rows from CSV."""
    df = pd.read_csv(path)
    return [_row_to_inputs(row) for _, row in df.iterrows()]


def export_chassis_candidates_csv(
    inputs_list: list[ChassisFormulaInputs],
    output_path: str,
    year_override: int | None = None,
) -> None:
    """Export formula results to package-optimizer-compatible chassis CSV."""
    records = []
    for inputs in inputs_list:
        if year_override is not None:
            inputs = replace(inputs, year=year_override)
        result = calculate_chassis(inputs)
        records.append(
            {
                "name": inputs.name,
                "comfort": round(result.comfort_rating, 2),
                "performance": round(result.performance_rating, 2),
                "strength": round(result.strength_rating, 2),
                "durability": round(result.durability_rating, 2),
                "overall": round(result.overall_rating, 2),
                "unit_cost": 0,
                "design_cost": 0,
                "weight": round(result.chassis_weight, 2),
                "max_engine_width": round(result.max_engine_width, 2),
                "max_engine_length": round(result.max_engine_length, 2),
                "notes": "generated from chassis formula",
            }
        )
    pd.DataFrame(records).to_csv(output_path, index=False)
