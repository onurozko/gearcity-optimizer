"""Validation and prediction-quality reports for generated save datasets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from gearcity_optimizer.reports.save_dataset_residuals import (
    RELIABLE_MEAN_PCT_ERROR,
    WEAK_MEAN_PCT_ERROR,
    annotate_correction_confidence,
    build_actual_vs_predicted_chart_data,
    engine_replay_metric_names,
    gearbox_replay_metric_names,
    metric_replay_columns,
)


@dataclass(frozen=True)
class DatasetQualityReport:
    """Aggregate validation output for generated save datasets."""

    dataset_dir: Path
    engine_row_count: int
    gearbox_row_count: int
    missing_values: pd.DataFrame
    metric_support: pd.DataFrame
    metric_errors: pd.DataFrame
    worst_errors: pd.DataFrame
    grouped_errors: pd.DataFrame
    reliable_metrics: pd.DataFrame
    weak_metrics: pd.DataFrame
    strongest_residuals: pd.DataFrame
    calibration_confidence: pd.DataFrame
    chart_data: pd.DataFrame


def load_generated_datasets(dataset_dir: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load engines.csv and gearboxes.csv from a generated dataset directory."""
    root = Path(dataset_dir)
    engine_path = root / "engines.csv"
    gearbox_path = root / "gearboxes.csv"
    if not engine_path.is_file() and (root / "calibration_engines.csv").is_file():
        engine_path = root / "calibration_engines.csv"
    if not gearbox_path.is_file() and (root / "calibration_gearboxes.csv").is_file():
        gearbox_path = root / "calibration_gearboxes.csv"

    engine_df = pd.read_csv(engine_path) if engine_path.is_file() else pd.DataFrame()
    gearbox_df = pd.read_csv(gearbox_path) if gearbox_path.is_file() else pd.DataFrame()
    return engine_df, gearbox_df


def missing_value_counts(df: pd.DataFrame, *, kind: str) -> pd.DataFrame:
    """Count missing values per column."""
    if df.empty:
        return pd.DataFrame(columns=["kind", "column", "missing_count", "row_count"])
    rows = [
        {
            "kind": kind,
            "column": column,
            "missing_count": int(df[column].isna().sum()),
            "row_count": len(df),
        }
        for column in df.columns
        if int(df[column].isna().sum()) > 0
    ]
    if not rows:
        return pd.DataFrame(columns=["kind", "column", "missing_count", "row_count"])
    return pd.DataFrame(rows).sort_values("missing_count", ascending=False)


def supported_metric_counts(
    engine_df: pd.DataFrame,
    gearbox_df: pd.DataFrame,
) -> pd.DataFrame:
    """Count rows with both actual and predicted values per replay metric."""
    rows: list[dict[str, object]] = []

    def _count(df: pd.DataFrame, kind: str, metrics: tuple[str, ...]) -> None:
        if df.empty:
            return
        for prefix in metrics:
            actual_col, predicted_col, _, _ = metric_replay_columns(prefix)
            if actual_col not in df.columns or predicted_col not in df.columns:
                continue
            actual = pd.to_numeric(df[actual_col], errors="coerce")
            predicted = pd.to_numeric(df[predicted_col], errors="coerce")
            supported = int((actual.notna() & predicted.notna()).sum())
            rows.append(
                {
                    "kind": kind,
                    "metric": prefix,
                    "supported_count": supported,
                    "row_count": len(df),
                }
            )

    _count(engine_df, "engine", engine_replay_metric_names())
    _count(gearbox_df, "gearbox", gearbox_replay_metric_names())
    if not rows:
        return pd.DataFrame(columns=["kind", "metric", "supported_count", "row_count"])
    return pd.DataFrame(rows)


