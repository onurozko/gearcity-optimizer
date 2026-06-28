"""Tests for validation-gated calibration policy."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from gearcity_optimizer.cli.main import main
from gearcity_optimizer.prediction.calibration_policy import (
    CalibrationPolicyMode,
    GatedPredictionService,
    build_calibration_policy,
    export_calibration_policy,
    load_calibration_policy,
    select_metric_prediction,
    summarize_calibration_policy,
)


def _write_metric_comparison(
    path: Path,
    rows: list[dict[str, object]],
) -> None:
    pd.DataFrame(rows).to_csv(path, index=False)


def _write_group_comparison(
    path: Path,
    rows: list[dict[str, object]],
) -> None:
    pd.DataFrame(rows).to_csv(path, index=False)


@pytest.fixture
def validation_dir(tmp_path: Path) -> Path:
    root = tmp_path / "validation"
    root.mkdir()
    _write_metric_comparison(
        root / "validation_metric_comparison.csv",
        [
            {
                "kind": "engine",
                "metric": "horsepower",
                "sample_count": 10,
                "formula_only_mae": 5.0,
                "save_calibrated_mae": 3.0,
                "absolute_improvement": 2.0,
                "improvement_pct": 40.0,
                "status": "improved",
            },
            {
                "kind": "engine",
                "metric": "torque",
                "sample_count": 8,
                "formula_only_mae": 4.0,
                "save_calibrated_mae": 5.0,
                "absolute_improvement": -1.0,
                "improvement_pct": -25.0,
                "status": "worse",
            },
            {
                "kind": "engine",
                "metric": "weight",
                "sample_count": 6,
                "formula_only_mae": 2.0,
                "save_calibrated_mae": 2.0,
                "absolute_improvement": 0.0,
                "improvement_pct": 0.0,
                "status": "unchanged",
            },
            {
                "kind": "gearbox",
                "metric": "max_torque",
                "sample_count": 2,
                "formula_only_mae": 1.0,
                "save_calibrated_mae": 0.8,
                "absolute_improvement": 0.2,
                "improvement_pct": 20.0,
                "status": "insufficient_data",
            },
        ],
    )
    return root


@pytest.fixture
def validation_dir_with_groups(validation_dir: Path) -> Path:
    _write_group_comparison(
        validation_dir / "validation_group_comparison.csv",
        [
            {
                "kind": "engine",
                "metric": "horsepower",
                "year_band": "1900-1909",
                "layout": "I4",
                "fuel_type": "Gasoline",
                "gearbox_type": "",
                "sample_count": 5,
                "formula_only_mae": 4.0,
                "save_calibrated_mae": 6.0,
                "absolute_improvement": -2.0,
                "status": "worse",
            },
            {
                "kind": "engine",
                "metric": "horsepower",
                "year_band": "1900-1909",
                "layout": "",
                "fuel_type": "",
                "gearbox_type": "",
                "sample_count": 10,
                "formula_only_mae": 5.0,
                "save_calibrated_mae": 3.0,
                "absolute_improvement": 2.0,
                "status": "improved",
            },
        ],
    )
    return validation_dir


def test_improved_metric_selects_save_calibrated(validation_dir: Path):
    policy = build_calibration_policy(validation_dir)
    decision = select_metric_prediction(
        policy,
        kind="engine",
        metric="horsepower",
        formula_only_value=100.0,
        save_calibrated_value=110.0,
    )
    assert decision.selected_mode == "save_calibrated"
    assert decision.final_prediction == 110.0
    assert decision.validation_status == "improved"
    assert "improved" in decision.reason.lower()


@pytest.mark.parametrize(
    ("metric", "status"),
    [
        ("torque", "worse"),
        ("weight", "unchanged"),
        ("max_torque", "insufficient_data"),
    ],
)
def test_non_improved_metrics_select_formula_only(
    validation_dir: Path,
    metric: str,
    status: str,
):
    policy = build_calibration_policy(validation_dir)
    kind = "gearbox" if metric == "max_torque" else "engine"
    decision = select_metric_prediction(
        policy,
        kind=kind,
        metric=metric,
        formula_only_value=50.0,
        save_calibrated_value=60.0,
    )
    assert decision.selected_mode == "formula_only"
    assert decision.final_prediction == 50.0
    assert decision.validation_status == status


def test_missing_validation_files_default_to_formula_only(tmp_path: Path):
    policy = build_calibration_policy(tmp_path / "missing")
    decision = select_metric_prediction(
        policy,
        kind="engine",
        metric="horsepower",
        formula_only_value=80.0,
        save_calibrated_value=90.0,
    )
    assert decision.selected_mode == "formula_only"
    assert decision.final_prediction == 80.0
    assert decision.validation_status == "insufficient_data"
    assert "missing validation" in decision.reason.lower()


def test_prediction_metadata_explains_decision(validation_dir: Path):
    policy = build_calibration_policy(validation_dir)
    decision = select_metric_prediction(
        policy,
        kind="engine",
        metric="torque",
        formula_only_value=10.0,
        save_calibrated_value=12.0,
        year=1905,
        layout="I4",
        fuel_type="Gasoline",
    )
    assert decision.formula_only_prediction == 10.0
    assert decision.save_calibrated_prediction == 12.0
    assert decision.sample_count == 8
    assert decision.improvement_pct == pytest.approx(-25.0)
    assert decision.validation_level == "metric"


def test_group_level_gating_prefers_group_status(validation_dir_with_groups: Path):
    policy = build_calibration_policy(validation_dir_with_groups)
    group_worse = select_metric_prediction(
        policy,
        kind="engine",
        metric="horsepower",
        formula_only_value=100.0,
        save_calibrated_value=120.0,
        year=1905,
        layout="I4",
        fuel_type="Gasoline",
    )
    assert group_worse.validation_level == "group"
    assert group_worse.selected_mode == "formula_only"
    assert group_worse.validation_status == "worse"

    metric_fallback = select_metric_prediction(
        policy,
        kind="engine",
        metric="horsepower",
        formula_only_value=100.0,
        save_calibrated_value=120.0,
        year=1905,
        layout="V8",
        fuel_type="Gasoline",
    )
    assert metric_fallback.validation_level == "group"
    assert metric_fallback.validation_status == "improved"
    assert metric_fallback.selected_mode == "save_calibrated"


def test_group_gating_skips_low_sample_groups(validation_dir: Path):
    root = validation_dir
    _write_group_comparison(
        root / "validation_group_comparison.csv",
        [
            {
                "kind": "engine",
                "metric": "torque",
                "year_band": "1900-1909",
                "layout": "I4",
                "fuel_type": "",
                "gearbox_type": "",
                "sample_count": 2,
                "formula_only_mae": 1.0,
                "save_calibrated_mae": 0.5,
                "absolute_improvement": 0.5,
                "status": "improved",
            },
        ],
    )
    policy = build_calibration_policy(root, min_group_samples=3)
    decision = select_metric_prediction(
        policy,
        kind="engine",
        metric="torque",
        formula_only_value=40.0,
        save_calibrated_value=45.0,
        year=1905,
        layout="I4",
    )
    assert decision.validation_level == "metric"
    assert decision.selected_mode == "formula_only"
    assert decision.validation_status == "worse"


def test_export_and_load_calibration_policy(validation_dir_with_groups: Path, tmp_path: Path):
    policy = build_calibration_policy(validation_dir_with_groups)
    out = tmp_path / "policy"
    paths = export_calibration_policy(policy, out)
    assert paths["calibration_policy"].is_file()
    assert paths["calibration_policy_metrics"].is_file()
    assert paths["calibration_policy_groups"].is_file()

    loaded = load_calibration_policy(paths["calibration_policy"])
    assert loaded.mode == CalibrationPolicyMode.VALIDATION_GATED
    assert len(loaded.metric_rows) == len(policy.metric_rows)
    decision = select_metric_prediction(
        loaded,
        kind="engine",
        metric="horsepower",
        formula_only_value=1.0,
        save_calibrated_value=2.0,
        year=1905,
        layout="I4",
        fuel_type="Gasoline",
    )
    assert decision.validation_level == "group"
    assert decision.selected_mode == "formula_only"


def test_always_formula_only_policy_mode():
    policy = build_calibration_policy(None, mode=CalibrationPolicyMode.ALWAYS_FORMULA_ONLY)
    decision = select_metric_prediction(
        policy,
        kind="engine",
        metric="horsepower",
        formula_only_value=1.0,
        save_calibrated_value=99.0,
    )
    assert decision.selected_mode == "formula_only"
    assert decision.final_prediction == 1.0
    assert decision.validation_level == "policy"


def test_always_save_calibrated_policy_mode():
    policy = build_calibration_policy(None, mode=CalibrationPolicyMode.ALWAYS_SAVE_CALIBRATED)
    decision = select_metric_prediction(
        policy,
        kind="engine",
        metric="horsepower",
        formula_only_value=1.0,
        save_calibrated_value=99.0,
    )
    assert decision.selected_mode == "save_calibrated"
    assert decision.final_prediction == 99.0


def test_build_calibration_policy_cli(validation_dir: Path, tmp_path: Path, capsys):
    out = tmp_path / "calibration_policy"
    exit_code = main(
        [
            "build-calibration-policy",
            "--validation",
            str(validation_dir),
            "--output",
            str(out),
        ]
    )
    assert exit_code == 0
    assert (out / "calibration_policy.json").is_file()
    assert (out / "calibration_policy_metrics.csv").is_file()
    payload = json.loads((out / "calibration_policy.json").read_text(encoding="utf-8"))
    assert payload["policy_mode"] == "validation_gated"
    assert payload["metrics_enabled"] >= 1
    captured = capsys.readouterr().out
    assert "Calibration policy" in captured


def test_gated_prediction_service_uses_policy_per_metric(validation_dir: Path, sample_save_db: Path):
    policy = build_calibration_policy(validation_dir)
    service = GatedPredictionService.from_policy(policy)
    from gearcity_optimizer.importers.save_db import load_save_game

    snapshot = load_save_game(sample_save_db, company_id=0)
    if not snapshot.engines:
        pytest.skip("No engines in sample save")
    result = service.predict_engine(snapshot.engines[0], None)
    assert result.policy_mode == "validation_gated"
    assert result.metric_decisions
    for decision in result.metric_decisions:
        assert decision.reason
        assert decision.formula_only_prediction is not None
        assert decision.save_calibrated_prediction is not None
        if decision.validation_status == "improved":
            assert decision.selected_mode == "save_calibrated"
        elif decision.validation_status in {"worse", "unchanged", "insufficient_data"}:
            assert decision.selected_mode == "formula_only"


def test_group_policy_label_and_min_count_enforcement(validation_dir: Path, tmp_path: Path):
    _write_group_comparison(
        validation_dir / "validation_group_comparison.csv",
        [
            {
                "kind": "engine",
                "metric": "horsepower",
                "year_band": "1900-1909",
                "layout": "V8",
                "fuel_type": "Gasoline",
                "gearbox_type": "",
                "sample_count": 1,
                "formula_only_mae": 1.0,
                "save_calibrated_mae": 0.5,
                "absolute_improvement": 0.5,
                "status": "improved",
            },
            {
                "kind": "engine",
                "metric": "torque",
                "year_band": "1900-1909",
                "layout": "I4",
                "fuel_type": "",
                "gearbox_type": "",
                "sample_count": 1,
                "formula_only_mae": 1.0,
                "save_calibrated_mae": 0.5,
                "absolute_improvement": 0.5,
                "status": "improved",
            },
            {
                "kind": "engine",
                "metric": "horsepower",
                "year_band": "1900-1909",
                "layout": "",
                "fuel_type": "",
                "gearbox_type": "",
                "sample_count": 10,
                "formula_only_mae": 5.0,
                "save_calibrated_mae": 3.0,
                "absolute_improvement": 2.0,
                "status": "improved",
            },
        ],
    )
    policy = build_calibration_policy(validation_dir, min_group_samples=3)
    counts = summarize_calibration_policy(policy)

    assert counts.enabled_group_rules_below_min_count == 0
    assert counts.group_rules_below_min_count == 2

    low_hp = next(
        row for row in policy.group_rows if row.sample_count == 1 and row.metric == "horsepower"
    )
    assert low_hp.selected_mode == "metric_fallback"
    assert low_hp.reason == "Group sample_count below min_count; using metric-level fallback"
    assert (
        low_hp.group_label
        == "component=engine | metric=horsepower | year_band=1900-1909 | layout=V8 | fuel_type=Gasoline"
    )

    low_torque = next(
        row for row in policy.group_rows if row.sample_count == 1 and row.metric == "torque"
    )
    assert low_torque.selected_mode == "formula_only"
    assert low_torque.reason == "Group sample_count below min_count; using formula-only"

    high_hp = next(row for row in policy.group_rows if row.sample_count == 10)
    assert high_hp.selected_mode == "save_calibrated"

    for row in policy.group_rows:
        assert row.group_label.strip() != ""

    out = tmp_path / "policy"
    paths = export_calibration_policy(policy, out)
    groups_csv = pd.read_csv(paths["calibration_policy_groups"])
    for column in (
        "group_label",
        "year_band",
        "layout",
        "fuel_type",
        "gearbox_type",
    ):
        assert column in groups_csv.columns
    assert (groups_csv["group_label"].astype(str).str.strip() != "").all()
    below_min_enabled = groups_csv[
        (groups_csv["sample_count"] < 3) & (groups_csv["selected_mode"] == "save_calibrated")
    ]
    assert below_min_enabled.empty
