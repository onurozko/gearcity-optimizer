"""Tests for save engine flag mapping."""

from __future__ import annotations

import pytest

from gearcity_optimizer.importers.save_engine_flags import engine_formula_flags_from_save


def test_dohc_sets_overhead_cam():
    flags = engine_formula_flags_from_save(valve="DOHC")
    assert flags["has_overhead_cam"] is True
    assert flags["wiki_valve_rpm"] == pytest.approx(1.30)


def test_gasoline_fuel_rpm_default():
    flags = engine_formula_flags_from_save(fuel_type="Gasoline")
    assert flags["wiki_fuel_rpm"] == pytest.approx(1.0)


def test_turbo_and_supercharger_flags():
    assert engine_formula_flags_from_save(induction="Supercharger")["is_supercharged"] is True
    assert engine_formula_flags_from_save(induction="Turbocharger")["is_turbocharged"] is True
    assert engine_formula_flags_from_save(induction="Twincharger")["is_turbocharged"] is False
