"""End-to-end smoke test workflow for real GearCity save files."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from gearcity_optimizer.importers.save_schema import format_save_schema_report, inspect_save_schema
from gearcity_optimizer.importers.wiki_downloader import project_root_from_module
from gearcity_optimizer.prediction.calibration_policy import (
    build_calibration_policy,
    export_calibration_policy,
    summarize_calibration_policy,
)
from gearcity_optimizer.reports.save_calibration_dataset import build_save_dataset_pipeline
from gearcity_optimizer.reports.save_calibration_validation import (
    collect_save_paths,
    export_holdout_validation,
    run_holdout_validation,
    run_row_level_holdout_validation,
)
from gearcity_optimizer.reports.save_dataset_quality import (
    build_dataset_quality_report,
    export_dataset_quality_report,
)
from gearcity_optimizer.reports.save_holdout_split import (
    SPLIT_MODE_EXPLICIT,
    SPLIT_MODE_SAVES_DIR,
    SPLIT_MODE_SINGLE_SAVE,
    collect_save_paths_recursive,
)


class RealSaveSmokeTestError(ValueError):
    """Raised when smoke test inputs or outputs are invalid."""


@dataclass(frozen=True)
class RealSaveSmokeTestResult:
    """Summary of a completed real-save smoke test run."""

    output_dir: Path
    split_mode: str
    train_saves: tuple[str, ...]
    test_saves: tuple[str, ...]
    engine_row_count: int
    gearbox_row_count: int
    train_row_count: int
    test_row_count: int
    improved_count: int
    worse_count: int
    unchanged_count: int
    insufficient_data_count: int
    fallback_count: int
    skipped_design_count: int
    duplicates_removed: int
    split_ratio: float | None
    seed: int | None
    validation_improved_metric_count: int
    validation_improved_group_count: int
    metric_level_enabled_count: int
    group_level_enabled_count: int
    total_enabled_rule_count: int
    group_rules_below_min_count: int
    enabled_group_rules_below_min_count: int
    artifact_paths: dict[str, Path]

    @property
    def train_save_count(self) -> int:
        return len(self.train_saves)

    @property
    def test_save_count(self) -> int:
        return len(self.test_saves)


def default_real_save_test_dir() -> Path:
    return project_root_from_module() / "generated" / "real_save_test"


def collect_smoke_test_save_paths(
    *,
    train_dir: str | Path,
    test_dir: str | Path,
) -> tuple[list[Path], list[Path]]:
    """Collect train/test saves and validate smoke test inputs."""
    train_root = Path(train_dir)
    test_root = Path(test_dir)
    if not train_root.is_dir():
        raise RealSaveSmokeTestError(f"Train directory not found: {train_root}")
    if not test_root.is_dir():
        raise RealSaveSmokeTestError(f"Test directory not found: {test_root}")

    train_paths = collect_save_paths(save_dir=train_root)
    test_paths = collect_save_paths(save_dir=test_root)
    if not train_paths:
        raise RealSaveSmokeTestError(
            f"No .db save files found in train directory: {train_root}"
        )
    if not test_paths:
        raise RealSaveSmokeTestError(
            f"No .db save files found in test directory: {test_root}"
        )

    train_set = {path.resolve() for path in train_paths}
    test_set = {path.resolve() for path in test_paths}
    overlap = train_set & test_set
    if overlap:
        names = ", ".join(sorted(path.name for path in overlap))
        raise RealSaveSmokeTestError(
            f"The same save file appears in both train and test directories: {names}"
        )

    for train_path in train_paths:
        for test_path in test_paths:
            if os.path.samefile(train_path, test_path):
                raise RealSaveSmokeTestError(
                    "The same save file appears in both train and test directories: "
                    f"{train_path.name} and {test_path.name}"
                )

    return train_paths, test_paths


def _count_metric_statuses(metric_comparison: pd.DataFrame) -> dict[str, int]:
    if metric_comparison.empty or "status" not in metric_comparison.columns:
        return {
            "improved": 0,
            "worse": 0,
            "unchanged": 0,
            "insufficient_data": 0,
        }
    status = metric_comparison["status"].astype(str)
    return {
        "improved": int((status == "improved").sum()),
        "worse": int((status == "worse").sum()),
        "unchanged": int((status == "unchanged").sum()),
        "insufficient_data": int((status == "insufficient_data").sum()),
    }


def _inspect_saves(
    save_paths: list[Path],
    output_dir: Path,
) -> dict[str, Path]:
    inspect_dir = output_dir / "inspect"
    inspect_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for save_path in save_paths:
        report = inspect_save_schema(save_path)
        text_path = inspect_dir / f"{save_path.stem}.txt"
        text_path.write_text(format_save_schema_report(report), encoding="utf-8")
        paths[f"inspect_{save_path.name}"] = text_path
    return paths


def _resolve_smoke_test_inputs(
    *,
    train_dir: str | Path | None,
    test_dir: str | Path | None,
    save: str | Path | None,
    saves_dir: str | Path | None,
) -> tuple[str, list[Path], list[Path]]:
    has_explicit = train_dir is not None or test_dir is not None
    if has_explicit and (train_dir is None or test_dir is None):
        raise RealSaveSmokeTestError(
            "Both --train-dir and --test-dir are required for explicit holdout mode."
        )

    modes = [bool(has_explicit), save is not None, saves_dir is not None]
    if sum(modes) == 0:
        raise RealSaveSmokeTestError(
            "Provide --save, --saves-dir, or both --train-dir and --test-dir."
        )
    if sum(modes) > 1:
        raise RealSaveSmokeTestError(
            "Use only one input mode: --save, --saves-dir, or --train-dir/--test-dir."
        )

    if has_explicit:
        train_paths, test_paths = collect_smoke_test_save_paths(
            train_dir=train_dir,
            test_dir=test_dir,
        )
        return SPLIT_MODE_EXPLICIT, train_paths, test_paths

    if save is not None:
        save_path = Path(save)
        if not save_path.is_file():
            raise RealSaveSmokeTestError(f"Save file not found: {save_path}")
        return SPLIT_MODE_SINGLE_SAVE, [save_path], [save_path]

    assert saves_dir is not None
    save_paths = collect_save_paths_recursive(saves_dir)
    if not save_paths:
        raise RealSaveSmokeTestError(
            f"No .db save files found in saves directory: {saves_dir}"
        )
    return SPLIT_MODE_SAVES_DIR, save_paths, save_paths


def run_real_save_smoke_test(
    *,
    train_dir: str | Path | None = None,
    test_dir: str | Path | None = None,
    save: str | Path | None = None,
    saves_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
    company_id: int | None = None,
    min_count: int = 3,
    split_ratio: float = 0.8,
    seed: int = 42,
) -> RealSaveSmokeTestResult:
    """Run inspect, datasets, quality, holdout validation, and policy build."""
    split_mode, source_paths, holdout_test_paths = _resolve_smoke_test_inputs(
        train_dir=train_dir,
        test_dir=test_dir,
        save=save,
        saves_dir=saves_dir,
    )
    out = Path(output_dir) if output_dir is not None else default_real_save_test_dir()
    out.mkdir(parents=True, exist_ok=True)

    artifact_paths: dict[str, Path] = {}
    all_inspect_paths = list(
        {path.resolve(): path for path in (*source_paths, *holdout_test_paths)}.values()
    )
    artifact_paths.update(_inspect_saves(all_inspect_paths, out))

    dataset_paths = list(
        {path.resolve(): path for path in (*source_paths, *holdout_test_paths)}.values()
    )
    if split_mode == SPLIT_MODE_EXPLICIT:
        dataset_source_paths = source_paths
    else:
        dataset_source_paths = dataset_paths

    datasets_dir = out / "save_datasets"
    dataset_result = build_save_dataset_pipeline(
        dataset_source_paths,
        company_id=company_id,
        output_dir=datasets_dir,
    )
    engine_df: pd.DataFrame = dataset_result["engine_df"]
    gearbox_df: pd.DataFrame = dataset_result["gearbox_df"]
    if engine_df.empty and gearbox_df.empty:
        raise RealSaveSmokeTestError(
            "Extracted datasets are empty: no engine or gearbox rows from saves."
        )
    artifact_paths.update(dataset_result["paths"])

    quality_report = build_dataset_quality_report(datasets_dir)
    artifact_paths.update(export_dataset_quality_report(quality_report, datasets_dir))

    validation_dir = out / "validation"
    if split_mode == SPLIT_MODE_EXPLICIT:
        validation_result = run_holdout_validation(
            source_paths,
            holdout_test_paths,
            company_id=company_id,
            min_count=min_count,
        )
        train_row_count = validation_result.train_engine_rows + validation_result.train_gearbox_rows
        test_row_count = validation_result.test_engine_rows + validation_result.test_gearbox_rows
        split_ratio_value: float | None = None
        seed_value: int | None = None
        duplicates_removed = 0
        train_save_names = validation_result.train_saves
        test_save_names = validation_result.test_saves
    else:
        validation_result = run_row_level_holdout_validation(
            source_paths,
            company_id=company_id,
            min_count=min_count,
            split_ratio=split_ratio,
            seed=seed,
            split_mode=split_mode,
        )
        train_row_count = validation_result.train_engine_rows + validation_result.train_gearbox_rows
        test_row_count = validation_result.test_engine_rows + validation_result.test_gearbox_rows
        split_ratio_value = split_ratio
        seed_value = seed
        duplicates_removed = validation_result.duplicates_removed
        train_save_names = validation_result.train_saves
        test_save_names = validation_result.test_saves

    artifact_paths.update(export_holdout_validation(validation_result, validation_dir))

    policy_dir = out / "calibration_policy"
    policy = build_calibration_policy(validation_dir)
    policy_counts = summarize_calibration_policy(
        policy,
        metric_comparison=validation_result.metric_comparison,
        group_comparison=validation_result.group_comparison,
    )
    artifact_paths.update(
        export_calibration_policy(
            policy,
            policy_dir,
            metric_comparison=validation_result.metric_comparison,
            group_comparison=validation_result.group_comparison,
        )
    )

    status_counts = _count_metric_statuses(validation_result.metric_comparison)
    skipped_design_count = int(
        dataset_result.get("skipped_design_count", 0)
        or validation_result.skipped_design_count
    )

    summary_path = out / "smoke_test_summary.json"
    summary_payload = {
        "split_mode": split_mode,
        "train_dir": str(Path(train_dir)) if train_dir is not None else None,
        "test_dir": str(Path(test_dir)) if test_dir is not None else None,
        "save": str(Path(save)) if save is not None else None,
        "saves_dir": str(Path(saves_dir)) if saves_dir is not None else None,
        "output_dir": str(out),
        "train_save_count": len(train_save_names),
        "test_save_count": len(test_save_names),
        "train_saves": list(train_save_names),
        "test_saves": list(test_save_names),
        "engine_row_count": len(engine_df),
        "gearbox_row_count": len(gearbox_df),
        "train_row_count": train_row_count,
        "test_row_count": test_row_count,
        "split_ratio": split_ratio_value,
        "seed": seed_value,
        "duplicates_removed": duplicates_removed,
        "skipped_design_count": skipped_design_count,
        "validation_improved_metric_count": policy_counts.validation_improved_metric_count,
        "validation_improved_group_count": policy_counts.validation_improved_group_count,
        "metric_level_enabled_count": policy_counts.metric_level_enabled_count,
        "group_level_enabled_count": policy_counts.group_level_enabled_count,
        "total_enabled_rule_count": policy_counts.total_enabled_rule_count,
        "group_rules_below_min_count": policy_counts.group_rules_below_min_count,
        "enabled_group_rules_below_min_count": policy_counts.enabled_group_rules_below_min_count,
        "improved_metric_count": status_counts["improved"],
        "worse_metric_count": status_counts["worse"],
        "unchanged_metric_count": status_counts["unchanged"],
        "insufficient_data_metric_count": status_counts["insufficient_data"],
        "fallback_count": validation_result.fallback_count,
        "artifacts": {key: str(path) for key, path in sorted(artifact_paths.items())},
    }
    summary_path.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")
    artifact_paths["smoke_test_summary"] = summary_path

    return RealSaveSmokeTestResult(
        output_dir=out,
        split_mode=split_mode,
        train_saves=train_save_names,
        test_saves=test_save_names,
        engine_row_count=len(engine_df),
        gearbox_row_count=len(gearbox_df),
        train_row_count=train_row_count,
        test_row_count=test_row_count,
        improved_count=status_counts["improved"],
        worse_count=status_counts["worse"],
        unchanged_count=status_counts["unchanged"],
        insufficient_data_count=status_counts["insufficient_data"],
        fallback_count=validation_result.fallback_count,
        skipped_design_count=skipped_design_count,
        duplicates_removed=duplicates_removed,
        split_ratio=split_ratio_value,
        seed=seed_value,
        validation_improved_metric_count=policy_counts.validation_improved_metric_count,
        validation_improved_group_count=policy_counts.validation_improved_group_count,
        metric_level_enabled_count=policy_counts.metric_level_enabled_count,
        group_level_enabled_count=policy_counts.group_level_enabled_count,
        total_enabled_rule_count=policy_counts.total_enabled_rule_count,
        group_rules_below_min_count=policy_counts.group_rules_below_min_count,
        enabled_group_rules_below_min_count=policy_counts.enabled_group_rules_below_min_count,
        artifact_paths=artifact_paths,
    )


def format_real_save_smoke_test_summary(result: RealSaveSmokeTestResult) -> list[str]:
    """Render a compact terminal summary for the smoke test."""
    lines = [
        "Real save smoke test",
        "=" * 72,
        f"Split mode: {result.split_mode}",
        f"Train saves: {result.train_save_count}",
        f"Test saves: {result.test_save_count}",
        f"Engine rows extracted: {result.engine_row_count}",
        f"Gearbox rows extracted: {result.gearbox_row_count}",
        f"Train rows (holdout): {result.train_row_count}",
        f"Test rows (holdout): {result.test_row_count}",
    ]
    if result.split_ratio is not None:
        lines.append(f"Split ratio: {result.split_ratio}")
    if result.seed is not None:
        lines.append(f"Seed: {result.seed}")
    lines.extend(
        [
            f"Duplicates removed: {result.duplicates_removed}",
            f"Validation improved metrics: {result.validation_improved_metric_count}",
            f"Validation improved groups: {result.validation_improved_group_count}",
            f"Enabled policy metrics: {result.metric_level_enabled_count}",
            f"Enabled policy groups: {result.group_level_enabled_count}",
            f"Total enabled calibration rules: {result.total_enabled_rule_count}",
            f"Group rules below min_count: {result.group_rules_below_min_count}",
            f"Enabled group rules below min_count: {result.enabled_group_rules_below_min_count}",
            f"Worse validation metrics: {result.worse_count}",
            f"Unchanged validation metrics: {result.unchanged_count}",
            f"Insufficient data validation metrics: {result.insufficient_data_count}",
            f"Formula fallback rows: {result.fallback_count}",
            f"Skipped designs: {result.skipped_design_count}",
            f"Output folder: {result.output_dir}",
        ]
    )
    return lines
