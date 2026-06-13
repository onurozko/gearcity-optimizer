"""Component candidate data models and CSV loading."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from gearcity_optimizer.core.models import _parse_optional_float, _parse_optional_str


@dataclass
class ChassisCandidate:
    """A chassis design candidate with ratings and optional dimensions."""

    name: str
    comfort: float
    performance: float
    strength: float
    durability: float
    overall: float
    unit_cost: float
    design_cost: float = 0
    weight: float | None = None
    max_engine_width: float | None = None
    max_engine_length: float | None = None
    notes: str | None = None


@dataclass
class EngineCandidate:
    """An engine design candidate with ratings and optional dimensions."""

    name: str
    horsepower: float
    torque: float
    fuel_economy: float
    reliability: float
    smoothness: float
    overall: float
    unit_cost: float
    design_cost: float = 0
    weight: float | None = None
    width: float | None = None
    length: float | None = None
    notes: str | None = None


@dataclass
class GearboxCandidate:
    """A gearbox design candidate with ratings and optional torque limit."""

    name: str
    power: float
    fuel_economy: float
    performance: float
    reliability: float
    comfort: float
    overall: float
    unit_cost: float
    design_cost: float = 0
    max_torque: float | None = None
    weight: float | None = None
    gears: int | None = None
    notes: str | None = None


@dataclass
class ComponentPriority:
    """Priority for a single component stat derived from vehicle type weights."""

    component: str
    stat: str
    priority: float
    reasons: list[str]


@dataclass
class ComponentFitResult:
    """Fit score for a single component against a vehicle type."""

    name: str
    component: str
    fit_score: float
    value_score: float
    unit_cost: float
    warnings: list[str]
    reasons: list[str]
    fit_debug: dict | None = None
    proxy_cost_used: bool = False


@dataclass
class ComponentPackageResult:
    """Combined chassis + engine + gearbox package evaluation."""

    chassis_name: str
    engine_name: str
    gearbox_name: str
    package_score: float
    package_value_score: float
    total_unit_cost: float
    warnings: list[str]
    chassis_fit: float
    engine_fit: float
    gearbox_fit: float
    chassis_reasons: list[str] | None = None
    engine_reasons: list[str] | None = None
    gearbox_reasons: list[str] | None = None
    fit_debug: dict | None = None
    proxy_cost_used: bool = False
    component_package_score: float | None = None
    assembly_vehicle_type_fit: float | None = None
    assembly_overall: float | None = None
    assembly_quality: float | None = None
    final_formula_fit_score: float | None = None


def _parse_optional_int(value: Any) -> int | None:
    """Parse optional integer fields; empty cells become None."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if text == "":
        return None
    return int(float(text))


def load_chassis_candidates(path: str) -> list[ChassisCandidate]:
    """Load chassis candidates from a CSV file."""
    df = pd.read_csv(path)
    candidates: list[ChassisCandidate] = []

    for _, row in df.iterrows():
        candidates.append(
            ChassisCandidate(
                name=str(row["name"]),
                comfort=float(row["comfort"]),
                performance=float(row["performance"]),
                strength=float(row["strength"]),
                durability=float(row["durability"]),
                overall=float(row["overall"]),
                unit_cost=float(row["unit_cost"]),
                design_cost=float(row.get("design_cost", 0) or 0),
                weight=_parse_optional_float(row.get("weight")),
                max_engine_width=_parse_optional_float(row.get("max_engine_width")),
                max_engine_length=_parse_optional_float(
                    row.get("max_engine_length")
                ),
                notes=_parse_optional_str(row.get("notes")),
            )
        )

    return candidates


def load_engine_candidates(path: str) -> list[EngineCandidate]:
    """Load engine candidates from a CSV file."""
    df = pd.read_csv(path)
    candidates: list[EngineCandidate] = []

    for _, row in df.iterrows():
        candidates.append(
            EngineCandidate(
                name=str(row["name"]),
                horsepower=float(row["horsepower"]),
                torque=float(row["torque"]),
                fuel_economy=float(row["fuel_economy"]),
                reliability=float(row["reliability"]),
                smoothness=float(row["smoothness"]),
                overall=float(row["overall"]),
                unit_cost=float(row["unit_cost"]),
                design_cost=float(row.get("design_cost", 0) or 0),
                weight=_parse_optional_float(row.get("weight")),
                width=_parse_optional_float(row.get("width")),
                length=_parse_optional_float(row.get("length")),
                notes=_parse_optional_str(row.get("notes")),
            )
        )

    return candidates


def load_gearbox_candidates(path: str) -> list[GearboxCandidate]:
    """Load gearbox candidates from a CSV file."""
    df = pd.read_csv(path)
    candidates: list[GearboxCandidate] = []

    for _, row in df.iterrows():
        candidates.append(
            GearboxCandidate(
                name=str(row["name"]),
                power=float(row["power"]),
                fuel_economy=float(row["fuel_economy"]),
                performance=float(row["performance"]),
                reliability=float(row["reliability"]),
                comfort=float(row["comfort"]),
                overall=float(row["overall"]),
                unit_cost=float(row["unit_cost"]),
                design_cost=float(row.get("design_cost", 0) or 0),
                max_torque=_parse_optional_float(row.get("max_torque")),
                weight=_parse_optional_float(row.get("weight")),
                gears=_parse_optional_int(row.get("gears")),
                notes=_parse_optional_str(row.get("notes")),
            )
        )

    return candidates
