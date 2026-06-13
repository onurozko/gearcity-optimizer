"""Data models and candidate design CSV loading."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass
class VehicleType:
    """GearCity vehicle type with importance weights for each rating."""

    name: str
    performance: float
    drivability: float
    luxury: float
    safety: float
    fuel: float
    power: float
    cargo: float
    dependability: float
    wealth_demo: int
    military_fleet: bool
    civilian_fleet: bool


@dataclass
class CandidateDesign:
    """A candidate vehicle design with ratings and optional engineering fields."""

    name: str
    vehicle_type: str
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
    unit_cost: float
    design_cost: float
    sale_price: float | None = None
    top_speed_kph: float | None = None
    engine_torque: float | None = None
    gearbox_max_torque: float | None = None
    engine_smoothness: float | None = None
    notes: str | None = None


@dataclass
class ScoreResult:
    """Computed scores and warnings for a candidate against a vehicle type."""

    vehicle_type_fit: float
    buyer_rating_proxy_before_penalties: float
    final_buyer_rating_proxy: float
    value_per_cost: float
    penalty_multiplier: float
    warnings: list[str]


RATING_ATTRIBUTES = (
    "performance",
    "drivability",
    "luxury",
    "safety",
    "fuel",
    "power",
    "cargo",
    "dependability",
)


def _parse_bool(value: Any) -> bool:
    """Parse boolean values from CSV cells."""
    if isinstance(value, bool):
        return value
    if pd.isna(value):
        return False
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no", ""}:
        return False
    raise ValueError(f"Cannot parse boolean value: {value!r}")


def _parse_optional_float(value: Any) -> float | None:
    """Parse optional float fields; empty cells become None."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if text == "":
        return None
    return float(text)


def _parse_optional_str(value: Any) -> str | None:
    """Parse optional string fields; empty cells become None."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text if text else None


def load_candidate_designs(path: str) -> list[CandidateDesign]:
    """Load candidate designs from a CSV file."""
    df = pd.read_csv(path)
    candidates: list[CandidateDesign] = []

    for _, row in df.iterrows():
        candidates.append(
            CandidateDesign(
                name=str(row["name"]),
                vehicle_type=str(row["vehicle_type"]),
                performance=float(row["performance"]),
                drivability=float(row["drivability"]),
                luxury=float(row["luxury"]),
                safety=float(row["safety"]),
                fuel=float(row["fuel"]),
                power=float(row["power"]),
                cargo=float(row["cargo"]),
                dependability=float(row["dependability"]),
                quality=float(row["quality"]),
                overall=float(row["overall"]),
                unit_cost=float(row["unit_cost"]),
                design_cost=float(row["design_cost"]),
                sale_price=_parse_optional_float(row.get("sale_price")),
                top_speed_kph=_parse_optional_float(row.get("top_speed_kph")),
                engine_torque=_parse_optional_float(row.get("engine_torque")),
                gearbox_max_torque=_parse_optional_float(row.get("gearbox_max_torque")),
                engine_smoothness=_parse_optional_float(row.get("engine_smoothness")),
                notes=_parse_optional_str(row.get("notes")),
            )
        )

    return candidates
