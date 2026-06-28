"""Tests for normalized save calibration datasets and export pipeline."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from gearcity_optimizer.cli.main import main
from gearcity_optimizer.reports.save_calibration import calibrate_save_game
from gearcity_optimizer.reports.save_calibration_dataset import (
    build_calibration_frames,
    build_save_dataset_pipeline,
    engine_dataset_columns,
    export_calibration_dataset,
    gearbox_dataset_columns,
    metrics_long_frame,
)
from gearcity_optimizer.reports.save_dataset_residuals import (
    build_residual_correction_tables,
    formula_error_summary,
    year_band,
)


def test_engine_dataset_columns_are_stable():
    columns = engine_dataset_columns()
    assert columns.index("year") < columns.index("layout")
    assert "actual_horsepower" in columns
    assert "predicted_horsepower" in columns
    assert "error_horsepower" in columns
    assert "pct_error_horsepower" in columns
    assert "calibration_mode" in columns
    assert "slider_torque" in columns
    assert "actual_rpm" in columns
    assert "actual_mpg" in columns
    assert "actual_length" in columns


def test_gearbox_dataset_columns_are_stable():
    columns = gearbox_dataset_columns()
    assert columns.index("year") < columns.index("gears")
    assert "actual_max_torque" in columns
    assert "predicted_max_torque" in columns
    assert "error_max_torque" in columns
    assert "pct_error_max_torque" in columns
    assert "limited_slip" in columns
    assert "sub_performance" in columns


def test_build_calibration_frames_includes_replay_columns(sample_save_db: Path):
    report = calibrate_save_game(str(sample_save_db), company_id=0)
    engine_df, gearbox_df = build_calibration_frames([report], save_labels=["sample.db"])

    assert list(engine_df.columns) == list(engine_dataset_columns())
    assert list(gearbox_df.columns) == list(gearbox_dataset_columns())
    assert engine_df.iloc[0]["actual_horsepower"] == pytest.approx(223.0)
    assert engine_df.iloc[0]["predicted_horsepower"] > 0
    assert engine_df.iloc[0]["error_horsepower"] >= 0
    assert engine_df.iloc[0]["pct_error_horsepower"] is not None
    assert gearbox_df.iloc[0]["actual_max_torque"] == pytest.approx(312.0)
    assert gearbox_df.iloc[0]["predicted_max_torque"] > 0


def test_formula_replay_columns_match_legacy_err_columns(sample_save_db: Path):
    report = calibrate_save_game(str(sample_save_db), company_id=0)
    engine_df, gearbox_df = build_calibration_frames([report])

    row = engine_df.iloc[0]
    assert row["pct_error_torque"] == pytest.approx(row["err_torque_pct"])
    assert row["pct_error_horsepower"] == pytest.approx(row["err_horsepower_pct"])

    gb_row = gearbox_df.iloc[0]
    assert gb_row["pct_error_max_torque"] == pytest.approx(gb_row["err_max_torque_pct"])


def test_export_calibration_dataset_writes_csv(sample_save_db: Path, tmp_path: Path):
    report = calibrate_save_game(str(sample_save_db), company_id=0)
    paths = export_calibration_dataset([report], tmp_path / "out")

    assert paths["engines"].exists()
    assert paths["gearboxes"].exists()
    assert paths["metrics_long"].exists()
    engines = pd.read_csv(paths["engines"])
    assert "actual_horsepower" in engines.columns
    assert len(engines) == 1


def test_build_save_dataset_pipeline_exports_artifacts(sample_save_db: Path, tmp_path: Path):
    result = build_save_dataset_pipeline(
        [sample_save_db],
        company_id=0,
        output_dir=tmp_path / "datasets",
        apply_corrections=False,
        min_correction_count=1,
    )

    paths = result["paths"]
    assert paths["engines"].exists()
    assert paths["gearboxes"].exists()
    assert paths["formula_error_summary"].exists()
    assert paths["worst_prediction_gaps"].exists()
    assert paths["schema_summary"].exists()
    assert result["engine_df"].iloc[0]["calibration_mode"] == "formula_only"


def test_residual_corrections_require_enough_rows():
    engine_df = pd.DataFrame(
        {
            "save": ["a", "a", "a"],
            "design_id": [1, 2, 3],
            "year": [1906, 1906, 1906],
            "layout": ["W", "W", "W"],
            "fuel_type": ["Gasoline", "Gasoline", "Gasoline"],
            "actual_torque": [100.0, 110.0, 120.0],
            "predicted_torque": [80.0, 88.0, 96.0],
            "error_torque": [20.0, 22.0, 24.0],
            "pct_error_torque": [20.0, 20.0, 20.0],
            "signed_torque_pct": [25.0, 25.0, 25.0],
        }
    )
    gearbox_df = pd.DataFrame()
    engine_corr, gearbox_corr = build_residual_correction_tables(
        engine_df,
        gearbox_df,
        min_count=3,
        min_abs_signed_pct=1.0,
    )
    assert len(engine_corr) == 1
    assert gearbox_corr.empty


def test_year_band_groups_by_decade():
    assert year_band(1906) == "1900-1909"
    assert year_band("1925") == "1920-1929"


def test_formula_error_summary_from_frames(sample_save_db: Path):
    report = calibrate_save_game(str(sample_save_db), company_id=0)
    engine_df, gearbox_df = build_calibration_frames([report])
    summary = formula_error_summary(engine_df, gearbox_df)
    assert not summary.empty
    assert set(summary["kind"]) <= {"engine", "gearbox"}


def test_metrics_long_frame_still_works(sample_save_db: Path):
    report = calibrate_save_game(str(sample_save_db), company_id=0)
    engine_df, gearbox_df = build_calibration_frames([report])
    long_df = metrics_long_frame(engine_df, gearbox_df)
    assert not long_df.empty


def test_inspect_save_cli(sample_save_db: Path, capsys):
    exit_code = main(["inspect-save", "--save", str(sample_save_db)])
    assert exit_code == 0
    captured = capsys.readouterr().out
    assert "Table: EngineInfo" in captured


def test_build_save_datasets_cli(sample_save_db: Path, tmp_path: Path, capsys):
    out_dir = tmp_path / "cli_out"
    exit_code = main(
        [
            "build-save-datasets",
            "--save",
            str(sample_save_db),
            "--output",
            str(out_dir),
            "--no-corrections",
            "--min-count",
            "1",
        ]
    )
    assert exit_code == 0
    captured = capsys.readouterr().out
    assert "Save dataset pipeline" in captured
    assert (out_dir / "engines.csv").exists()