def metric_error_summary(
    engine_df: pd.DataFrame,
    gearbox_df: pd.DataFrame,
) -> pd.DataFrame:
    """Compute mean/median absolute and percentage error by metric."""
    rows: list[dict[str, object]] = []

    def _summarize(df: pd.DataFrame, kind: str, metrics: tuple[str, ...]) -> None:
        if df.empty:
            return
        for prefix in metrics:
            actual_col, predicted_col, error_col, pct_col = metric_replay_columns(prefix)
            if actual_col not in df.columns or predicted_col not in df.columns:
                continue
            actual = pd.to_numeric(df[actual_col], errors="coerce")
            predicted = pd.to_numeric(df[predicted_col], errors="coerce")
            valid = actual.notna() & predicted.notna()
            if not valid.any():
                continue
            abs_error = pd.to_numeric(df.loc[valid, error_col], errors="coerce")
            if abs_error.isna().all():
                abs_error = (actual[valid] - predicted[valid]).abs()
            pct_error = pd.to_numeric(df.loc[valid, pct_col], errors="coerce")
            if pct_error.isna().all() and (actual[valid].abs() > 1e-6).any():
                pct_error = abs_error / actual[valid].abs() * 100.0
            rows.append(
                {
                    "kind": kind,
                    "metric": prefix,
                    "count": int(valid.sum()),
                    "mean_abs_error": float(abs_error.mean()),
                    "median_abs_error": float(abs_error.median()),
                    "mean_pct_error": float(pct_error.mean()),
                    "median_pct_error": float(pct_error.median()),
                }
            )

    _summarize(engine_df, "engine", engine_replay_metric_names())
    _summarize(gearbox_df, "gearbox", gearbox_replay_metric_names())
    if not rows:
        return pd.DataFrame(
            columns=[
                "kind",
                "metric",
                "count",
                "mean_abs_error",
                "median_abs_error",
                "mean_pct_error",
                "median_pct_error",
            ]
        )
    return pd.DataFrame(rows)


def worst_errors_by_metric(
    engine_df: pd.DataFrame,
    gearbox_df: pd.DataFrame,
    *,
    top_n: int = 10,
) -> pd.DataFrame:
    """Return the worst pct-error rows for each metric."""
    parts: list[pd.DataFrame] = []

    def _worst(df: pd.DataFrame, kind: str, metrics: tuple[str, ...]) -> None:
        if df.empty:
            return
        for prefix in metrics:
            pct_col = f"pct_error_{prefix}"
            if pct_col not in df.columns:
                continue
            base_cols = ["save", "design_id", "name", "year", "layout", "fuel_type", "gearbox_type"]
            selected_cols = [col for col in base_cols if col in df.columns] + [pct_col]
            subset = df[selected_cols].copy()
            subset = subset.rename(columns={pct_col: "pct_error"})
            subset["kind"] = kind
            subset["metric"] = prefix
            subset["pct_error"] = pd.to_numeric(subset["pct_error"], errors="coerce")
            subset = subset.dropna(subset=["pct_error"]).sort_values("pct_error", ascending=False)
            if subset.empty:
                continue
            parts.append(subset.head(top_n))

    _worst(engine_df, "engine", engine_replay_metric_names())
    _worst(gearbox_df, "gearbox", gearbox_replay_metric_names())
    if not parts:
        return pd.DataFrame(
            columns=[
                "save",
                "design_id",
                "name",
                "year",
                "layout",
                "fuel_type",
                "gearbox_type",
                "pct_error",
                "kind",
                "metric",
            ]
        )
    return pd.concat(parts, ignore_index=True)


def grouped_metric_errors(
    engine_df: pd.DataFrame,
    gearbox_df: pd.DataFrame,
) -> pd.DataFrame:
    """Aggregate pct error by year band and categorical groups where available."""
    chart = build_actual_vs_predicted_chart_data(engine_df, gearbox_df)
    if chart.empty:
        return pd.DataFrame(
            columns=[
                "kind",
                "metric",
                "year_band",
                "layout",
                "fuel_type",
                "gearbox_type",
                "count",
                "mean_pct_error",
                "median_pct_error",
            ]
        )

    rows: list[pd.DataFrame] = []
    engine_groups = ["year_band", "layout", "fuel_type"]
    for group_cols in (["year_band"], ["year_band", "layout"], ["year_band", "layout", "fuel_type"]):
        subset = chart[chart["kind"] == "engine"]
        if subset.empty:
            continue
        grouped = (
            subset.groupby(["metric", *group_cols], dropna=False)["pct_error"]
            .agg(["count", "mean", "median"])
            .reset_index()
            .rename(columns={"mean": "mean_pct_error", "median": "median_pct_error"})
        )
        grouped["kind"] = "engine"
        if "gearbox_type" not in grouped.columns:
            grouped["gearbox_type"] = ""
        rows.append(grouped)

    for group_cols in (["year_band"], ["year_band", "gearbox_type"]):
        subset = chart[chart["kind"] == "gearbox"]
        if subset.empty:
            continue
        grouped = (
            subset.groupby(["metric", *group_cols], dropna=False)["pct_error"]
            .agg(["count", "mean", "median"])
            .reset_index()
            .rename(columns={"mean": "mean_pct_error", "median": "median_pct_error"})
        )
        grouped["kind"] = "gearbox"
        for col in ("layout", "fuel_type"):
            if col not in grouped.columns:
                grouped[col] = ""
        rows.append(grouped)

    if not rows:
        return pd.DataFrame()
    merged = pd.concat(rows, ignore_index=True)
    return merged.sort_values(["kind", "metric", "mean_pct_error"], ascending=[True, True, False])


