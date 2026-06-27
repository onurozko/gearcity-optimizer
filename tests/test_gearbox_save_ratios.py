"""Tests for save-game gearbox ratio normalization."""

from __future__ import annotations

import pytest

from gearcity_optimizer.formulas.gearbox_formula import (
    GearboxFormulaInputs,
    calculate_max_torque_support,
    normalize_save_gear_ratios,
    save_unset_gear_ratio_torque_bonus,
    year_factor,
    TORQUE_YEAR_BASE,
)


def test_normalize_save_gear_ratios_maps_max_hi_to_zero():
    low, high = normalize_save_gear_ratios(0.0, 1.0)
    assert low == 0.0
    assert high == 0.0


def test_normalize_save_gear_ratios_maps_both_max_to_zero():
    low, high = normalize_save_gear_ratios(1.0, 1.0)
    assert low == 0.0
    assert high == 0.0


def test_save_unset_gear_ratio_bonus_only_when_both_zero():
    assert save_unset_gear_ratio_torque_bonus(0.0, 0.0, 1906) > 0.0
    assert save_unset_gear_ratio_torque_bonus(0.0, 1.0, 1906) == 0.0


def test_duplicate_tech_components_term_in_max_torque():
    inputs = GearboxFormulaInputs(
        year=1906,
        number_of_gears=7,
        low_gear_ratio=0.0,
        high_gear_ratio=0.0,
        torque_max_input=1.0,
        tech_components=0.3,
        design_dependability=0.3,
    )
    yf = year_factor(TORQUE_YEAR_BASE, 1906)
    expected = (
        10 * 7
        + 75 * yf * 1.0
        + 35 * yf
        + 15 * yf
        + 5 * yf * 0.3
        + 10 * yf * 0.3
    )
    assert calculate_max_torque_support(inputs) == pytest.approx(expected)
