"""Holdout validation for save-calibrated predictions against formula-only baseline."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from gearcity_optimizer.importers.save_db import SaveEngineRecord, SaveGearboxRecord
from gearcity_optimizer.prediction.backend import SaveEnginePrediction, SaveGearboxPrediction, SavePredictionBackend
from gearcity_optimizer.reports.save_calibration import calibrate_save_game
from gearcity_optimizer.reports.save_calibration_dataset import build_calibration_frames
from gearcity_optimizer.reports.save_dataset_residuals import (
    ResidualCorrectionStore,
    build_residual_correction_tables,
    engine_replay_metric_names,
    gearbox_replay_metric_names,
    year_band,
)

MIN_VALIDATION_SAMPLES = 1
STATUS_EPSILON = 1e-9


@dataclass(frozen=True)
class HoldoutValidationResult:
    """Full holdout validation output."""

    train_saves: tuple[str, ...]
    test_saves: tuple[str, ...]
    train_engine_rows: int
    train_gearbox_rows: int
    test_engine_rows: int
    test_gearbox_rows: int
    correction_segments: int
    eval_rows: pd.DataFrame
    metric_comparison: pd.DataFrame
    worst_regressions: pd.DataFrame
    best_improvements: pd.DataFrame
    group_comparison: pd.DataFrame
    fallback_count: int


def collect_save_paths(
    *,
    save_paths: list[str | Path] | None = None,
    save_dir: str | Path | None = None,
) -> list[Path]:
    """Collect GearCity .db paths from explicit files and/or a directory."""
    paths: list[Path] = []
    seen: set[Path] = set()

    for raw in save_paths or []:
        path = Path(raw)
        if not path.is_file():
            raise FileNotFoundError(f"Save game not found: {path}")
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            paths.append(path)

    if save_dir is not None:
        directory = Path(save_dir)
        if not directory.is_dir():
            raise FileNotFoundError(f"Save directory not found: {directory}")
        for path in sorted(directory.glob("*.db")):
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                paths.append(path)

    return paths


def engine_actual_value(record: SaveEngineRecord, metric: str) -> float:
    mapping = {
        "length": record.length_in,
        "width": record.width_in,
        "weight": record.weight_lb,
        "torque": record.torque_lbft,
        "horsepower": record.horsepower,
        "power_rating": record.engine_power_rating,
        "fuel_rating": record.engine_fuel_rating,
        "reliability_rating": record.engine_reliability_rating,
        "overall_rating": record.overall_rating,
    }
    return float(mapping[metric])


def engine_predicted_value(prediction: SaveEnginePrediction, metric: str) -> float:
    result = prediction.predicted
    mapping = {
        "length": result.length,
        "width": result.width,
        "weight": result.weight,
        "torque": result.torque,
        "horsepower": result.horsepower,
        "power_rating": result.performance_rating,
        "fuel_rating": result.fuel_economy,
        "reliability_rating": result.reliability_rating,
        "overall_rating": result.overall_rating,
    }
    return float(mapping[metric])


def gearbox_actual_value(record: SaveGearboxRecord, metric: str) -> float:
    mapping = {
        "max_torque": record.max_torque_input_lbft,
        "weight": record.weight_lb,
        "power_rating": record.power_rating,
        "fuel_rating": record.fuel_rating,
        "performance_rating": record.performance_rating,
        "reliability_rating": record.reliability_rating,
        "overall_rating": record.overall_rating,
    }
    return float(mapping[metric])


def gearbox_predicted_value(prediction: SaveGearboxPrediction, metric: str) -> float:
    result = prediction.predicted
    if metric == "max_torque":
        return float(prediction.max_torque_support)
    mapping = {
        "weight": result.weight,
        "power_rating": result.power_rating,
        "fuel_rating": result.fuel_economy_rating,
        "performance_rating": result.performance_rating,
        "reliability_rating": result.reliability_rating,
        "overall_rating": result.overall_rating,
    }
    return float(mapping[metric])


def build_train_correction_store(
    train_paths: list[str | Path],
    *,
    company_id: int | None = 0,
    min_count: int = 3,
) -> tuple[ResidualCorrectionStore, pd.DataFrame, pd.DataFrame]:
    """Build residual corrections from train saves only."""
    labels = [Path(path).name for path in train_paths]
    reports = [
        calibrate_save_game(
            str(path),
            company_id=company_id,
            engine_limit=None,
            gearbox_limit=None,
            apply_corrections=False,
        )
        for path in train_paths
    ]
    engine_df, gearbox_df = build_calibration_frames(
        reports,
        save_labels=labels,
        apply_corrections=False,
    )
    engine_corr, gearbox_corr = build_residual_correction_tables(
        engine_df,
        gearbox_df,
        min_count=min_count,
    )
    return ResidualCorrectionStore(engine_corr, gearbox_corr), engine_df, gearbox_df


def evaluate_holdout_predictions(
    test_paths: list[str | Path],
    *,
    residual_store: ResidualCorrectionStore,
    company_id: int | None = 0,
) -> tuple[pd.DataFrame, int]:
    """Run formula-only and train-calibrated predictions on held-out test saves."""
    formula_backend = SavePredictionBackend.formula_only()
    calibrated_backend = SavePredictionBackend.holdout_calibrated(
        residual_store=residual_store
    )

    rows: list[dict[str, object]] = []
    fallback_count = 0

    for path in test_paths:
        report = calibrate_save_game(
            str(path),
            company_id=company_id,
            engine_limit=None,
            gearbox_limit=None,
            apply_corrections=False,
        )
        save_label = Path(path).name

        for item in report.engines:
            record = item.record
            formula_pred = formula_backend.predict_engine(record, item.layout)
            calibrated_pred = calibrated_backend.predict_engine(record, item.layout)
            if not calibrated_pred.corrections_applied:
                fallback_count += 1

            for metric in engine_replay_metric_names():
                actual = engine_actual_value(record, metric)
                formula_value = engine_predicted_value(formula_pred, metric)
                calibrated_value = engine_predicted_value(calibrated_pred, metric)
                rows.append(
                    _eval_row(
                        save=save_label,
                        kind="engine",
                        design_id=record.engine_id,
                        name=record.name,
                        year=record.year_built,
                        layout=record.layout,
                        fuel_type=record.fuel_type,
                        gearbox_type="",
                        metric=metric,
                        actual=actual,
                        formula_only=formula_value,
                        save_calibrated=calibrated_value,
                        correction_applied=calibrated_pred.corrections_applied,
                        matched_segment=calibrated_pred.matched_segment,
                        confidence=calibrated_pred.confidence,
                    )
                )

        for item in report.gearboxes:
            record = item.record
            formula_pred = formula_backend.predict_gearbox(record)
            calibrated_pred = calibrated_backend.predict_gearbox(record)
            if not calibrated_pred.corrections_applied:
                fallback_count += 1

            for metric in gearbox_replay_metric_names():
                actual = gearbox_actual_value(record, metric)
                formula_value = gearbox_predicted_value(formula_pred, metric)
                calibrated_value = gearbox_predicted_value(calibrated_pred, metric)
                rows.append(
                    _eval_row(
                        save=save_label,
                        kind="gearbox",
                        design_id=record.gearbox_id,
                        name=record.name,
                        year=record.year_built,
                        layout="",
                        fuel_type="",
                        gearbox_type=record.gearbox_type,
                        metric=metric,
                        actual=actual,
                        formula_only=formula_value,
                        save_calibrated=calibrated_value,
                        correction_applied=calibrated_pred.corrections_applied,
                        matched_segment=calibrated_pred.matched_segment,
                        confidence=calibrated_pred.confidence,
                    )
                )

    if not rows:
        return _empty_eval_frame(), 0
    return pd.DataFrame(rows), fallback_count


def _eval_row(
    *,
    save: str,
    kind: str,
    design_id: int,
    name: str,
    year: int,
    layout: str,
    fuel_type: str,
    gearbox_type: str,
    metric: str,
    actual: float,
    formula_only: float,
    save_calibrated: float,
    correction_applied: bool,
    matched_segment: str | None,
    confidence: str | None,
) -> dict[str, object]:
    formula_abs = abs(formula_only - actual)
    calibrated_abs = abs(save_calibrated - actual)
    formula_pct = _pct_error(actual, formula_only)
    calibrated_pct = _pct_error(actual, save_calibrated)
    return {
        "save": save,
        "kind": kind,
        "design_id": design_id,
        "name": name,
        "year": year,
        "year_band": year_band(year),
        "layout": layout,
        "fuel_type": fuel_type,
        "gearbox_type": gearbox_type,
        "metric": metric,
        "actual": actual,
        "formula_only": formula_only,
        "save_calibrated": save_calibrated,
        "formula_only_abs_error": formula_abs,
        "save_calibrated_abs_error": calibrated_abs,
        "formula_only_pct_error": formula_pct,
        "save_calibrated_pct_error": calibrated_pct,
        "row_improvement": formula_abs - calibrated_abs,
        "correction_applied": correction_applied,
        "matched_segment": matched_segment,
        "confidence": confidence,
        "used_formula_fallback": not correction_applied,
    }


def _pct_error(actual: float, predicted: float) -> float | None:
    if abs(actual) <= 1e-6:
        return None
    return abs(predicted - actual) / abs(actual) * 100.0


def _empty_eval_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "save",
            "kind",
            "design_id",
            "name",
            "year",
            "year_band",
            "layout",
            "fuel_type",
            "gearbox_type",
            "metric",
            "actual",
            "formula_only",
            "save_calibrated",
            "formula_only_abs_error",
            "save_calibrated_abs_error",
            "formula_only_pct_error",
            "save_calibrated_pct_error",
            "row_improvement",
            "correction_applied",
            "matched_segment",
            "confidence",
            "used_formula_fallback",
        ]
    )


def classify_metric_status(
    *,
    sample_count: int,
    formula_only_mae: float,
    save_calibrated_mae: float,
) -> str:
    """Classify whether save calibration improved holdout error for one metric."""
    if sample_count < MIN_VALIDATION_SAMPLES:
        return "insufficient_data"
    delta = formula_only_mae - save_calibrated_mae
    if abs(delta) <= STATUS_EPSILON:
        return "unchanged"
    if delta > STATUS_EPSILON:
        return "improved"
    return "worse"


def compute_metric_comparison(eval_rows: pd.DataFrame) -> pd.DataFrame:
    """Aggregate holdout MAE/MAPE comparison by kind and metric."""
    if eval_rows.empty:
        return pd.DataFrame(
            columns=[
                "kind",
                "metric",
                "sample_count",
                "formula_only_mae",
                "save_calibrated_mae",
                "formula_only_mape",
                "save_calibrated_mape",
                "absolute_improvement",
                "improvement_pct",
                "status",
            ]
        )

    rows: list[dict[str, object]] = []
    for (kind, metric), frame in eval_rows.groupby(["kind", "metric"], dropna=False):
        sample_count = len(frame)
        formula_only_mae = float(frame["formula_only_abs_error"].mean())
        save_calibrated_mae = float(frame["save_calibrated_abs_error"].mean())
        formula_only_mape = _mean_pct(frame["formula_only_pct_error"])
        save_calibrated_mape = _mean_pct(frame["save_calibrated_pct_error"])
        absolute_improvement = formula_only_mae - save_calibrated_mae
        improvement_pct = (
            (absolute_improvement / formula_only_mae) * 100.0
            if formula_only_mae > STATUS_EPSILON
            else 0.0
        )
        rows.append(
            {
                "kind": kind,
                "metric": metric,
                "sample_count": sample_count,
                "formula_only_mae": formula_only_mae,
                "save_calibrated_mae": save_calibrated_mae,
                "formula_only_mape": formula_only_mape,
                "save_calibrated_mape": save_calibrated_mape,
                "absolute_improvement": absolute_improvement,
                "improvement_pct": improvement_pct,
                "status": classify_metric_status(
                    sample_count=sample_count,
                    formula_only_mae=formula_only_mae,
                    save_calibrated_mae=save_calibrated_mae,
                ),
            }
        )
    return pd.DataFrame(rows).sort_values(["kind", "metric"])


def _mean_pct(series: pd.Series) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return None
    return float(values.mean())


def worst_regressions(eval_rows: pd.DataFrame, *, top_n: int = 20) -> pd.DataFrame:
    """Rows where save calibration performed worse than formula-only."""
    if eval_rows.empty:
        return eval_rows.copy()
    worse = eval_rows[eval_rows["row_improvement"] < -STATUS_EPSILON].copy()
    return worse.sort_values("row_improvement").head(top_n)


def best_improvements(eval_rows: pd.DataFrame, *, top_n: int = 20) -> pd.DataFrame:
    """Rows where save calibration improved over formula-only."""
    if eval_rows.empty:
        return eval_rows.copy()
    improved = eval_rows[eval_rows["row_improvement"] > STATUS_EPSILON].copy()
    return improved.sort_values("row_improvement", ascending=False).head(top_n)


def compute_group_comparison(eval_rows: pd.DataFrame) -> pd.DataFrame:
    """Compare formula-only vs save-calibrated error by grouped segments."""
    if eval_rows.empty:
        return pd.DataFrame(
            columns=[
                "kind",
                "metric",
                "year_band",
                "layout",
                "fuel_type",
                "gearbox_type",
                "sample_count",
                "formula_only_mae",
                "save_calibrated_mae",
                "absolute_improvement",
                "status",
            ]
        )

    parts: list[pd.DataFrame] = []
    engine_groups = [
        ["year_band"],
        ["year_band", "layout"],
        ["year_band", "layout", "fuel_type"],
    ]
    for group_cols in engine_groups:
        subset = eval_rows[eval_rows["kind"] == "engine"]
        if subset.empty:
            continue
        parts.append(_group_metric_frame(subset, group_cols))

    for group_cols in (["year_band"], ["year_band", "gearbox_type"]):
        subset = eval_rows[eval_rows["kind"] == "gearbox"]
        if subset.empty:
            continue
        parts.append(_group_metric_frame(subset, group_cols))

    if not parts:
        return pd.DataFrame()
    merged = pd.concat(parts, ignore_index=True)
    return merged.sort_values("absolute_improvement")


def _group_metric_frame(frame: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    grouped = (
        frame.groupby(["metric", *group_cols], dropna=False)
        .agg(
            sample_count=("actual", "count"),
            formula_only_mae=("formula_only_abs_error", "mean"),
            save_calibrated_mae=("save_calibrated_abs_error", "mean"),
        )
        .reset_index()
    )
    grouped["absolute_improvement"] = (
        grouped["formula_only_mae"] - grouped["save_calibrated_mae"]
    )
    grouped["status"] = grouped.apply(
        lambda row: classify_metric_status(
            sample_count=int(row["sample_count"]),
            formula_only_mae=float(row["formula_only_mae"]),
            save_calibrated_mae=float(row["save_calibrated_mae"]),
        ),
        axis=1,
    )
    grouped["kind"] = frame["kind"].iloc[0]
    for col in ("layout", "fuel_type", "gearbox_type"):
        if col not in grouped.columns:
            grouped[col] = ""
    return grouped


def run_holdout_validation(
    train_paths: list[str | Path],
    test_paths: list[str | Path],
    *,
    company_id: int | None = 0,
    min_count: int = 3,
) -> HoldoutValidationResult:
    """Run the full train/test holdout validation workflow."""
    if not train_paths:
        raise ValueError("At least one train save is required.")
    if not test_paths:
        raise ValueError("At least one test save is required.")

    train_set = {Path(path).resolve() for path in train_paths}
    test_set = {Path(path).resolve() for path in test_paths}
    overlap = train_set & test_set
    if overlap:
        names = ", ".join(sorted(path.name for path in overlap))
        raise ValueError(f"Train and test saves must not overlap: {names}")

    residual_store, train_engine_df, train_gearbox_df = build_train_correction_store(
        train_paths,
        company_id=company_id,
        min_count=min_count,
    )
    eval_rows, fallback_count = evaluate_holdout_predictions(
        test_paths,
        residual_store=residual_store,
        company_id=company_id,
    )
    metric_comparison = compute_metric_comparison(eval_rows)

    def _design_count(kind: str) -> int:
        if eval_rows.empty:
            return 0
        subset = eval_rows[eval_rows["kind"] == kind]
        return len(subset[["save", "design_id"]].drop_duplicates())

    return HoldoutValidationResult(
        train_saves=tuple(Path(path).name for path in train_paths),
        test_saves=tuple(Path(path).name for path in test_paths),
        train_engine_rows=len(train_engine_df),
        train_gearbox_rows=len(train_gearbox_df),
        test_engine_rows=_design_count("engine"),
        test_gearbox_rows=_design_count("gearbox"),
        correction_segments=len(residual_store.engine_corrections)
        + len(residual_store.gearbox_corrections),
        eval_rows=eval_rows,
        metric_comparison=metric_comparison,
        worst_regressions=worst_regressions(eval_rows),
        best_improvements=best_improvements(eval_rows),
        group_comparison=compute_group_comparison(eval_rows),
        fallback_count=fallback_count,
    )


def export_holdout_validation(
    result: HoldoutValidationResult,
    output_dir: str | Path,
) -> dict[str, Path]:
    """Write holdout validation artifacts to disk."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    summary = {
        "train_saves": list(result.train_saves),
        "test_saves": list(result.test_saves),
        "train_engine_rows": result.train_engine_rows,
        "train_gearbox_rows": result.train_gearbox_rows,
        "test_engine_rows": result.test_engine_rows,
        "test_gearbox_rows": result.test_gearbox_rows,
        "correction_segments": result.correction_segments,
        "fallback_count": result.fallback_count,
        "metrics_improved": int((result.metric_comparison["status"] == "improved").sum())
        if not result.metric_comparison.empty
        else 0,
        "metrics_worse": int((result.metric_comparison["status"] == "worse").sum())
        if not result.metric_comparison.empty
        else 0,
        "metrics_unchanged": int((result.metric_comparison["status"] == "unchanged").sum())
        if not result.metric_comparison.empty
        else 0,
    }
    paths = {
        "validation_summary": out / "validation_summary.json",
        "validation_metric_comparison": out / "validation_metric_comparison.csv",
        "validation_worst_regressions": out / "validation_worst_regressions.csv",
        "validation_best_improvements": out / "validation_best_improvements.csv",
        "validation_group_comparison": out / "validation_group_comparison.csv",
    }
    paths["validation_summary"].write_text(json.dumps(summary, indent=2), encoding="utf-8")
    result.metric_comparison.to_csv(paths["validation_metric_comparison"], index=False)
    result.worst_regressions.to_csv(paths["validation_worst_regressions"], index=False)
    result.best_improvements.to_csv(paths["validation_best_improvements"], index=False)
    result.group_comparison.to_csv(paths["validation_group_comparison"], index=False)
    return paths


def format_holdout_validation_summary(result: HoldoutValidationResult) -> list[str]:
    """Render a concise CLI summary."""
    lines = [
        "Holdout save calibration validation",
        "=" * 72,
        f"Train saves: {len(result.train_saves)} "
        f"({result.train_engine_rows} engine rows, {result.train_gearbox_rows} gearbox rows)",
        f"Test saves: {len(result.test_saves)} "
        f"({result.test_engine_rows} engine designs, {result.test_gearbox_rows} gearbox designs)",
        f"Train correction segments: {result.correction_segments}",
        f"Formula fallback rows: {result.fallback_count}",
        "",
        "Metric comparison:",
    ]
    if result.metric_comparison.empty:
        lines.append("  (no metrics evaluated)")
    else:
        for _, row in result.metric_comparison.iterrows():
            lines.append(
                f"  {row['kind']} {row['metric']}: {row['status']} "
                f"(formula MAE={row['formula_only_mae']:.2f}, "
                f"calibrated MAE={row['save_calibrated_mae']:.2f}, "
                f"improvement={row['absolute_improvement']:+.2f})"
            )
    return lines
