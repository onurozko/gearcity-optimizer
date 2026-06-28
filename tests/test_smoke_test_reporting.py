"""Tests for smoke test and calibration policy reporting consistency."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd

from gearcity_optimizer.prediction.calibration_policy import (
    build_calibration_policy,
    export_calibration_policy,
    summarize_calibration_policy,
)
from gearcity_optimizer.reports.real_save_smoke_test import run_real_save_smoke_test


def _write_validation_artifacts(
    validation_dir: Path,
    *,
    metric_rows: list[dict[str, object]],
    group_rows: list[dict[str, object]],
) -> None:
    validation_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(metric_rows).to_csv(
        validation_dir / "validation_metric_comparison.csv",
        index=False,
    )
    pd.DataFrame(group_rows).to_csv(
        validation_dir / "validation_group_comparison.csv",
        index=False,
    )


def test_smoke_summary_counts_match_policy_csvs(tmp_path: Path):
    validation_dir = tmp_path / "validation"
    _write_validation_artifacts(
        validation_dir,
        metric_rows=[
            {
                "component": "engine",
                "kind": "engine",
                "metric": "torque",
                "sample_count": 100,
                "test_design_count": 100,
                "validation_eval_row_count": 100,
                "formula_only_mae": 10.0,
                "save_calibrated_mae": 5.0,
                "formula_only_mape": 20.0,
                "save_calibrated_mape": 10.0,
                "absolute_improvement": 5.0,
                "improvement_pct": 50.0,
                "status": "improved",
            },
            {
                "component": "engine",
                "kind": "engine",
                "metric": "horsepower",
                "sample_count": 100,
                "test_design_count": 100,
                "validation_eval_row_count": 100,
                "formula_only_mae": 8.0,
                "save_calibrated_mae": 8.0,
                "formula_only_mape": 15.0,
                "save_calibrated_mape": 15.0,
                "absolute_improvement": 0.0,
                "improvement_pct": 0.0,
                "status": "unchanged",
            },
        ],
        group_rows=[
            {
                "component": "engine",
                "kind": "engine",
                "metric": "torque",
                "year_band": "1900-1909",
                "layout": "I",
                "fuel_type": "Gasoline",
                "gearbox_type": "",
                "sample_count": 50,
                "test_design_count": 50,
                "validation_eval_row_count": 50,
                "formula_only_mae": 9.0,
                "save_calibrated_mae": 4.0,
                "absolute_improvement": 5.0,
                "status": "improved",
            },
            {
                "component": "engine",
                "kind": "engine",
                "metric": "torque",
                "year_band": "1910-1919",
                "layout": "I",
                "fuel_type": "Gasoline",
                "gearbox_type": "",
                "sample_count": 50,
                "test_design_count": 50,
                "validation_eval_row_count": 50,
                "formula_only_mae": 11.0,
                "save_calibrated_mae": 15.0,
                "absolute_improvement": -4.0,
                "status": "worse",
            },
        ],
    )

    policy = build_calibration_policy(validation_dir)
    metric_df = pd.read_csv(validation_dir / "validation_metric_comparison.csv")
    group_df = pd.read_csv(validation_dir / "validation_group_comparison.csv")
    counts = summarize_calibration_policy(
        policy,
        metric_comparison=metric_df,
        group_comparison=group_df,
    )
    policy_dir = tmp_path / "calibration_policy"
    export_calibration_policy(
        policy,
        policy_dir,
        metric_comparison=metric_df,
        group_comparison=group_df,
    )

    metrics_csv = pd.read_csv(policy_dir / "calibration_policy_metrics.csv")
    groups_csv = pd.read_csv(policy_dir / "calibration_policy_groups.csv")

    assert counts.validation_improved_metric_count == 1
    assert counts.validation_improved_group_count == 1
    assert counts.metric_level_enabled_count == 1
    assert counts.group_level_enabled_count == 1
    assert counts.total_enabled_rule_count == 2
    assert counts.total_enabled_rule_count == counts.metric_level_enabled_count + counts.group_level_enabled_count
    assert counts.validation_improved_metric_count >= counts.metric_level_enabled_count
    assert counts.validation_improved_group_count >= counts.group_level_enabled_count

    assert (metrics_csv["component"] != "").all()
    assert set(metrics_csv["component"]) <= {"engine", "gearbox"}
    assert int((metrics_csv["selected_mode"] == "save_calibrated").sum()) == counts.metric_level_enabled_count
    assert int((groups_csv["selected_mode"] == "save_calibrated").sum()) == counts.group_level_enabled_count
    assert int(metrics_csv.loc[metrics_csv["metric"] == "torque", "sample_count"].iloc[0]) == 100
    assert counts.enabled_group_rules_below_min_count == 0
    assert (groups_csv["group_label"].astype(str).str.strip() != "").all()
    for column in ("year_band", "layout", "fuel_type", "gearbox_type"):
        assert column in groups_csv.columns


def test_compute_metric_comparison_sample_count_uses_eval_rows(sample_save_db: Path, tmp_path: Path):
    train_dir = tmp_path / "train"
    test_dir = tmp_path / "test"
    train_dir.mkdir()
    test_dir.mkdir()
    shutil.copy(sample_save_db, train_dir / "train.db")
    shutil.copy(sample_save_db, test_dir / "test.db")

    from gearcity_optimizer.reports.save_calibration_validation import run_holdout_validation

    result = run_holdout_validation([train_dir / "train.db"], [test_dir / "test.db"], min_count=1, company_id=0)
    comparison = result.metric_comparison
    assert not comparison.empty
    assert (comparison["component"] != "").all()
    assert (comparison["sample_count"] == comparison["test_design_count"]).all()
    assert int(comparison.loc[comparison["kind"] == "engine", "sample_count"].iloc[0]) >= 1


def test_smoke_test_end_to_end_reporting(sample_save_db: Path, tmp_path: Path):
    train_dir = tmp_path / "train"
    test_dir = tmp_path / "test"
    train_dir.mkdir()
    test_dir.mkdir()
    shutil.copy(sample_save_db, train_dir / "train.db")
    shutil.copy(sample_save_db, test_dir / "test.db")
    out = tmp_path / "smoke"

    result = run_real_save_smoke_test(
        train_dir=train_dir,
        test_dir=test_dir,
        output_dir=out,
        min_count=1,
        company_id=0,
    )

    summary = json.loads((out / "smoke_test_summary.json").read_text(encoding="utf-8"))
    metrics_csv = pd.read_csv(out / "calibration_policy" / "calibration_policy_metrics.csv")

    assert summary["validation_improved_metric_count"] == result.validation_improved_metric_count
    assert summary["metric_level_enabled_count"] == result.metric_level_enabled_count
    assert summary["metric_level_enabled_count"] == int(
        (metrics_csv["selected_mode"] == "save_calibrated").sum()
    )
    assert (metrics_csv["component"] != "").all()
    assert summary["validation_improved_metric_count"] >= summary["metric_level_enabled_count"]
