"""Tests for save dataset quality reports and prediction backends."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from gearcity_optimizer.prediction.backend import PredictionMode, SavePredictionBackend
from gearcity_optimizer.reports.save_calibration import calibrate_save_game
from gearcity_optimizer.reports.save_calibration_dataset import build_calibration_frames
from gearcity_optimizer.reports.save_dataset_quality import (
    build_dataset_quality_report,
    export_dataset_quality_report,
    load_generated_datasets,
)
from gearcity_optimizer.reports.save_dataset_residuals import (
    CorrectionLookupResult,
    ResidualCorrectionStore,
    annotate_correction_confidence,
    build_actual_vs_predicted_chart_data,
    confidence_from_count,
)


@pytest.fixture
def tiny_engine_csv(tmp_path: Path) -> Path:
    rows = [
        {
            "save": "sample.db",
            "kind": "engine",
            "design_id": 1,
            "name": "Engine A",
            "year": 1906,
            "layout": "W",
            "fuel_type": "Gasoline",
            "actual_torque": 100.0,
            "predicted_torque": 80.0,
            "error_torque": 20.0,
            "pct_error_torque": 20.0,
            "actual_horsepower": 200.0,
            "predicted_horsepower": 180.0,
            "error_horsepower": 20.0,
            "pct_error_horsepower": 10.0,
        },
        {
            "save": "sample.db",
            "kind": "engine",
            "design_id": 2,
            "name": "Engine B",
            "year": 1908,
            "layout": "W",
            "fuel_type": "Gasoline",
            "actual_torque": 110.0,
            "predicted_torque": 90.0,
            "error_torque": 20.0,
            "pct_error_torque": 18.18,
            "actual_horsepower": 210.0,
            "predicted_horsepower": 170.0,
            "error_horsepower": 40.0,
            "pct_error_horsepower": 19.05,
        },
        {
            "save": "sample.db",
            "kind": "engine",
            "design_id": 3,
            "name": "Engine C",
            "year": 1906,
            "layout": "I",
            "fuel_type": "Gasoline",
            "actual_torque": 120.0,
            "predicted_torque": 96.0,
            "error_torque": 24.0,
            "pct_error_torque": 20.0,
            "actual_horsepower": 220.0,
            "predicted_horsepower": 176.0,
            "error_horsepower": 44.0,
            "pct_error_horsepower": 20.0,
        },
    ]
    path = tmp_path / "engines.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


@pytest.fixture
def tiny_gearbox_csv(tmp_path: Path) -> Path:
    rows = [
        {
            "save": "sample.db",
            "kind": "gearbox",
            "design_id": 10,
            "name": "Gearbox A",
            "year": 1906,
            "gearbox_type": "Non-Synchronous",
            "actual_max_torque": 300.0,
            "predicted_max_torque": 250.0,
            "error_max_torque": 50.0,
            "pct_error_max_torque": 16.67,
        }
    ]
    path = tmp_path / "gearboxes.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


@pytest.fixture
def tiny_dataset_dir(tiny_engine_csv: Path, tiny_gearbox_csv: Path) -> Path:
    return tiny_engine_csv.parent


def test_confidence_labels():
    assert confidence_from_count(2) is None
    assert confidence_from_count(3) == "low"
    assert confidence_from_count(9) == "low"
    assert confidence_from_count(10) == "medium"
    assert confidence_from_count(29) == "medium"
    assert confidence_from_count(30) == "high"


def test_no_correction_when_sample_count_too_low():
    corrections = pd.DataFrame(
        [
            {
                "metric": "torque",
                "year_band": "1900-1909",
                "layout": "W",
                "fuel_type": "Gasoline",
                "count": 2,
                "mean_signed_pct": 25.0,
                "mean_abs_pct": 25.0,
                "suggested_scale": 0.8,
            }
        ]
    )
    store = ResidualCorrectionStore(engine_corrections=corrections)
    lookup = store.lookup_engine(
        metric="torque",
        year=1906,
        layout="W",
        fuel_type="Gasoline",
    )
    assert lookup.applied is False
    assert lookup.correction_value is None
    assert lookup.confidence is None
    assert lookup.sample_count == 2


def test_correction_metadata_is_returned():
    corrections = pd.DataFrame(
        [
            {
                "metric": "torque",
                "year_band": "1900-1909",
                "layout": "W",
                "fuel_type": "Gasoline",
                "count": 12,
                "mean_signed_pct": 25.0,
                "mean_abs_pct": 25.0,
                "suggested_scale": 0.8,
            }
        ]
    )
    annotated = annotate_correction_confidence(corrections)
    store = ResidualCorrectionStore(engine_corrections=annotated)
    lookup = store.lookup_engine(
        metric="torque",
        year=1906,
        layout="W",
        fuel_type="Gasoline",
    )
    assert lookup.applied is True
    assert lookup.correction_value == pytest.approx(0.8)
    assert lookup.sample_count == 12
    assert lookup.confidence == "medium"
    assert "layout=W" in (lookup.matched_group or "")


def test_build_dataset_quality_report_from_fixture_csvs(tiny_dataset_dir: Path):
    report = build_dataset_quality_report(tiny_dataset_dir)

    assert report.engine_row_count == 3
    assert report.gearbox_row_count == 1
    assert not report.metric_support.empty
    assert not report.metric_errors.empty
    assert not report.worst_errors.empty
    assert not report.chart_data.empty
    assert set(report.chart_data.columns) >= {
        "metric",
        "actual",
        "predicted",
        "error",
        "pct_error",
        "group_label",
    }


def test_export_dataset_quality_report_writes_files(tiny_dataset_dir: Path):
    report = build_dataset_quality_report(tiny_dataset_dir)
    paths = export_dataset_quality_report(report, tiny_dataset_dir / "quality_out")

    assert paths["quality_summary"].exists()
    assert paths["metric_errors"].exists()
    assert paths["chart_data"].exists()
    assert paths["calibration_confidence"].exists()


def test_chart_data_is_csv_friendly(tiny_dataset_dir: Path):
    engine_df, gearbox_df = load_generated_datasets(tiny_dataset_dir)
    chart = build_actual_vs_predicted_chart_data(engine_df, gearbox_df)
    assert len(chart) >= 4
    assert chart["actual"].notna().all()
    assert chart["predicted"].notna().all()


def test_formula_only_backend_works_without_generated_datasets(sample_save_db: Path):
    report = calibrate_save_game(str(sample_save_db), company_id=0, apply_corrections=False)
    engine_item = report.engines[0]
    backend = SavePredictionBackend.formula_only()
    result = backend.predict_engine(engine_item.record, engine_item.layout)

    assert result.mode == PredictionMode.FORMULA_ONLY.value
    assert result.predicted.horsepower > 0
    assert result.corrections_applied is False
    assert result.confidence is None


def test_save_calibrated_backend_falls_back_without_residual_tables(sample_save_db: Path):
    report = calibrate_save_game(str(sample_save_db), company_id=0, apply_corrections=False)
    engine_item = report.engines[0]
    backend = SavePredictionBackend.save_calibrated(datasets_dir="/nonexistent/generated/path")
    result = backend.predict_engine(engine_item.record, engine_item.layout)

    assert result.mode == PredictionMode.SAVE_CALIBRATED.value
    assert result.predicted.horsepower > 0


def test_save_calibrated_backend_applies_residual_when_available(
    sample_save_db: Path,
    tmp_path: Path,
):
    report = calibrate_save_game(str(sample_save_db), company_id=0, apply_corrections=False)
    engine_df, gearbox_df = build_calibration_frames([report])
    corrections = pd.DataFrame(
        [
            {
                "metric": "torque",
                "year_band": "1900-1909",
                "layout": engine_df.iloc[0]["layout"],
                "fuel_type": engine_df.iloc[0]["fuel_type"],
                "count": 10,
                "mean_signed_pct": 25.0,
                "mean_abs_pct": 25.0,
                "suggested_scale": 0.8,
                "confidence": "medium",
            }
        ]
    )
    corrections.to_csv(tmp_path / "engine_residual_corrections.csv", index=False)

    engine_item = report.engines[0]
    formula_only = SavePredictionBackend.formula_only().predict_engine(
        engine_item.record,
        engine_item.layout,
    )
    calibrated = SavePredictionBackend.save_calibrated(datasets_dir=tmp_path).predict_engine(
        engine_item.record,
        engine_item.layout,
    )

    lookup = ResidualCorrectionStore.from_datasets_dir(tmp_path).lookup_engine(
        metric="torque",
        year=engine_item.record.year_built,
        layout=engine_item.record.layout,
        fuel_type=engine_item.record.fuel_type,
    )
    assert isinstance(lookup, CorrectionLookupResult)
    assert lookup.applied is True
    assert calibrated.predicted.torque != formula_only.predicted.torque


def test_save_dataset_quality_cli(tiny_dataset_dir: Path, capsys):
    from gearcity_optimizer.cli.main import main

    exit_code = main(
        [
            "save-dataset-quality",
            "--input",
            str(tiny_dataset_dir),
        ]
    )
    assert exit_code == 0
    captured = capsys.readouterr().out
    assert "Save dataset quality report" in captured
    assert (tiny_dataset_dir / "quality_metric_errors.csv").exists()
