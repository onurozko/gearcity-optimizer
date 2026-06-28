"""Tests for real-save smoke test CLI and workflow."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pandas as pd
import pytest

from gearcity_optimizer.cli.main import main
from gearcity_optimizer.reports.real_save_smoke_test import (
    RealSaveSmokeTestError,
    collect_smoke_test_save_paths,
    run_real_save_smoke_test,
)


@pytest.fixture
def smoke_train_dir(sample_save_db: Path, tmp_path: Path) -> Path:
    directory = tmp_path / "train"
    directory.mkdir()
    shutil.copy(sample_save_db, directory / "train-save.db")
    return directory


@pytest.fixture
def smoke_test_dir(sample_save_db: Path, tmp_path: Path) -> Path:
    directory = tmp_path / "test"
    directory.mkdir()
    path = directory / "test-save.db"
    shutil.copy(sample_save_db, path)
    return directory


def test_collect_smoke_test_save_paths_success(smoke_train_dir: Path, smoke_test_dir: Path):
    train_paths, test_paths = collect_smoke_test_save_paths(
        train_dir=smoke_train_dir,
        test_dir=smoke_test_dir,
    )
    assert len(train_paths) == 1
    assert len(test_paths) == 1


def test_collect_smoke_test_save_paths_empty_train(tmp_path: Path, smoke_test_dir: Path):
    empty = tmp_path / "empty_train"
    empty.mkdir()
    with pytest.raises(RealSaveSmokeTestError, match="No .db save files found in train"):
        collect_smoke_test_save_paths(train_dir=empty, test_dir=smoke_test_dir)


def test_collect_smoke_test_save_paths_empty_test(tmp_path: Path, smoke_train_dir: Path):
    empty = tmp_path / "empty_test"
    empty.mkdir()
    with pytest.raises(RealSaveSmokeTestError, match="No .db save files found in test"):
        collect_smoke_test_save_paths(train_dir=smoke_train_dir, test_dir=empty)


def test_collect_smoke_test_save_paths_overlap(sample_save_db: Path, tmp_path: Path):
    train_dir = tmp_path / "train"
    test_dir = tmp_path / "test"
    train_dir.mkdir()
    test_dir.mkdir()
    shared = train_dir / "shared.db"
    shutil.copy(sample_save_db, shared)
    os.link(shared, test_dir / "shared.db")
    with pytest.raises(RealSaveSmokeTestError, match="same save file appears in both"):
        collect_smoke_test_save_paths(train_dir=train_dir, test_dir=test_dir)


def test_run_real_save_smoke_test_success(
    smoke_train_dir: Path,
    smoke_test_dir: Path,
    tmp_path: Path,
):
    out = tmp_path / "real_save_test"
    result = run_real_save_smoke_test(
        train_dir=smoke_train_dir,
        test_dir=smoke_test_dir,
        output_dir=out,
        min_count=1,
        company_id=0,
    )
    assert result.split_mode == "explicit_train_test"
    assert result.train_save_count == 1
    assert result.test_save_count == 1
    assert result.engine_row_count >= 1
    assert result.gearbox_row_count >= 1
    assert (out / "smoke_test_summary.json").is_file()
    assert (out / "save_datasets" / "engines.csv").is_file()
    assert (out / "validation" / "validation_metric_comparison.csv").is_file()
    assert (out / "calibration_policy" / "calibration_policy.json").is_file()
    assert (out / "inspect" / "train-save.txt").is_file()
    assert (out / "inspect" / "test-save.txt").is_file()

    payload = json.loads((out / "smoke_test_summary.json").read_text(encoding="utf-8"))
    assert payload["train_save_count"] == 1
    assert payload["test_save_count"] == 1
    assert payload["engine_row_count"] == result.engine_row_count
    assert payload["fallback_count"] == result.fallback_count


def test_run_real_save_smoke_test_empty_datasets(
    smoke_train_dir: Path,
    smoke_test_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    def empty_pipeline(*args, **kwargs):
        out = Path(kwargs["output_dir"])
        out.mkdir(parents=True, exist_ok=True)
        return {
            "engine_df": pd.DataFrame(),
            "gearbox_df": pd.DataFrame(),
            "paths": {},
        }

    monkeypatch.setattr(
        "gearcity_optimizer.reports.real_save_smoke_test.build_save_dataset_pipeline",
        empty_pipeline,
    )
    with pytest.raises(RealSaveSmokeTestError, match="Extracted datasets are empty"):
        run_real_save_smoke_test(
            train_dir=smoke_train_dir,
            test_dir=smoke_test_dir,
            output_dir=tmp_path / "out",
            min_count=1,
            company_id=0,
        )


def test_smoke_test_saves_cli(
    smoke_train_dir: Path,
    smoke_test_dir: Path,
    tmp_path: Path,
    capsys,
):
    out = tmp_path / "cli_smoke"
    exit_code = main(
        [
            "smoke-test-saves",
            "--train-dir",
            str(smoke_train_dir),
            "--test-dir",
            str(smoke_test_dir),
            "--output",
            str(out),
            "--min-count",
            "1",
            "--company-id",
            "0",
        ]
    )
    assert exit_code == 0
    captured = capsys.readouterr().out
    assert "Real save smoke test" in captured
    assert "Train saves: 1" in captured
    assert "Test saves: 1" in captured
    assert "Output folder:" in captured
    assert (out / "smoke_test_summary.json").is_file()


def test_smoke_test_saves_cli_empty_train(tmp_path: Path, smoke_test_dir: Path):
    empty = tmp_path / "empty_train"
    empty.mkdir()
    with pytest.raises(SystemExit) as exc:
        main(
            [
                "smoke-test-saves",
                "--train-dir",
                str(empty),
                "--test-dir",
                str(smoke_test_dir),
                "--output",
                str(tmp_path / "out"),
            ]
        )
    assert "No .db save files found in train" in str(exc.value)
