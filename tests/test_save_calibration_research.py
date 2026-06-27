"""Tests for save calibration research datasets and grouped analysis."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from gearcity_optimizer.reports.save_calibration import calibrate_save_game
from gearcity_optimizer.reports.save_calibration_dataset import (
    build_calibration_frames,
    export_calibration_dataset,
    metrics_long_frame,
)
from gearcity_optimizer.reports.save_calibration_features import (
    fuel_family,
    mod_bucket,
    valve_family,
)
from gearcity_optimizer.reports.save_calibration_research import (
    feature_correlations,
    format_research_report,
    recommend_fix_buckets,
    run_calibration_research,
)


def test_feature_helpers():
    assert fuel_family("Gasoline") == "gasoline"
    assert fuel_family("Electric Hybrid") == "electric/hybrid"
    assert valve_family("W/DOHC") == "DOHC"
    assert mod_bucket(0) == "mod=0"
    assert mod_bucket(2) == "mod=1-2"
    assert mod_bucket(3) == "mod=3+"


def test_build_calibration_frames(sample_save_db: Path):
    report = calibrate_save_game(str(sample_save_db), company_id=0)
    engine_df, gearbox_df = build_calibration_frames([report], save_labels=["sample.db"])

    assert len(engine_df) == 1
    assert len(gearbox_df) == 1
    assert engine_df.iloc[0]["save"] == "sample.db"
    assert engine_df.iloc[0]["kind"] == "engine"
    assert "err_torque_pct" in engine_df.columns
    assert "fit_max_pct" in engine_df.columns
    assert gearbox_df.iloc[0]["ratio_pattern"] in {"lo0_hi0", "hi_max", "lo1_hi1", "mid"}


def test_metrics_long_frame(sample_save_db: Path):
    report = calibrate_save_game(str(sample_save_db), company_id=0)
    engine_df, gearbox_df = build_calibration_frames([report])
    long_df = metrics_long_frame(engine_df, gearbox_df)

    assert not long_df.empty
    assert set(long_df.columns) >= {"save", "kind", "design_id", "metric", "pct_error"}
    assert long_df["kind"].isin(["engine", "gearbox"]).all()


def test_export_calibration_dataset(sample_save_db: Path, tmp_path: Path):
    report = calibrate_save_game(str(sample_save_db), company_id=0)
    paths = export_calibration_dataset([report], tmp_path / "out")

    assert paths["engines"].exists()
    assert paths["gearboxes"].exists()
    assert paths["metrics_long"].exists()
    engines = pd.read_csv(paths["engines"])
    assert len(engines) == 1


def test_run_calibration_research_writes_artifacts(sample_save_db: Path, tmp_path: Path):
    out_dir = tmp_path / "research"
    result = run_calibration_research(
        [str(sample_save_db)],
        company_id=0,
        output_dir=out_dir,
    )

    assert len(result["engine_df"]) == 1
    assert len(result["fix_buckets"]) >= 0
    paths = result["paths"]
    assert paths["engines"].exists()
    assert paths["report"].exists()
    assert paths["correlations"].exists()
    assert paths["fix_buckets"].exists()

    lines = format_research_report(
        result["reports"],
        result["engine_df"],
        result["gearbox_df"],
        result["fix_buckets"],
        result["correlations_df"],
    )
    text = "\n".join(lines)
    assert "Calibration research report" in text
    assert "Recommended fix buckets" in text


def test_feature_correlations_returns_sorted_rows():
    df = pd.DataFrame(
        {
            "mod_amount": [0, 1, 2, 3],
            "slider_torq": [0.1, 0.2, 0.3, 0.4],
            "fit_max_pct": [5.0, 10.0, 15.0, 20.0],
            "err_torque_pct": [4.0, 8.0, 12.0, 16.0],
        }
    )
    corr = feature_correlations(
        df,
        ("err_torque_pct",),
        ("mod_amount", "slider_torq"),
    )
    assert not corr.empty
    assert corr.iloc[0]["target"] == "err_torque_pct"
    assert corr.iloc[0]["abs_correlation"] >= corr.iloc[-1]["abs_correlation"]


def test_recommend_fix_buckets_empty_when_no_high_errors():
    engine_df = pd.DataFrame(
        {
            "fuel_family": ["gasoline"],
            "layout": ["W"],
            "valve_family": ["DOHC"],
            "mod_bucket": ["mod=1-2"],
            "err_torque_pct": [2.0],
            "signed_torque_pct": [1.0],
            "err_horsepower_pct": [2.0],
            "signed_horsepower_pct": [1.0],
            "fit_max_pct": [2.0],
        }
    )
    gearbox_df = pd.DataFrame(
        {
            "mod_bucket": ["mod=0"],
            "ratio_pattern": ["lo0_hi0"],
            "gears": [3],
            "err_max_torque_pct": [3.0],
            "signed_max_torque_pct": [1.0],
            "err_power_rating_pct": [50.0],
        }
    )
    buckets = recommend_fix_buckets(engine_df, gearbox_df)
    assert buckets == []
