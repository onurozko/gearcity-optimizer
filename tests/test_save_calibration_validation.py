"""Tests for holdout save calibration validation."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

from gearcity_optimizer.cli.main import main
from gearcity_optimizer.prediction.backend import SavePredictionBackend
from gearcity_optimizer.reports.save_calibration_validation import (
    build_train_correction_store,
    classify_metric_status,
    collect_save_paths,
    compute_metric_comparison,
    evaluate_holdout_predictions,
    export_holdout_validation,
    run_holdout_validation,
)
from gearcity_optimizer.reports.save_dataset_residuals import (
    ResidualCorrectionStore,
    build_residual_correction_tables,
)


@pytest.fixture
def holdout_train_db(sample_save_db: Path, tmp_path: Path) -> Path:
    path = tmp_path / "train-save.db"
    shutil.copy(sample_save_db, path)
    return path


@pytest.fixture
def holdout_test_db(sample_save_db: Path, tmp_path: Path) -> Path:
    path = tmp_path / "test-save.db"
    shutil.copy(sample_save_db, path)
    return path


def test_collect_save_paths_from_dir(sample_save_db: Path, tmp_path: Path):
    directory = tmp_path / "saves"
    directory.mkdir()
    shutil.copy(sample_save_db, directory / "a.db")
    paths = collect_save_paths(save_dir=directory)
    assert len(paths) == 1
    assert paths[0].name == "a.db"


def test_train_test_overlap_rejected(holdout_train_db: Path):
    with pytest.raises(ValueError, match="must not overlap"):
        run_holdout_validation([holdout_train_db], [holdout_train_db])


def test_no_correction_built_from_test_data(
    holdout_train_db: Path,
    holdout_test_db: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    seen_train_saves: list[str] = []
    original = build_residual_correction_tables

    def tracked(engine_df, gearbox_df, **kwargs):
        seen_train_saves.extend(engine_df["save"].unique().tolist())
        return original(engine_df, gearbox_df, **kwargs)

    monkeypatch.setattr(
        "gearcity_optimizer.reports.save_calibration_validation.build_residual_correction_tables",
        tracked,
    )
    run_holdout_validation([holdout_train_db], [holdout_test_db], min_count=1)
    assert "train-save.db" in seen_train_saves
    assert "test-save.db" not in seen_train_saves


def test_formula_fallback_when_correction_missing(holdout_test_db: Path):
    empty_store = ResidualCorrectionStore()
    eval_rows, fallback_count = evaluate_holdout_predictions(
        [holdout_test_db],
        residual_store=empty_store,
    )
    assert not eval_rows.empty
    assert fallback_count > 0
    assert eval_rows["used_formula_fallback"].all()
    assert (eval_rows["formula_only"] == eval_rows["save_calibrated"]).all()


def test_improvement_calculation():
    eval_rows = pd.DataFrame(
        [
            {
                "kind": "engine",
                "metric": "torque",
                "formula_only_abs_error": 10.0,
                "save_calibrated_abs_error": 7.0,
                "formula_only_pct_error": 20.0,
                "save_calibrated_pct_error": 14.0,
            },
            {
                "kind": "engine",
                "metric": "torque",
                "formula_only_abs_error": 8.0,
                "save_calibrated_abs_error": 5.0,
                "formula_only_pct_error": 16.0,
                "save_calibrated_pct_error": 10.0,
            },
        ]
    )
    comparison = compute_metric_comparison(eval_rows)
    row = comparison.iloc[0]
    assert row["formula_only_mae"] == pytest.approx(9.0)
    assert row["save_calibrated_mae"] == pytest.approx(6.0)
    assert row["absolute_improvement"] == pytest.approx(3.0)
    assert row["improvement_pct"] == pytest.approx(100.0 * 3.0 / 9.0)
    assert row["status"] == "improved"


def test_status_classification():
    assert classify_metric_status(sample_count=0, formula_only_mae=1.0, save_calibrated_mae=0.5) == "insufficient_data"
    assert classify_metric_status(sample_count=5, formula_only_mae=10.0, save_calibrated_mae=8.0) == "improved"
    assert classify_metric_status(sample_count=5, formula_only_mae=8.0, save_calibrated_mae=10.0) == "worse"
    assert classify_metric_status(sample_count=5, formula_only_mae=5.0, save_calibrated_mae=5.0) == "unchanged"


def test_holdout_backend_uses_train_store_only(holdout_test_db: Path):
    store = ResidualCorrectionStore(
        engine_corrections=pd.DataFrame(
            [
                {
                    "metric": "torque",
                    "year_band": "1900-1909",
                    "layout": "W",
                    "fuel_type": "Gasoline",
                    "count": 10,
                    "mean_signed_pct": 25.0,
                    "mean_abs_pct": 25.0,
                    "suggested_scale": 0.8,
                    "confidence": "medium",
                }
            ]
        )
    )
    backend = SavePredictionBackend.holdout_calibrated(residual_store=store)
    assert backend._corrections is None
    assert backend._residual_store is store


def test_run_holdout_validation_exports_files(
    holdout_train_db: Path,
    holdout_test_db: Path,
    tmp_path: Path,
):
    result = run_holdout_validation(
        [holdout_train_db],
        [holdout_test_db],
        min_count=1,
    )
    paths = export_holdout_validation(result, tmp_path / "validation")
    assert paths["validation_summary"].exists()
    assert paths["validation_metric_comparison"].exists()
    assert paths["validation_worst_regressions"].exists()
    assert paths["validation_best_improvements"].exists()
    assert paths["validation_group_comparison"].exists()

    summary = json.loads(paths["validation_summary"].read_text(encoding="utf-8"))
    assert summary["train_saves"] == ["train-save.db"]
    assert summary["test_saves"] == ["test-save.db"]


def test_validate_save_calibration_cli(
    holdout_train_db: Path,
    holdout_test_db: Path,
    tmp_path: Path,
    capsys,
):
    out_dir = tmp_path / "cli_validation"
    exit_code = main(
        [
            "validate-save-calibration",
            "--train-save",
            str(holdout_train_db),
            "--test-save",
            str(holdout_test_db),
            "--output",
            str(out_dir),
            "--min-count",
            "1",
        ]
    )
    assert exit_code == 0
    captured = capsys.readouterr().out
    assert "Holdout save calibration validation" in captured
    assert (out_dir / "validation_metric_comparison.csv").exists()


def test_build_train_correction_store_uses_formula_only(holdout_train_db: Path):
    store, engine_df, gearbox_df = build_train_correction_store(
        [holdout_train_db],
        min_count=1,
    )
    assert len(engine_df) >= 1
    assert isinstance(store, ResidualCorrectionStore)
