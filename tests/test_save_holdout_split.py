"""Tests for save holdout splitting and row-level validation."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

from gearcity_optimizer.cli.main import main
from gearcity_optimizer.reports.real_save_smoke_test import run_real_save_smoke_test
from gearcity_optimizer.reports.save_calibration_validation import run_row_level_holdout_validation
from gearcity_optimizer.reports.save_holdout_split import (
    SPLIT_MODE_SINGLE_SAVE,
    dedupe_design_frames,
    split_dedup_keys,
    split_design_frames,
    train_test_overlap,
)
from gearcity_optimizer.reports.save_calibration_dataset import build_save_dataset_pipeline


@pytest.fixture
def mixed_save_db(sample_save_db: Path, tmp_path: Path) -> Path:
    path = tmp_path / "mixed.db"
    shutil.copy(sample_save_db, path)
    return path


def _frames_from_save(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    result = build_save_dataset_pipeline([path], apply_corrections=False)
    return result["engine_df"], result["gearbox_df"]


def test_split_dedup_keys_same_seed_is_stable():
    keys = [f"key-{index}" for index in range(20)]
    train_a, test_a = split_dedup_keys(keys, split_ratio=0.8, seed=42)
    train_b, test_b = split_dedup_keys(keys, split_ratio=0.8, seed=42)
    assert train_a == train_b
    assert test_a == test_b


def test_split_dedup_keys_different_seed_can_differ():
    keys = [f"key-{index}" for index in range(30)]
    train_a, _ = split_dedup_keys(keys, split_ratio=0.8, seed=42)
    train_b, _ = split_dedup_keys(keys, split_ratio=0.8, seed=99)
    assert train_a != train_b or len(keys) < 2


def test_split_design_frames_no_train_test_overlap(mixed_save_db: Path):
    engine_df, gearbox_df = _frames_from_save(mixed_save_db)
    (
        train_engine,
        test_engine,
        train_gearbox,
        test_gearbox,
        _duplicates,
        train_keys,
        test_keys,
    ) = split_design_frames(engine_df, gearbox_df, split_ratio=0.8, seed=42)

    assert train_test_overlap(train_keys, test_keys) == set()
    if not train_engine.empty:
        assert not set(train_engine["dedup_key"]).intersection(set(test_engine["dedup_key"]))
    if not train_gearbox.empty:
        assert not set(train_gearbox["dedup_key"]).intersection(set(test_gearbox["dedup_key"]))


def test_dedupe_design_frames_removes_duplicate_rows(sample_save_db: Path, tmp_path: Path):
    first = tmp_path / "a.db"
    second = tmp_path / "b.db"
    shutil.copy(sample_save_db, first)
    shutil.copy(sample_save_db, second)
    engine_parts: list[pd.DataFrame] = []
    gearbox_parts: list[pd.DataFrame] = []
    for path in (first, second):
        engine_df, gearbox_df = _frames_from_save(path)
        engine_parts.append(engine_df)
        gearbox_parts.append(gearbox_df)
    engine_df = pd.concat(engine_parts, ignore_index=True)
    gearbox_df = pd.concat(gearbox_parts, ignore_index=True)
    before = len(engine_df) + len(gearbox_df)
    deduped_engine, deduped_gearbox, removed = dedupe_design_frames(engine_df, gearbox_df)
    after = len(deduped_engine) + len(deduped_gearbox)
    assert removed == before - after
    assert removed > 0


def test_run_row_level_holdout_validation_single_save(mixed_save_db: Path):
    result = run_row_level_holdout_validation(
        [mixed_save_db],
        min_count=1,
        split_ratio=0.5,
        seed=42,
        split_mode=SPLIT_MODE_SINGLE_SAVE,
    )
    assert result.split_mode == SPLIT_MODE_SINGLE_SAVE
    assert result.train_engine_rows + result.train_gearbox_rows >= 1
    assert result.test_engine_rows + result.test_gearbox_rows >= 1
    assert not result.eval_rows.empty


def test_smoke_test_single_save_cli(mixed_save_db: Path, tmp_path: Path, capsys):
    out = tmp_path / "single_save_smoke"
    exit_code = main(
        [
            "smoke-test-saves",
            "--save",
            str(mixed_save_db),
            "--output",
            str(out),
            "--min-count",
            "1",
            "--split-ratio",
            "0.5",
            "--seed",
            "42",
            "--company-id",
            "0",
        ]
    )
    assert exit_code == 0
    captured = capsys.readouterr().out
    assert "single_save_row_split" in captured
    payload = json.loads((out / "smoke_test_summary.json").read_text(encoding="utf-8"))
    assert payload["split_mode"] == "single_save_row_split"
    assert payload["train_row_count"] >= 1
    assert payload["test_row_count"] >= 1
    assert payload["seed"] == 42
    assert payload["split_ratio"] == 0.5


def test_smoke_test_saves_dir_cli(sample_save_db: Path, tmp_path: Path):
    saves_dir = tmp_path / "saves"
    saves_dir.mkdir()
    shutil.copy(sample_save_db, saves_dir / "one.db")
    shutil.copy(sample_save_db, saves_dir / "two.db")
    out = tmp_path / "saves_dir_smoke"
    result = run_real_save_smoke_test(
        saves_dir=saves_dir,
        output_dir=out,
        min_count=1,
        split_ratio=0.5,
        seed=7,
        company_id=0,
    )
    assert result.split_mode == "saves_dir_row_split"
    assert result.duplicates_removed >= 1
    payload = json.loads((out / "smoke_test_summary.json").read_text(encoding="utf-8"))
    assert payload["split_mode"] == "saves_dir_row_split"


def test_smoke_test_explicit_train_test_still_works(
    sample_save_db: Path,
    tmp_path: Path,
):
    train_dir = tmp_path / "train"
    test_dir = tmp_path / "test"
    train_dir.mkdir()
    test_dir.mkdir()
    shutil.copy(sample_save_db, train_dir / "train.db")
    shutil.copy(sample_save_db, test_dir / "test.db")
    out = tmp_path / "explicit_smoke"
    result = run_real_save_smoke_test(
        train_dir=train_dir,
        test_dir=test_dir,
        output_dir=out,
        min_count=1,
        company_id=0,
    )
    assert result.split_mode == "explicit_train_test"
    payload = json.loads((out / "smoke_test_summary.json").read_text(encoding="utf-8"))
    assert payload["split_mode"] == "explicit_train_test"
    assert payload["split_ratio"] is None
