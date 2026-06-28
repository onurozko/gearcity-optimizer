"""Build tabular datasets from save calibration reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from gearcity_optimizer.importers.save_schema import (
    SaveSchemaReport,
    format_save_schema_report,
    inspect_save_schema,
)
from gearcity_optimizer.reports.save_calibration import (
    MetricDelta,
    SaveCalibrationReport,
    calibrate_save_game,
)
from gearcity_optimizer.reports.save_calibration_features import (
    engine_fit_max_pct,
    fuel_family,
    gearbox_ratio_pattern,
    hp_torque_rpm_inconsistent,
    mod_bucket,
    reliability_stale,
    signed_pct_error,
    stale_gearbox_power_rating,
    valve_family,
)
from gearcity_optimizer.reports.save_dataset_quality import (
    build_dataset_quality_report,
    export_dataset_quality_report,
    format_quality_report_summary,
)
from gearcity_optimizer.reports.save_dataset_residuals import (
    build_residual_correction_tables,
    default_save_datasets_dir,
    export_residual_corrections,
    formula_error_summary,
    worst_prediction_gaps,
)

ENGINE_FEATURE_COLUMNS: tuple[str, ...] = (
    "year",
    "layout",
    "cylinders",
    "fuel_type",
    "induction",
    "valve",
    "bore",
    "stroke",
    "displacement",
    "slider_length",
    "slider_width",
    "slider_weight",
    "slider_rpm",
    "slider_torque",
    "slider_economy",
    "slider_materials",
    "slider_techniques",
    "slider_tech",
    "slider_components",
    "slider_design_performance",
    "slider_design_fuel",
    "slider_design_dependability",
    "design_pace",
)

ENGINE_TARGET_COLUMNS: tuple[str, ...] = (
    "actual_rpm",
    "actual_mpg",
)

ENGINE_LEGACY_ANALYSIS_COLUMNS: tuple[str, ...] = (
    "displacement_cc",
    "bore_mm",
    "stroke_mm",
    "layout_weight_sub",
    "layout_arrangement",
    "slider_displace",
    "slider_torq",
    "slider_eco",
)

ENGINE_REPLAY_METRICS: tuple[tuple[str, str], ...] = (
    ("length", "length_in"),
    ("width", "width_in"),
    ("weight", "weight_lb"),
    ("torque", "torque_lbft"),
    ("horsepower", "horsepower"),
    ("power_rating", "engine_power_rating"),
    ("fuel_rating", "engine_fuel_rating"),
    ("reliability_rating", "engine_reliability_rating"),
    ("overall_rating", "overall_rating"),
)

GEARBOX_FEATURE_COLUMNS: tuple[str, ...] = (
    "year",
    "gears",
    "gearbox_type",
    "reverse",
    "overdrive",
    "limited_slip",
    "transaxle",
    "low_ratio",
    "high_ratio",
    "torque_input_ratio",
    "tech_material",
    "tech_parts",
    "tech_techniques",
    "tech_tech",
    "design_performance",
    "design_fuel",
    "design_dependability",
    "design_ease",
    "sub_weight",
    "sub_complexity",
    "sub_smoothness",
    "sub_comfort",
    "sub_fuel",
    "sub_performance",
    "design_pace",
)

GEARBOX_TARGET_COLUMNS: tuple[str, ...] = ()

GEARBOX_LEGACY_ANALYSIS_COLUMNS: tuple[str, ...] = (
    "year_built",
    "lo_ratio",
    "hi_ratio",
)

GEARBOX_REPLAY_METRICS: tuple[tuple[str, str], ...] = (
    ("max_torque", "max_torque_lbft"),
    ("weight", "weight_lb"),
    ("power_rating", "power_rating"),
    ("fuel_rating", "fuel_rating"),
    ("performance_rating", "performance_rating"),
    ("reliability_rating", "reliability_rating"),
    ("overall_rating", "overall_rating"),
)

ENGINE_DATASET_META_COLUMNS: tuple[str, ...] = (
    "save",
    "kind",
    "design_id",
    "name",
    "fuel_family",
    "valve_family",
    "mod_amount",
    "mod_bucket",
    "formula_supported",
    "calibration_mode",
)

GEARBOX_DATASET_META_COLUMNS: tuple[str, ...] = (
    "save",
    "kind",
    "design_id",
    "name",
    "mod_amount",
    "mod_bucket",
    "ratio_pattern",
    "calibration_mode",
)


def engine_dataset_columns() -> tuple[str, ...]:
    """Stable ordered column list for engine calibration datasets."""
    replay_cols: list[str] = []
    for prefix, _ in ENGINE_REPLAY_METRICS:
        replay_cols.extend(
            [
                f"actual_{prefix}",
                f"predicted_{prefix}",
                f"error_{prefix}",
                f"pct_error_{prefix}",
            ]
        )
    legacy_cols = (
        "err_length_pct",
        "err_width_pct",
        "err_torque_pct",
        "err_horsepower_pct",
        "err_weight_pct",
        "err_power_rating_pct",
        "err_fuel_rating_pct",
        "err_reliability_pct",
        "err_overall_pct",
        "fit_max_pct",
        "signed_torque_pct",
        "signed_horsepower_pct",
        "signed_length_pct",
        "signed_width_pct",
        "game_torque",
        "pred_torque",
        "game_horsepower",
        "pred_horsepower",
        "game_rpm",
        "hp_rpm_inconsistent",
        "reliability_stale",
        "note_count",
    )
    return (
        *ENGINE_DATASET_META_COLUMNS,
        *ENGINE_FEATURE_COLUMNS,
        *ENGINE_TARGET_COLUMNS,
        *replay_cols,
        *ENGINE_LEGACY_ANALYSIS_COLUMNS,
        *legacy_cols,
    )


def gearbox_dataset_columns() -> tuple[str, ...]:
    """Stable ordered column list for gearbox calibration datasets."""
    replay_cols: list[str] = []
    for prefix, _ in GEARBOX_REPLAY_METRICS:
        replay_cols.extend(
            [
                f"actual_{prefix}",
                f"predicted_{prefix}",
                f"error_{prefix}",
                f"pct_error_{prefix}",
            ]
        )
    legacy_cols = (
        "err_max_torque_pct",
        "err_weight_pct",
        "err_power_rating_pct",
        "err_fuel_rating_pct",
        "err_performance_pct",
        "err_reliability_pct",
        "err_overall_pct",
        "signed_max_torque_pct",
        "game_max_torque",
        "pred_max_torque",
        "stale_power_rating",
        "note_count",
    )
    return (
        *GEARBOX_DATASET_META_COLUMNS,
        *GEARBOX_FEATURE_COLUMNS,
        *GEARBOX_TARGET_COLUMNS,
        *replay_cols,
        *GEARBOX_LEGACY_ANALYSIS_COLUMNS,
        *legacy_cols,
    )


def _metric_value(deltas: tuple[MetricDelta, ...], metric: str, field: str) -> float:
    for delta in deltas:
        if delta.metric == metric:
            if field == "game":
                return delta.game_value
            if field == "pred":
                return delta.predicted_value
            if field == "abs":
                return delta.abs_error
            return delta.pct_error or 0.0
    return 0.0


def _replay_columns_from_deltas(
    deltas: tuple[MetricDelta, ...],
    metrics: tuple[tuple[str, str], ...],
) -> dict[str, float | None]:
    """Build actual/predicted/error/pct_error columns for supported metrics."""
    out: dict[str, float | None] = {}
    delta_map = {delta.metric: delta for delta in deltas}
    for prefix, metric_key in metrics:
        delta = delta_map.get(metric_key)
        if delta is None:
            out[f"actual_{prefix}"] = None
            out[f"predicted_{prefix}"] = None
            out[f"error_{prefix}"] = None
            out[f"pct_error_{prefix}"] = None
            continue
        out[f"actual_{prefix}"] = delta.game_value
        out[f"predicted_{prefix}"] = delta.predicted_value
        out[f"error_{prefix}"] = delta.abs_error
        out[f"pct_error_{prefix}"] = delta.pct_error
    return out


def _calibration_mode(*, apply_corrections: bool) -> str:
    return "save_calibrated" if apply_corrections else "formula_only"


def engine_rows_from_report(
    report: SaveCalibrationReport,
    *,
    save_label: str | None = None,
    apply_corrections: bool = True,
) -> list[dict[str, object]]:
    """Flatten engine calibration results into dataset rows."""
    label = save_label or report.snapshot.path.name
    rows: list[dict[str, object]] = []
    for item in report.engines:
        record = item.record
        layout = item.layout
        deltas = item.deltas
        replay = _replay_columns_from_deltas(deltas, ENGINE_REPLAY_METRICS)
        rows.append(
            {
                "save": label,
                "kind": "engine",
                "design_id": record.engine_id,
                "name": record.name,
                "year": record.year_built,
                "layout": record.layout,
                "cylinders": record.cylinder_count,
                "fuel_type": record.fuel_type,
                "induction": record.induction,
                "valve": record.valve,
                "bore": record.bore,
                "stroke": record.stroke,
                "displacement": record.displacement_cc,
                "slider_length": record.slider_length,
                "slider_width": record.slider_width,
                "slider_weight": record.slider_weight,
                "slider_rpm": record.slider_rpm,
                "slider_torque": record.slider_torq,
                "slider_economy": record.slider_eco,
                "slider_materials": record.slider_materials,
                "slider_techniques": record.slider_techniques,
                "slider_tech": record.slider_tech,
                "slider_components": record.slider_components,
                "slider_design_performance": record.slider_design_performance,
                "slider_design_fuel": record.slider_design_fuel,
                "slider_design_dependability": record.slider_design_dependability,
                "design_pace": record.design_pace,
                "actual_rpm": record.rpm,
                "actual_mpg": record.fuel_mpg,
                **replay,
                "fuel_family": fuel_family(record.fuel_type),
                "valve_family": valve_family(record.valve),
                "mod_amount": record.mod_amount,
                "mod_bucket": mod_bucket(record.mod_amount),
                "displacement_cc": record.displacement_cc,
                "bore_mm": record.bore,
                "stroke_mm": record.stroke,
                "layout_weight_sub": layout.layout_weight if layout is not None else None,
                "layout_arrangement": (
                    layout.cylinder_length_arrangement if layout is not None else None
                ),
                "slider_displace": record.slider_displace,
                "slider_torq": record.slider_torq,
                "slider_eco": record.slider_eco,
                "err_length_pct": _metric_value(deltas, "length_in", "pct"),
                "err_width_pct": _metric_value(deltas, "width_in", "pct"),
                "err_torque_pct": _metric_value(deltas, "torque_lbft", "pct"),
                "err_horsepower_pct": _metric_value(deltas, "horsepower", "pct"),
                "err_weight_pct": _metric_value(deltas, "weight_lb", "pct"),
                "err_power_rating_pct": _metric_value(deltas, "engine_power_rating", "pct"),
                "err_fuel_rating_pct": _metric_value(deltas, "engine_fuel_rating", "pct"),
                "err_reliability_pct": _metric_value(
                    deltas, "engine_reliability_rating", "pct"
                ),
                "err_overall_pct": _metric_value(deltas, "overall_rating", "pct"),
                "fit_max_pct": engine_fit_max_pct(item),
                "signed_torque_pct": signed_pct_error(
                    record.torque_lbft,
                    _metric_value(deltas, "torque_lbft", "pred"),
                ),
                "signed_horsepower_pct": signed_pct_error(
                    record.horsepower,
                    _metric_value(deltas, "horsepower", "pred"),
                ),
                "signed_length_pct": signed_pct_error(
                    record.length_in,
                    _metric_value(deltas, "length_in", "pred"),
                ),
                "signed_width_pct": signed_pct_error(
                    record.width_in,
                    _metric_value(deltas, "width_in", "pred"),
                ),
                "formula_supported": fuel_family(record.fuel_type)
                in {"gasoline", "diesel"},
                "calibration_mode": _calibration_mode(apply_corrections=apply_corrections),
                "game_torque": record.torque_lbft,
                "pred_torque": _metric_value(deltas, "torque_lbft", "pred"),
                "game_horsepower": record.horsepower,
                "pred_horsepower": _metric_value(deltas, "horsepower", "pred"),
                "game_rpm": record.rpm,
                "hp_rpm_inconsistent": hp_torque_rpm_inconsistent(
                    record.horsepower, record.torque_lbft, record.rpm
                ),
                "reliability_stale": reliability_stale(
                    record.static_engine_reliability_rating,
                    record.engine_reliability_rating,
                ),
                "note_count": len(item.notes),
            }
        )
    return rows


def gearbox_rows_from_report(
    report: SaveCalibrationReport,
    *,
    save_label: str | None = None,
    apply_corrections: bool = True,
) -> list[dict[str, object]]:
    """Flatten gearbox calibration results into dataset rows."""
    label = save_label or report.snapshot.path.name
    rows: list[dict[str, object]] = []
    for item in report.gearboxes:
        record = item.record
        deltas = item.deltas
        replay = _replay_columns_from_deltas(deltas, GEARBOX_REPLAY_METRICS)
        rows.append(
            {
                "save": label,
                "kind": "gearbox",
                "design_id": record.gearbox_id,
                "name": record.name,
                "year": record.year_built,
                "gears": record.gears,
                "gearbox_type": record.gearbox_type,
                "reverse": record.has_reverse,
                "overdrive": record.has_overdrive,
                "limited_slip": record.has_limited_slip,
                "transaxle": record.has_transaxle,
                "low_ratio": record.low_ratio,
                "high_ratio": record.high_ratio,
                "torque_input_ratio": record.torque_input_ratio,
                "tech_material": record.tech_material,
                "tech_parts": record.tech_parts,
                "tech_techniques": record.tech_techniques,
                "tech_tech": record.tech_tech,
                "design_performance": record.design_performance,
                "design_fuel": record.design_fuel,
                "design_dependability": record.design_dependability,
                "design_ease": record.design_ease,
                "sub_weight": record.sub_weight,
                "sub_complexity": record.sub_complexity,
                "sub_smoothness": record.sub_smoothness,
                "sub_comfort": record.sub_comfort,
                "sub_fuel": record.sub_fuel,
                "sub_performance": record.sub_performance,
                "design_pace": record.design_pace,
                **replay,
                "year_built": record.year_built,
                "mod_amount": record.mod_amount,
                "mod_bucket": mod_bucket(record.mod_amount),
                "ratio_pattern": gearbox_ratio_pattern(
                    record.low_ratio,
                    record.high_ratio,
                ),
                "lo_ratio": record.low_ratio,
                "hi_ratio": record.high_ratio,
                "err_max_torque_pct": _metric_value(deltas, "max_torque_lbft", "pct"),
                "err_weight_pct": _metric_value(deltas, "weight_lb", "pct"),
                "err_power_rating_pct": _metric_value(deltas, "power_rating", "pct"),
                "err_fuel_rating_pct": _metric_value(deltas, "fuel_rating", "pct"),
                "err_performance_pct": _metric_value(deltas, "performance_rating", "pct"),
                "err_reliability_pct": _metric_value(
                    deltas, "reliability_rating", "pct"
                ),
                "err_overall_pct": _metric_value(deltas, "overall_rating", "pct"),
                "signed_max_torque_pct": signed_pct_error(
                    record.max_torque_input_lbft,
                    _metric_value(deltas, "max_torque_lbft", "pred"),
                ),
                "calibration_mode": _calibration_mode(apply_corrections=apply_corrections),
                "game_max_torque": record.max_torque_input_lbft,
                "pred_max_torque": _metric_value(deltas, "max_torque_lbft", "pred"),
                "stale_power_rating": stale_gearbox_power_rating(item),
                "note_count": len(item.notes),
            }
        )
    return rows


def build_calibration_frames(
    reports: list[SaveCalibrationReport],
    *,
    save_labels: list[str] | None = None,
    apply_corrections: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build engine and gearbox DataFrames from one or more calibration reports."""
    engine_rows: list[dict[str, object]] = []
    gearbox_rows: list[dict[str, object]] = []
    for index, report in enumerate(reports):
        label = None
        if save_labels is not None and index < len(save_labels):
            label = save_labels[index]
        engine_rows.extend(
            engine_rows_from_report(
                report,
                save_label=label,
                apply_corrections=apply_corrections,
            )
        )
        gearbox_rows.extend(
            gearbox_rows_from_report(
                report,
                save_label=label,
                apply_corrections=apply_corrections,
            )
        )
    engine_df = pd.DataFrame(engine_rows)
    gearbox_df = pd.DataFrame(gearbox_rows)
    if not engine_df.empty:
        engine_df = engine_df.reindex(columns=list(engine_dataset_columns()), fill_value=None)
    if not gearbox_df.empty:
        gearbox_df = gearbox_df.reindex(columns=list(gearbox_dataset_columns()), fill_value=None)
    return engine_df, gearbox_df


