"""Build tabular datasets from save calibration reports."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from gearcity_optimizer.reports.save_calibration import SaveCalibrationReport
from gearcity_optimizer.reports.save_calibration_features import (
    delta_map,
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


def _metric_value(deltas: tuple, metric: str, field: str) -> float:
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


def engine_rows_from_report(
    report: SaveCalibrationReport,
    *,
    save_label: str | None = None,
) -> list[dict[str, object]]:
    """Flatten engine calibration results into dataset rows."""
    label = save_label or report.snapshot.path.name
    rows: list[dict[str, object]] = []
    for item in report.engines:
        record = item.record
        layout = item.layout
        deltas = item.deltas
        rows.append(
            {
                "save": label,
                "kind": "engine",
                "design_id": record.engine_id,
                "name": record.name,
                "year_built": record.year_built,
                "layout": record.layout,
                "fuel_type": record.fuel_type,
                "fuel_family": fuel_family(record.fuel_type),
                "valve": record.valve,
                "valve_family": valve_family(record.valve),
                "mod_amount": record.mod_amount,
                "mod_bucket": mod_bucket(record.mod_amount),
                "cylinders": record.cylinder_count,
                "displacement_cc": record.displacement_cc,
                "bore_mm": record.bore,
                "stroke_mm": record.stroke,
                "layout_weight_sub": layout.layout_weight if layout is not None else None,
                "layout_arrangement": (
                    layout.cylinder_length_arrangement if layout is not None else None
                ),
                "slider_displace": record.slider_displace,
                "slider_length": record.slider_length,
                "slider_width": record.slider_width,
                "slider_weight": record.slider_weight,
                "slider_rpm": record.slider_rpm,
                "slider_torq": record.slider_torq,
                "slider_eco": record.slider_eco,
                "slider_materials": record.slider_materials,
                "slider_components": record.slider_components,
                "slider_design_performance": record.slider_design_performance,
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
) -> list[dict[str, object]]:
    """Flatten gearbox calibration results into dataset rows."""
    label = save_label or report.snapshot.path.name
    rows: list[dict[str, object]] = []
    for item in report.gearboxes:
        record = item.record
        deltas = item.deltas
        rows.append(
            {
                "save": label,
                "kind": "gearbox",
                "design_id": record.gearbox_id,
                "name": record.name,
                "year_built": record.year_built,
                "gears": record.gears,
                "gearbox_type": record.gearbox_type,
                "mod_amount": record.mod_amount,
                "mod_bucket": mod_bucket(record.mod_amount),
                "ratio_pattern": gearbox_ratio_pattern(
                    record.low_ratio,
                    record.high_ratio,
                ),
                "lo_ratio": record.low_ratio,
                "hi_ratio": record.high_ratio,
                "torque_input_ratio": record.torque_input_ratio,
                "design_ease": record.design_ease,
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
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build engine and gearbox DataFrames from one or more calibration reports."""
    engine_rows: list[dict[str, object]] = []
    gearbox_rows: list[dict[str, object]] = []
    for index, report in enumerate(reports):
        label = None
        if save_labels is not None and index < len(save_labels):
            label = save_labels[index]
        engine_rows.extend(engine_rows_from_report(report, save_label=label))
        gearbox_rows.extend(gearbox_rows_from_report(report, save_label=label))
    engine_df = pd.DataFrame(engine_rows)
    gearbox_df = pd.DataFrame(gearbox_rows)
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
) -> dict[str, Path]:
    """Write calibration datasets to CSV files."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    engine_df, gearbox_df = build_calibration_frames(reports, save_labels=save_labels)
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
