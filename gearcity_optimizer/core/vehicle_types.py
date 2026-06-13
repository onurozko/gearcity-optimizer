"""Vehicle type CSV loading."""

from __future__ import annotations

import pandas as pd

from gearcity_optimizer.core.models import VehicleType, _parse_bool


def load_vehicle_types(path: str) -> dict[str, VehicleType]:
    """Load vehicle types from a CSV file, keyed by name."""
    df = pd.read_csv(path)
    vehicle_types: dict[str, VehicleType] = {}

    for _, row in df.iterrows():
        name = str(row["vehicle_type"])
        vehicle_types[name] = VehicleType(
            name=name,
            performance=float(row["performance"]),
            drivability=float(row["drivability"]),
            luxury=float(row["luxury"]),
            safety=float(row["safety"]),
            fuel=float(row["fuel"]),
            power=float(row["power"]),
            cargo=float(row["cargo"]),
            dependability=float(row["dependability"]),
            wealth_demo=int(row["wealth_demo"]),
            military_fleet=_parse_bool(row["military_fleet"]),
            civilian_fleet=_parse_bool(row["civilian_fleet"]),
        )

    return vehicle_types
