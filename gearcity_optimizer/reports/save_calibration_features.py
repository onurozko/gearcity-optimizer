"""Shared feature extraction for save calibration analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gearcity_optimizer.reports.save_calibration import (
        EngineCalibrationResult,
        GearboxCalibrationResult,
    )

ENGINE_SEGMENT_COLS = (
    "fuel_family",
    "layout",
    "valve_family",
    "mod_bucket",
)
GEARBOX_SEGMENT_COLS = (
    "mod_bucket",
    "ratio_pattern",
    "gears",
)


def fuel_family(fuel_type: str) -> str:
    text = fuel_type.lower()
    if "electric" in text or "hybrid" in text:
        return "electric/hybrid"
    if "steam" in text:
        return "steam"
    if "diesel" in text:
        return "diesel"
    if "gas" in text:
        return "gasoline"
    return fuel_type or "unknown"


def valve_family(valve: str) -> str:
    text = valve.lower()
    if "dohc" in text:
        return "DOHC"
    if "sohc" in text:
        return "SOHC"
    if "f head" in text or "flat" in text:
        return "F Head"
    if "ohv" in text:
        return "OHV"
    if "l head" in text:
        return "L Head"
    return valve or "unknown"


def mod_bucket(mod_amount: int) -> str:
    if mod_amount <= 0:
        return "mod=0"
    if mod_amount <= 2:
        return "mod=1-2"
    return "mod=3+"


def gearbox_ratio_pattern(low_ratio: float, high_ratio: float) -> str:
    if low_ratio == 0.0 and high_ratio == 0.0:
        return "lo0_hi0"
    if high_ratio >= 0.999:
        return "hi_max"
    if low_ratio >= 0.999 and high_ratio >= 0.999:
        return "lo1_hi1"
    return "mid"


def delta_map(deltas: tuple) -> dict[str, float | None]:
    return {delta.metric: delta.pct_error for delta in deltas}


def signed_pct_error(game_value: float, predicted_value: float) -> float | None:
    if abs(game_value) <= 1e-6:
        return None
    return (predicted_value - game_value) / abs(game_value) * 100.0


def engine_fit_max_pct(result: EngineCalibrationResult) -> float:
    deltas = delta_map(result.deltas)
    return max(
        deltas.get("length_in") or 0.0,
        deltas.get("width_in") or 0.0,
        deltas.get("torque_lbft") or 0.0,
    )


def hp_torque_rpm_inconsistent(horsepower: float, torque_lbft: float, rpm: float) -> bool:
    if horsepower <= 0 or torque_lbft <= 0 or rpm <= 0:
        return False
    implied_hp = torque_lbft * rpm / 5252.0
    return abs(implied_hp - horsepower) / horsepower > 0.05


def reliability_stale(static_value: float, live_value: float) -> bool:
    if static_value <= 0:
        return False
    return abs(live_value - static_value) / static_value > 0.35


def stale_gearbox_power_rating(result: GearboxCalibrationResult) -> bool:
    deltas = delta_map(result.deltas)
    power_err = deltas.get("power_rating") or 0.0
    return power_err > 100.0 and result.record.power_rating > 0