def classify_metric_reliability(metric_errors: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split metrics into reliable and weak buckets using mean pct error."""
    if metric_errors.empty:
        empty = pd.DataFrame(columns=[*metric_errors.columns, "reliability"])
        return empty, empty.copy()

    classified = metric_errors.copy()
    classified["reliability"] = classified["mean_pct_error"].apply(
        lambda value: (
            "reliable"
            if value <= RELIABLE_MEAN_PCT_ERROR
            else "weak"
            if value >= WEAK_MEAN_PCT_ERROR
            else "mixed"
        )
    )
    reliable = classified[classified["reliability"] == "reliable"].copy()
    weak = classified[classified["reliability"] == "weak"].copy()
    return reliable, weak


def strongest_systematic_residuals(grouped_errors: pd.DataFrame, *, top_n: int = 12) -> pd.DataFrame:
    """Return the largest grouped mean pct errors."""
    if grouped_errors.empty:
        return grouped_errors.copy()
    frame = grouped_errors.copy()
    frame = frame[frame["count"] >= 2]
    return frame.sort_values("mean_pct_error", ascending=False).head(top_n)


def load_calibration_confidence_table(dataset_dir: str | Path) -> pd.DataFrame:
    """Load residual correction tables and expose confidence by metric/group."""
    root = Path(dataset_dir)
    parts: list[pd.DataFrame] = []
    for kind, filename in (
        ("engine", "engine_residual_corrections.csv"),
        ("gearbox", "gearbox_residual_corrections.csv"),
    ):
        path = root / filename
        if not path.is_file():
            continue
        frame = pd.read_csv(path)
        if frame.empty:
            continue
        annotated = annotate_correction_confidence(frame)
        annotated["kind"] = kind
        annotated["matched_group"] = annotated.apply(
            lambda row: "|".join(
                f"{col}={row[col]}"
                for col in (
                    "metric",
                    "year_band",
                    "layout",
                    "fuel_type",
                    "gearbox_type",
                )
                if col in annotated.columns and str(row.get(col, "")) not in {"", "nan"}
            ),
            axis=1,
        )
        parts.append(
            annotated[
                [
                    "kind",
                    "metric",
                    "matched_group",
                    "count",
                    "mean_signed_pct",
                    "mean_abs_pct",
                    "suggested_scale",
                    "confidence",
                ]
            ].rename(
                columns={
                    "count": "sample_count",
                    "suggested_scale": "correction_value",
                }
            )
        )
    if not parts:
        return pd.DataFrame(
            columns=[
                "kind",
                "metric",
                "matched_group",
                "sample_count",
                "mean_signed_pct",
                "mean_abs_pct",
                "correction_value",
                "confidence",
            ]
        )
    return pd.concat(parts, ignore_index=True)


def build_dataset_quality_report(
    dataset_dir: str | Path,
    *,
    engine_df: pd.DataFrame | None = None,
    gearbox_df: pd.DataFrame | None = None,
) -> DatasetQualityReport:
    """Build a full validation report from generated dataset CSV files."""
    root = Path(dataset_dir)
    if engine_df is None or gearbox_df is None:
        engine_df, gearbox_df = load_generated_datasets(root)

    missing = pd.concat(
        [
            missing_value_counts(engine_df, kind="engine"),
            missing_value_counts(gearbox_df, kind="gearbox"),
        ],
        ignore_index=True,
    )
    metric_support = supported_metric_counts(engine_df, gearbox_df)
    metric_errors = metric_error_summary(engine_df, gearbox_df)
    worst = worst_errors_by_metric(engine_df, gearbox_df)
    grouped = grouped_metric_errors(engine_df, gearbox_df)
    reliable, weak = classify_metric_reliability(metric_errors)
    strongest = strongest_systematic_residuals(grouped)
    confidence = load_calibration_confidence_table(root)
    chart_data = build_actual_vs_predicted_chart_data(engine_df, gearbox_df)

    return DatasetQualityReport(
        dataset_dir=root,
        engine_row_count=len(engine_df),
        gearbox_row_count=len(gearbox_df),
        missing_values=missing,
        metric_support=metric_support,
        metric_errors=metric_errors,
        worst_errors=worst,
        grouped_errors=grouped,
        reliable_metrics=reliable,
        weak_metrics=weak,
        strongest_residuals=strongest,
        calibration_confidence=confidence,
        chart_data=chart_data,
    )


def export_dataset_quality_report(
    report: DatasetQualityReport,
    output_dir: str | Path | None = None,
) -> dict[str, Path]:
    """Write quality report tables under generated/save_datasets/."""
    out = Path(output_dir) if output_dir is not None else report.dataset_dir
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "quality_summary": out / "quality_summary.json",
        "missing_values": out / "quality_missing_values.csv",
        "metric_support": out / "quality_metric_support.csv",
        "metric_errors": out / "quality_metric_errors.csv",
        "worst_errors": out / "quality_worst_errors.csv",
        "grouped_errors": out / "quality_grouped_errors.csv",
        "reliable_metrics": out / "quality_reliable_metrics.csv",
        "weak_metrics": out / "quality_weak_metrics.csv",
        "strongest_residuals": out / "quality_strongest_residuals.csv",
        "calibration_confidence": out / "quality_calibration_confidence.csv",
        "chart_data": out / "quality_chart_data.csv",
    }
    summary = {
        "dataset_dir": str(report.dataset_dir),
        "engine_row_count": report.engine_row_count,
        "gearbox_row_count": report.gearbox_row_count,
        "metric_count": len(report.metric_errors),
        "reliable_metric_count": len(report.reliable_metrics),
        "weak_metric_count": len(report.weak_metrics),
    }
    paths["quality_summary"].write_text(json.dumps(summary, indent=2), encoding="utf-8")
    report.missing_values.to_csv(paths["missing_values"], index=False)
    report.metric_support.to_csv(paths["metric_support"], index=False)
    report.metric_errors.to_csv(paths["metric_errors"], index=False)
    report.worst_errors.to_csv(paths["worst_errors"], index=False)
    report.grouped_errors.to_csv(paths["grouped_errors"], index=False)
    report.reliable_metrics.to_csv(paths["reliable_metrics"], index=False)
    report.weak_metrics.to_csv(paths["weak_metrics"], index=False)
    report.strongest_residuals.to_csv(paths["strongest_residuals"], index=False)
    report.calibration_confidence.to_csv(paths["calibration_confidence"], index=False)
    report.chart_data.to_csv(paths["chart_data"], index=False)
    return paths


def format_quality_report_summary(report: DatasetQualityReport) -> list[str]:
    """Render a concise text summary for CLI or logs."""
    lines = [
        "Save dataset quality report",
        "=" * 72,
        f"Dataset dir: {report.dataset_dir}",
        f"Engine rows: {report.engine_row_count}",
        f"Gearbox rows: {report.gearbox_row_count}",
        "",
        "Metric support:",
    ]
    if report.metric_support.empty:
        lines.append("  (none)")
    else:
        for _, row in report.metric_support.iterrows():
            lines.append(
                f"  {row['kind']} {row['metric']}: {row['supported_count']}/{row['row_count']}"
            )

    lines.extend(["", "Metric errors:"])
    if report.metric_errors.empty:
        lines.append("  (none)")
    else:
        for _, row in report.metric_errors.iterrows():
            lines.append(
                f"  {row['kind']} {row['metric']}: "
                f"mean_abs={row['mean_abs_error']:.2f}, "
                f"mean_pct={row['mean_pct_error']:.1f}%"
            )

    lines.extend(["", "Reliable metrics:"])
    if report.reliable_metrics.empty:
        lines.append("  (none)")
    else:
        for _, row in report.reliable_metrics.iterrows():
            lines.append(f"  {row['kind']} {row['metric']} mean_pct={row['mean_pct_error']:.1f}%")

    lines.extend(["", "Weak metrics:"])
    if report.weak_metrics.empty:
        lines.append("  (none)")
    else:
        for _, row in report.weak_metrics.iterrows():
            lines.append(f"  {row['kind']} {row['metric']} mean_pct={row['mean_pct_error']:.1f}%")

    lines.extend(["", "Calibration confidence segments:", f"  {len(report.calibration_confidence)}"])
    return lines
