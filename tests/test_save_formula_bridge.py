"""Tests for save-specific formula bridge adjustments."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from gearcity_optimizer.reports.save_formula_bridge import (
    apply_save_engine_physical_adjustments,
    engine_save_formula_supported,
    save_gearbox_max_torque_multiplier,
)


@dataclass
class _PredictedEngine:
    torque: float = 300.0
    length: float = 60.0
    width: float = 45.0
    horsepower: float = 220.0


@dataclass
class _EngineRecord:
    fuel_type: str = "Gasoline"
    mod_amount: int = 0
    layout: str = "W"
    valve: str = "DOHC"
    low_ratio: float = 0.0
    high_ratio: float = 0.0
    mod_amount_gb: int = 0


def test_unmodded_w_dohc_scales_torque_only():
    record = _EngineRecord()
    predicted = apply_save_engine_physical_adjustments(_PredictedEngine(), record)
    scale = 1.0 / 1.178
    assert predicted.torque == pytest.approx(300.0 * scale, rel=1e-3)
    assert predicted.length == 60.0
    assert predicted.width == 45.0


def test_modded_w_dohc_is_not_adjusted():
    record = _EngineRecord(mod_amount=2)
    predicted = apply_save_engine_physical_adjustments(_PredictedEngine(), record)
    assert predicted.torque == 300.0


def test_electric_engine_not_supported():
    record = _EngineRecord(fuel_type="Electric Hybrid")
    assert engine_save_formula_supported(record) is False


def test_gearbox_mod3_hi_max_multiplier():
    @dataclass
    class _GearboxRecord:
        mod_amount: int = 3
        low_ratio: float = 0.2
        high_ratio: float = 1.0

    assert save_gearbox_max_torque_multiplier(_GearboxRecord()) == pytest.approx(
        1.0 / (1.0 - 0.2653),
        rel=1e-3,
    )


def test_gearbox_mod0_has_no_multiplier():
    @dataclass
    class _GearboxRecord:
        mod_amount: int = 0
        low_ratio: float = 0.0
        high_ratio: float = 0.0

    assert save_gearbox_max_torque_multiplier(_GearboxRecord()) == 1.0
