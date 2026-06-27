"""Tests for mass-scale save calibration segment corrections."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from gearcity_optimizer.importers.save_db import load_save_game
from gearcity_optimizer.reports.save_calibration import (
    calibrate_engine_record,
    calibrate_save_game,
)
from gearcity_optimizer.reports.save_calibration_corrections import (
    CalibrationCorrections,
    SegmentCorrection,
    corrections_from_dict,
    corrections_to_dict,
    engine_formula_supported,
    engine_segment_key,
    fit_calibration_corrections,
    load_calibration_corrections,
    mass_quality_summary,
    save_calibration_corrections,
    signed_pct_to_scale,
)
from gearcity_optimizer.reports.save_calibration_dataset import build_calibration_frames
from gearcity_optimizer.reports.save_calibration_research import run_calibration_fit


def test_signed_pct_to_scale():
    assert signed_pct_to_scale(17.8) == pytest.approx(1.0 / 1.178, rel=1e-3)


def test_fit_segment_corrections_from_synthetic_frame():
    engine_df = pd.DataFrame(
        {
            "fuel_family": ["gasoline", "gasoline"],
            "layout": ["W", "W"],
            "valve_family": ["DOHC", "DOHC"],
            "mod_bucket": ["mod=0", "mod=0"],
            "signed_torque_pct": [18.0, 16.0],
            "signed_horsepower_pct": [8.0, 8.0],
            "signed_length_pct": [18.0, 16.0],
            "signed_width_pct": [18.0, 16.0],
            "fit_max_pct": [18.0, 16.0],
            "err_torque_pct": [18.0, 16.0],
            "err_horsepower_pct": [8.0, 8.0],
        }
    )
    corrections = fit_calibration_corrections(engine_df, pd.DataFrame(), min_count=2)
    key = "fuel_family=gasoline|layout=W|valve_family=DOHC|mod_bucket=mod=0"
    assert key in corrections.engine
    assert corrections.engine[key].scales["torque"] == pytest.approx(signed_pct_to_scale(17.0), rel=1e-3)


def test_corrections_reduce_overpredicted_engine_torque(sample_save_db: Path):
    snapshot = load_save_game(sample_save_db, company_id=0)
    engine = snapshot.engines[0]
    layout = snapshot.layouts.get(engine.layout)
    before = calibrate_engine_record(engine, layout)
    before_torque = next(item for item in before.deltas if item.metric == "torque_lbft")
    if before_torque.predicted_value <= before_torque.game_value:
        pytest.skip("Sample engine is not over-predicting torque")

    scale = before_torque.game_value / before_torque.predicted_value
    corrections = CalibrationCorrections(
        engine={
            engine_segment_key(engine): SegmentCorrection(
                scales={"torque": scale, "horsepower": 1.0, "length": 1.0, "width": 1.0},
                count=2,
                level=0,
                mean_signed={"torque": 17.6},
            )
        }
    )
    after = calibrate_engine_record(engine, layout, corrections=corrections)
    after_torque = next(item for item in after.deltas if item.metric == "torque_lbft")
    assert after_torque.pct_error is not None
    assert after_torque.pct_error < 1.0


def test_corrections_json_roundtrip(tmp_path: Path):
    corrections = CalibrationCorrections(
        engine={
            "fuel_family=gasoline|layout=W|valve_family=DOHC|mod_bucket=mod=0": SegmentCorrection(
                scales={"torque": 0.85},
                count=2,
                level=0,
                mean_signed={"torque": 17.6},
            )
        }
    )
    path = save_calibration_corrections(tmp_path / "corrections.json", corrections)
    loaded = load_calibration_corrections(path)
    assert corrections_to_dict(loaded) == corrections_to_dict(corrections_from_dict(json.loads(path.read_text())))


def test_run_calibration_fit_writes_outputs(sample_save_db: Path, tmp_path: Path):
    result = run_calibration_fit(
        [str(sample_save_db)],
        company_id=0,
        output_dir=tmp_path / "fit",
        min_count=1,
        min_abs_signed_pct=0.0,
    )
    assert result["corrections_path"].exists()
    assert result["fit_report_path"].exists()
    assert "Before corrections" in "\n".join(result["fit_report_lines"])


def test_engine_formula_supported(sample_save_db: Path):
    snapshot = load_save_game(sample_save_db, company_id=0)
    assert engine_formula_supported(snapshot.engines[0]) is True


def test_mass_quality_summary_skips_unsupported():
    engine_df = pd.DataFrame(
        {
            "fuel_family": ["gasoline", "electric/hybrid"],
            "fit_max_pct": [4.0, 90.0],
            "err_torque_pct": [4.0, 90.0],
            "err_horsepower_pct": [4.0, 90.0],
        }
    )
    summary = mass_quality_summary(engine_df, pd.DataFrame(), supported_only=True)
    assert summary["engine_count"] == 1
    assert summary["unsupported_engine_count"] == 1
    fit_ok, fit_n = summary["engine_fit_within_5pct"]
    assert fit_ok == 1 and fit_n == 1