def metrics_long_frame(
    engine_df: pd.DataFrame,
    gearbox_df: pd.DataFrame,
) -> pd.DataFrame:
    """Melt pct-error columns into long format for plotting and aggregation."""
    engine_metrics = [
        c for c in engine_df.columns if c.startswith("err_") and c.endswith("_pct")
    ]
    gearbox_metrics = [
        c for c in gearbox_df.columns if c.startswith("err_") and c.endswith("_pct")
    ]
    parts: list[pd.DataFrame] = []
    if not engine_df.empty and engine_metrics:
        parts.append(
            engine_df[["save", "kind", "design_id", *engine_metrics]].melt(
                id_vars=["save", "kind", "design_id"],
                var_name="metric",
                value_name="pct_error",
            )
        )
    if not gearbox_df.empty and gearbox_metrics:
        parts.append(
            gearbox_df[["save", "kind", "design_id", *gearbox_metrics]].melt(
                id_vars=["save", "kind", "design_id"],
                var_name="metric",
                value_name="pct_error",
            )
        )
    if not parts:
        return pd.DataFrame(columns=["save", "kind", "design_id", "metric", "pct_error"])
    return pd.concat(parts, ignore_index=True)


def export_calibration_dataset(
    reports: list[SaveCalibrationReport],
    output_dir: str | Path,
    *,
    save_labels: list[str] | None = None,
    apply_corrections: bool = True,
) -> dict[str, Path]:
    """Write calibration datasets to CSV files."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    engine_df, gearbox_df = build_calibration_frames(
        reports,
        save_labels=save_labels,
        apply_corrections=apply_corrections,
    )
    long_df = metrics_long_frame(engine_df, gearbox_df)
    paths = {
        "engines": out / "calibration_engines.csv",
        "gearboxes": out / "calibration_gearboxes.csv",
        "metrics_long": out / "calibration_metrics_long.csv",
    }
    engine_df.to_csv(paths["engines"], index=False)
    gearbox_df.to_csv(paths["gearboxes"], index=False)
    long_df.to_csv(paths["metrics_long"], index=False)
    return paths


def schema_summaries_for_saves(save_paths: list[str | Path]) -> list[SaveSchemaReport]:
    """Inspect schema for each save path."""
    return [inspect_save_schema(path) for path in save_paths]


def build_save_dataset_pipeline(
    save_paths: list[str | Path],
    *,
    company_id: int | None = 0,
    output_dir: str | Path | None = None,
    apply_corrections: bool = True,
    min_correction_count: int = 3,
) -> dict[str, Any]:
    """Run full deterministic save dataset extraction, replay, and export."""
    labels = [Path(path).name for path in save_paths]
    schema_reports = schema_summaries_for_saves(save_paths)
    reports = [
        calibrate_save_game(
            str(path),
            company_id=company_id,
            engine_limit=None,
            gearbox_limit=None,
            apply_corrections=apply_corrections,
        )
        for path in save_paths
    ]
    engine_df, gearbox_df = build_calibration_frames(
        reports,
        save_labels=labels,
        apply_corrections=apply_corrections,
    )
    error_summary = formula_error_summary(engine_df, gearbox_df)
    worst_gaps = worst_prediction_gaps(engine_df, gearbox_df)
    engine_corr, gearbox_corr = build_residual_correction_tables(
        engine_df,
        gearbox_df,
        min_count=min_correction_count,
    )

    out = Path(output_dir) if output_dir is not None else default_save_datasets_dir()
    out.mkdir(parents=True, exist_ok=True)
    paths = export_calibration_dataset(
        reports,
        out,
        save_labels=labels,
        apply_corrections=apply_corrections,
    )
    paths["engines"] = out / "engines.csv"
    paths["gearboxes"] = out / "gearboxes.csv"
    engine_df.to_csv(paths["engines"], index=False)
    gearbox_df.to_csv(paths["gearboxes"], index=False)
    paths.update(export_residual_corrections(engine_corr, gearbox_corr, out))
    paths["formula_error_summary"] = out / "formula_error_summary.csv"
    error_summary.to_csv(paths["formula_error_summary"], index=False)
    paths["worst_prediction_gaps"] = out / "worst_prediction_gaps.csv"
    worst_gaps.to_csv(paths["worst_prediction_gaps"], index=False)

    schema_payload = [
        {
            "save": report.path.name,
            "tables": [
                {
                    "name": table.name,
                    "row_count": table.row_count,
                    "columns": [column.name for column in table.columns],
                    "read_error": table.read_error,
                }
                for table in report.tables
            ],
            "missing_expected_tables": list(report.missing_expected_tables),
            "read_errors": list(report.read_errors),
        }
        for report in schema_reports
    ]
    paths["schema_summary"] = out / "schema_summary.json"
    paths["schema_summary"].write_text(
        json.dumps(schema_payload, indent=2),
        encoding="utf-8",
    )
    for index, report in enumerate(schema_reports):
        text_path = out / f"schema_{labels[index]}.txt"
        text_path.write_text(format_save_schema_report(report), encoding="utf-8")
        paths[f"schema_text_{labels[index]}"] = text_path

    quality_report = build_dataset_quality_report(
        out,
        engine_df=engine_df,
        gearbox_df=gearbox_df,
    )
    paths.update(export_dataset_quality_report(quality_report, out))

    return {
        "reports": reports,
        "schema_reports": schema_reports,
        "engine_df": engine_df,
        "gearbox_df": gearbox_df,
        "error_summary": error_summary,
        "worst_gaps": worst_gaps,
        "engine_corrections": engine_corr,
        "gearbox_corrections": gearbox_corr,
        "quality_report": quality_report,
        "paths": paths,
        "apply_corrections": apply_corrections,
    }


def format_dataset_pipeline_summary(result: dict[str, Any]) -> list[str]:
    """Render a short CLI summary for the save dataset pipeline."""
    engine_df: pd.DataFrame = result["engine_df"]
    gearbox_df: pd.DataFrame = result["gearbox_df"]
    error_summary: pd.DataFrame = result["error_summary"]
    worst_gaps: pd.DataFrame = result["worst_gaps"]
    engine_corr: pd.DataFrame = result["engine_corrections"]
    gearbox_corr: pd.DataFrame = result["gearbox_corrections"]
    schema_reports: list[SaveSchemaReport] = result["schema_reports"]

    lines = [
        "Save dataset pipeline",
        "=" * 72,
        f"Engines extracted: {len(engine_df)}",
        f"Gearboxes extracted: {len(gearbox_df)}",
        f"Calibration mode: {'save_calibrated' if result['apply_corrections'] else 'formula_only'}",
        "",
        "Schema summary:",
    ]
    for report in schema_reports:
        table_count = len(report.tables)
        engine_rows = next(
            (table.row_count for table in report.tables if table.name == "EngineInfo"),
            0,
        )
        gearbox_rows = next(
            (table.row_count for table in report.tables if table.name == "GearboxInfo"),
            0,
        )
        lines.append(
            f"  {report.path.name}: {table_count} tables, "
            f"EngineInfo={engine_rows}, GearboxInfo={gearbox_rows}"
        )
        if report.missing_expected_tables:
            lines.append(
                "    missing optional tables: "
                + ", ".join(report.missing_expected_tables)
            )

    lines.extend(["", "Formula error summary:"])
    if error_summary.empty:
        lines.append("  (no replay metrics)")
    else:
        for _, row in error_summary.iterrows():
            lines.append(
                f"  {row['kind']} {row['metric']}: "
                f"mean={row['mean_pct_error']:.1f}% "
                f"median={row['median_pct_error']:.1f}% "
                f"n={row['count']}"
            )

    lines.extend(["", "Worst prediction gaps:"])
    if worst_gaps.empty:
        lines.append("  (none)")
    else:
        for _, row in worst_gaps.head(5).iterrows():
            lines.append(
                f"  {row['kind']} {row['name']} ({row['metric']}): "
                f"{row['pct_error']:.1f}%"
            )

    lines.extend(
        [
            "",
            "Residual correction suggestions:",
            f"  engine segments: {len(engine_corr)}",
            f"  gearbox segments: {len(gearbox_corr)}",
        ]
    )
    if not engine_corr.empty:
        top = engine_corr.iloc[0]
        lines.append(
            f"  top engine: {top['metric']} {top['year_band']} layout={top['layout']} "
            f"fuel={top['fuel_type']} signed={top['mean_signed_pct']:+.1f}%"
        )
    if not gearbox_corr.empty:
        top = gearbox_corr.iloc[0]
        lines.append(
            f"  top gearbox: {top['metric']} {top['year_band']} "
            f"type={top['gearbox_type']} signed={top['mean_signed_pct']:+.1f}%"
        )
    return lines
