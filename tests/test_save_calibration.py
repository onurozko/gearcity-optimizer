"""Tests for GearCity save game calibration against wiki formulas."""

from __future__ import annotations

from pathlib import Path

import pytest

from gearcity_optimizer.importers.save_db import load_save_game
from gearcity_optimizer.reports.save_calibration import (
    calibrate_engine_record,
    calibrate_gearbox_record,
    calibrate_save_game,
)
from gearcity_optimizer.reports.save_calibration_analysis import format_calibration_analysis


def test_load_save_game_reads_layout_and_engine(sample_save_db: Path):
    snapshot = load_save_game(sample_save_db, company_id=0)
    assert snapshot.current_year == 1906
    assert "W" in snapshot.layouts
    assert snapshot.layouts["W"].engine_length == pytest.approx(0.85)
    assert len(snapshot.engines) == 1
    assert snapshot.engines[0].engine_id == 707


def test_calibrate_engine_produces_metric_deltas(sample_save_db: Path):
    snapshot = load_save_game(sample_save_db, company_id=0)
    engine = snapshot.engines[0]
    result = calibrate_engine_record(engine, snapshot.layouts.get(engine.layout))
    metrics = {item.metric: item for item in result.deltas}
    assert "length_in" in metrics
    assert "torque_lbft" in metrics
    assert metrics["length_in"].game_value == pytest.approx(56.0)
    assert metrics["length_in"].abs_error < 5.0
    assert metrics["width_in"].abs_error < 5.0
    assert metrics["torque_lbft"].abs_error < 20.0
    assert metrics["horsepower"].pct_error is not None
    assert metrics["horsepower"].pct_error < 5.0
    assert metrics["weight_lb"].pct_error is not None
    assert metrics["weight_lb"].pct_error < 12.0


def test_calibrate_engine_notes_mod_and_stale_ratings(sample_save_db: Path):
    snapshot = load_save_game(sample_save_db, company_id=0)
    engine = snapshot.engines[0]
    result = calibrate_engine_record(engine, snapshot.layouts.get(engine.layout))
    joined = " ".join(result.notes)
    assert "ModAmount=2" in joined
    assert "static design-time ratings" in joined


def test_calibrate_save_game_report(sample_save_db: Path):
    report = calibrate_save_game(str(sample_save_db), company_id=0, engine_limit=5, gearbox_limit=5)
    assert len(report.engines) == 1
    assert len(report.gearboxes) == 1
    assert "length_in_mean_abs_error" in report.engine_summary


def test_calibrate_gearbox_matches_save_max_torque(sample_save_db: Path):
    snapshot = load_save_game(sample_save_db, company_id=0)
    gearbox = snapshot.gearboxes[0]
    result = calibrate_gearbox_record(gearbox)
    torque_delta = next(item for item in result.deltas if item.metric == "max_torque_lbft")
    assert torque_delta.pct_error is not None
    assert torque_delta.pct_error < 5.0


def test_format_calibration_analysis_runs(sample_save_db: Path):
    report = calibrate_save_game(
        str(sample_save_db), company_id=0, engine_limit=None, gearbox_limit=None
    )
    text = "\n".join(format_calibration_analysis(report))
    assert "Save-wide analysis" in text
    assert "Engine groups" in text
    assert "Gearbox groups" in text
