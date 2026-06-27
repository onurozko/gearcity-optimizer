"""Tests for bundled calibration correction loading."""

from __future__ import annotations

from gearcity_optimizer.reports.calibration_defaults import load_default_calibration_corrections


def test_default_corrections_load_and_filter_mod3_gearboxes():
    corrections = load_default_calibration_corrections()
    assert not any("mod_bucket=mod=3+" in key for key in corrections.gearbox)
    assert any("layout=I" in key for key in corrections.engine)
