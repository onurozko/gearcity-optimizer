"""Save-specific formula adjustments discovered via mass calibration."""

from __future__ import annotations

from dataclasses import replace

from gearcity_optimizer.importers.save_db import SaveEngineRecord, SaveGearboxRecord
from gearcity_optimizer.reports.save_calibration_features import (
    fuel_family,
    gearbox_ratio_pattern,
    valve_family,
)

# Unmodded W/DOHC gas engines over-predict physical stats vs modded rows in saves.
_UNMODDED_W_DOHC_PHYSICAL_SCALE = 1.0 / 1.178

# Save ModAmount>=3 uplifts max torque beyond wiki replay, strongest at hi_max ratios.
_GEARBOX_MOD3_HI_MAX_TORQUE_SCALE = 1.0 / (1.0 - 0.2653)
_GEARBOX_MOD3_TORQUE_SCALE = 1.0 / (1.0 - 0.0888)


def engine_save_formula_supported(record: SaveEngineRecord) -> bool:
    return fuel_family(record.fuel_type) in {"gasoline", "diesel"}


def apply_save_engine_physical_adjustments(predicted: object, record: SaveEngineRecord) -> object:
    """Apply grouped save-calibration fixes to engine physical outputs."""
    if not engine_save_formula_supported(record):
        return predicted
    if record.mod_amount > 0:
        return predicted
    if record.layout != "W" or valve_family(record.valve) != "DOHC":
        return predicted

    scale = _UNMODDED_W_DOHC_PHYSICAL_SCALE
    return replace(
        predicted,
        torque=predicted.torque * scale,
        horsepower=predicted.horsepower * (1.0 / 1.08),
    )


def save_gearbox_max_torque_multiplier(record: SaveGearboxRecord) -> float:
    """Return a multiplier for save gearbox max torque from ModAmount and ratios."""
    if record.mod_amount < 3:
        return 1.0
    pattern = gearbox_ratio_pattern(record.low_ratio, record.high_ratio)
    if pattern == "hi_max":
        return _GEARBOX_MOD3_HI_MAX_TORQUE_SCALE
    return _GEARBOX_MOD3_TORQUE_SCALE
