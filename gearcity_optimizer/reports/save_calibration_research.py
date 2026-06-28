"""Data-science style analysis for save calibration datasets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from gearcity_optimizer.reports.save_calibration import SaveCalibrationReport, calibrate_save_game
from gearcity_optimizer.reports.save_calibration_analysis import format_calibration_analysis
from gearcity_optimizer.reports.save_calibration_dataset import (
    build_calibration_frames,
    export_calibration_dataset,
    metrics_long_frame,
)
from gearcity_optimizer.reports.save_calibration_corrections import (
    CalibrationCorrections,
    fit_calibration_corrections,
    format_mass_quality_summary,
    mass_quality_summary,
    save_calibration_corrections,
)
from gearcity_optimizer.reports.save_calibration_features import (
    ENGINE_SEGMENT_COLS,
    GEARBOX_SEGMENT_COLS,
)


ENGINE_NUMERIC_FEATURES = (
    "mod_amount",
    "cylinders",
    "displacement_cc",
    "bore_mm",
    "stroke_mm",
    "layout_weight_sub",
    "layout_arrangement",
    "slider_displace",
    "slider_length",
    "slider_width",
    "slider_weight",
    "slider_rpm",
    "slider_torq",
    "slider_eco",
    "slider_materials",
    "slider_components",
    "slider_design_performance",
)

ENGINE_TARGETS = (
    "fit_max_pct",
    "err_torque_pct",
    "err_horsepower_pct",
    "err_weight_pct",
    "err_length_pct",
    "err_width_pct",
)


@dataclass(frozen=True)
class FixBucket:
    """Suggested systematic fix area from grouped error analysis."""

    kind: str
    segment: str
    count: int
    metric: str
    mean_pct_error: float
    median_pct_error: float
    mean_signed_pct: float | None
    priority: str
    recommendation: str


def load_reports_from_saves(
    save_paths: list[str],
    *,
    company_id: int | None = None,
    corrections: CalibrationCorrections | None = None,
    apply_corrections: bool = False,
) -> list[SaveCalibrationReport]:
    return [
        calibrate_save_game(
            path,
            company_id=company_id,
            engine_limit=None,
            gearbox_limit=None,
            corrections=corrections,
            apply_corrections=apply_corrections,
        )
        for path in save_paths
    ]


def segment_group_stats(
    df: pd.DataFrame,
    segment_cols: tuple[str, ...],
    metric_col: str,
    *,
    signed_col: str | None = None,
    min_count: int = 2,
    min_mean_error: float = 10.0,
) -> pd.DataFrame:
    """Aggregate one metric by categorical segment columns."""
    if df.empty or metric_col not in df.columns:
        return pd.DataFrame()

    grouped = (
        df.groupby(list(segment_cols), dropna=False)[metric_col]
        .agg(["count", "mean", "median", "max"])
        .reset_index()
    )
    if signed_col and signed_col in df.columns:
        signed = (
            df.groupby(list(segment_cols), dropna=False)[signed_col]
            .mean()
            .reset_index(name="mean_signed_pct")
        )
        grouped = grouped.merge(signed, on=list(segment_cols), how="left")
    else:
        grouped["mean_signed_pct"] = None

    return grouped[
        (grouped["count"] >= min_count) & (grouped["mean"] >= min_mean_error)
    ].sort_values("mean", ascending=False)


def feature_correlations(
    df: pd.DataFrame,
    targets: tuple[str, ...],
    features: tuple[str, ...],
) -> pd.DataFrame:
    """Pearson correlation of numeric features against error targets."""
    rows: list[dict[str, object]] = []
    numeric = df[list(features)].apply(pd.to_numeric, errors="coerce")
    for target in targets:
        if target not in df.columns:
            continue
        target_series = pd.to_numeric(df[target], errors="coerce")
        for feature in features:
            feature_series = numeric[feature]
            valid = target_series.notna() & feature_series.notna()
            if valid.sum() < 3:
                continue
            corr = target_series[valid].corr(feature_series[valid])
            if pd.isna(corr):
                continue
            rows.append(
                {
                    "target": target,
                    "feature": feature,
                    "correlation": corr,
                    "abs_correlation": abs(corr),
                    "n": int(valid.sum()),
                }
            )
    if not rows:
        return pd.DataFrame(columns=["target", "feature", "correlation", "abs_correlation", "n"])
    return pd.DataFrame(rows).sort_values(["target", "abs_correlation"], ascending=[True, False])


def recommend_fix_buckets(
    engine_df: pd.DataFrame,
    gearbox_df: pd.DataFrame,
) -> list[FixBucket]:
    """Suggest systematic fix buckets from high-error grouped segments."""
    buckets: list[FixBucket] = []

    gas = engine_df[engine_df["fuel_family"] == "gasoline"] if not engine_df.empty else engine_df
    for metric, signed, recommendation_prefix in (
        ("err_torque_pct", "signed_torque_pct", "Investigate torque formula mapping for"),
        ("err_horsepower_pct", "signed_horsepower_pct", "Investigate RPM/HP mapping for"),
        ("fit_max_pct", None, "Investigate physical fit formula for"),
    ):
        stats = segment_group_stats(
            gas,
            ENGINE_SEGMENT_COLS,
            metric,
            signed_col=signed,
            min_count=2,
            min_mean_error=8.0 if metric != "fit_max_pct" else 5.0,
        )
        for _, row in stats.iterrows():
            segment = "|".join(f"{col}={row[col]}" for col in ENGINE_SEGMENT_COLS)
            bias = "over-predicting" if (row.get("mean_signed_pct") or 0) > 0 else "under-predicting"
            buckets.append(
                FixBucket(
                    kind="engine",
                    segment=segment,
                    count=int(row["count"]),
                    metric=metric,
                    mean_pct_error=float(row["mean"]),
                    median_pct_error=float(row["median"]),
                    mean_signed_pct=(
                        float(row["mean_signed_pct"])
                        if row.get("mean_signed_pct") is not None
                        and not pd.isna(row["mean_signed_pct"])
                        else None
                    ),
                    priority="high" if row["mean"] >= 15 else "medium",
                    recommendation=(
                        f"{recommendation_prefix} {segment} "
                        f"(mean {row['mean']:.1f}%, {bias})."
                    ),
                )
            )

    if not engine_df.empty:
        unsupported = (
            engine_df.groupby("fuel_family")["err_horsepower_pct"]
            .agg(["count", "mean"])
            .reset_index()
        )
        for _, row in unsupported.iterrows():
            if row["fuel_family"] in {"gasoline", "diesel"}:
                continue
            if row["count"] < 1 or row["mean"] < 20:
                continue
            buckets.append(
                FixBucket(
                    kind="engine",
                    segment=f"fuel_family={row['fuel_family']}",
                    count=int(row["count"]),
                    metric="err_horsepower_pct",
                    mean_pct_error=float(row["mean"]),
                    median_pct_error=float(row["mean"]),
                    mean_signed_pct=None,
                    priority="high",
                    recommendation=(
                        f"Add dedicated formula path for fuel_family={row['fuel_family']} "
                        f"(mean HP error {row['mean']:.1f}%)."
                    ),
                )
            )

    for metric, signed, recommendation_prefix in (
        ("err_max_torque_pct", "signed_max_torque_pct", "Investigate max torque mapping for"),
        ("err_power_rating_pct", None, "Treat stale ratings separately for"),
    ):
        stats = segment_group_stats(
            gearbox_df,
            GEARBOX_SEGMENT_COLS,
            metric,
            signed_col=signed,
            min_count=2,
            min_mean_error=12.0 if metric.startswith("err_max") else 100.0,
        )
        for _, row in stats.iterrows():
            segment = "|".join(f"{col}={row[col]}" for col in GEARBOX_SEGMENT_COLS)
            if metric == "err_power_rating_pct":
                rec = (
                    f"Likely stale stored ratings for {segment}; "
                    f"do not chase formula unless max torque is also bad."
                )
                priority = "low"
            else:
                bias = "over-predicting" if (row.get("mean_signed_pct") or 0) > 0 else "under-predicting"
                rec = (
                    f"{recommendation_prefix} {segment} "
                    f"(mean {row['mean']:.1f}%, {bias})."
                )
                priority = "high" if row["mean"] >= 20 else "medium"
            buckets.append(
                FixBucket(
                    kind="gearbox",
                    segment=segment,
                    count=int(row["count"]),
                    metric=metric,
                    mean_pct_error=float(row["mean"]),
                    median_pct_error=float(row["median"]),
                    mean_signed_pct=(
                        float(row["mean_signed_pct"])
                        if row.get("mean_signed_pct") is not None
                        and not pd.isna(row["mean_signed_pct"])
                        else None
                    ),
                    priority=priority,
                    recommendation=rec,
                )
            )

    buckets.sort(key=lambda item: (item.priority != "high", -item.mean_pct_error))
    return buckets


def outlier_designs(
    engine_df: pd.DataFrame,
    gearbox_df: pd.DataFrame,
    *,
    engine_metric: str = "err_torque_pct",
    gearbox_metric: str = "err_max_torque_pct",
    z_threshold: float = 2.0,
) -> pd.DataFrame:
    """Flag designs whose error is far above the kind-wide mean."""
    parts: list[pd.DataFrame] = []
    for df, kind, metric_col in (
        (engine_df, "engine", engine_metric),
        (gearbox_df, "gearbox", gearbox_metric),
    ):
        if df.empty or metric_col not in df.columns:
            continue
        series = pd.to_numeric(df[metric_col], errors="coerce")
        mean = series.mean()
        std = series.std(ddof=0)
        if std <= 1e-6:
            continue
        z = (series - mean) / std
        flagged = df[z >= z_threshold].copy()
        flagged["outlier_metric"] = metric_col
        flagged["outlier_z"] = z[z >= z_threshold]
        flagged["kind"] = kind
        parts.append(flagged)
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True)


def run_calibration_research(
    save_paths: list[str],
    *,
    company_id: int | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, object]:
    """Run full dataset export and analysis across one or more saves."""
    reports = load_reports_from_saves(save_paths, company_id=company_id)
    labels = [Path(path).name for path in save_paths]
    engine_df, gearbox_df = build_calibration_frames(reports, save_labels=labels)
    long_df = metrics_long_frame(engine_df, gearbox_df)
    gas = engine_df[engine_df["fuel_family"] == "gasoline"] if not engine_df.empty else engine_df
    corr_df = feature_correlations(gas, ENGINE_TARGETS, ENGINE_NUMERIC_FEATURES)
    buckets = recommend_fix_buckets(engine_df, gearbox_df)
    outliers = outlier_designs(engine_df, gearbox_df)

    paths: dict[str, Path] = {}
    if output_dir is not None:
        paths = export_calibration_dataset(reports, output_dir, save_labels=labels)
        out = Path(output_dir)
        corr_df.to_csv(out / "calibration_correlations.csv", index=False)
        pd.DataFrame([bucket.__dict__ for bucket in buckets]).to_csv(
            out / "calibration_fix_buckets.csv",
            index=False,
        )
        if not outliers.empty:
            outliers.to_csv(out / "calibration_outliers.csv", index=False)
        summary_path = out / "calibration_research_report.txt"
        summary_path.write_text(
            "\n".join(format_research_report(reports, engine_df, gearbox_df, buckets, corr_df)),
            encoding="utf-8",
        )
        paths["report"] = summary_path
        paths["correlations"] = out / "calibration_correlations.csv"
        paths["fix_buckets"] = out / "calibration_fix_buckets.csv"
        if not outliers.empty:
            paths["outliers"] = out / "calibration_outliers.csv"

    return {
        "reports": reports,
        "engine_df": engine_df,
        "gearbox_df": gearbox_df,
        "metrics_long_df": long_df,
        "correlations_df": corr_df,
        "fix_buckets": buckets,
        "outliers_df": outliers,
        "paths": paths,
    }


def format_research_report(
    reports: list[SaveCalibrationReport],
    engine_df: pd.DataFrame,
    gearbox_df: pd.DataFrame,
    buckets: list[FixBucket],
    correlations: pd.DataFrame,
) -> list[str]:
    """Render a data-science style research summary."""
    lines: list[str] = []
    lines.append("Calibration research report")
    lines.append("=" * 72)
    lines.append(
        f"Designs: {len(engine_df)} engines, {len(gearbox_df)} gearboxes "
        f"across {len(reports)} save(s)"
    )
    lines.append("")

    for report in reports:
        lines.extend(format_calibration_analysis(report))
        lines.append("-" * 72)
        lines.append("")

    lines.append("Recommended fix buckets (grouped, not one-by-one):")
    if not buckets:
        lines.append("  None above threshold.")
    else:
        for bucket in buckets[:12]:
            lines.append(
                f"  [{bucket.priority}] {bucket.kind} n={bucket.count} "
                f"{bucket.metric} mean={bucket.mean_pct_error:.1f}%"
            )
            lines.append(f"    {bucket.segment}")
            lines.append(f"    -> {bucket.recommendation}")
    lines.append("")

    lines.append("Top numeric correlations (gasoline engines only):")
    if correlations.empty:
        lines.append("  Not enough rows for correlation analysis.")
    else:
        for target in ENGINE_TARGETS:
            target_rows = correlations[correlations["target"] == target].head(5)
            if target_rows.empty:
                continue
            lines.append(f"  Target {target}:")
            for _, row in target_rows.iterrows():
                lines.append(
                    f"    {row['feature']}: corr={row['correlation']:+.3f} (n={row['n']})"
                )
    lines.append("")

    lines.append("Exported artifacts when --output is set:")
    lines.append("  calibration_engines.csv         one row per engine with features/errors")
    lines.append("  calibration_gearboxes.csv       one row per gearbox with features/errors")
    lines.append("  calibration_metrics_long.csv    long format for charts/pivot tables")
    lines.append("  calibration_correlations.csv    feature vs error correlations")
    lines.append("  calibration_fix_buckets.csv     grouped fix recommendations")
    lines.append("  calibration_outliers.csv        high-error outliers")
    lines.append("  calibration_research_report.txt")
    return lines


def run_calibration_fit(
    save_paths: list[str],
    *,
    company_id: int | None = None,
    output_dir: str | Path,
    min_count: int = 2,
    min_abs_signed_pct: float = 5.0,
) -> dict[str, object]:
    """Fit segment corrections from all saves and validate before/after quality."""
    labels = [Path(path).name for path in save_paths]
    baseline_reports = load_reports_from_saves(
        save_paths,
        company_id=company_id,
        apply_corrections=False,
    )
    engine_df, gearbox_df = build_calibration_frames(baseline_reports, save_labels=labels)
    before_summary = mass_quality_summary(engine_df, gearbox_df)

    corrections = fit_calibration_corrections(
        engine_df,
        gearbox_df,
        min_count=min_count,
        min_abs_signed_pct=min_abs_signed_pct,
    )

    corrected_reports = load_reports_from_saves(
        save_paths,
        company_id=company_id,
        corrections=corrections,
        apply_corrections=False,
    )
    corrected_engine_df, corrected_gearbox_df = build_calibration_frames(
        corrected_reports,
        save_labels=labels,
    )
    after_summary = mass_quality_summary(corrected_engine_df, corrected_gearbox_df)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    corrections_path = save_calibration_corrections(out / "calibration_corrections.json", corrections)
    export_calibration_dataset(corrected_reports, out, save_labels=labels)

    fit_report_lines = [
        "Calibration mass-fit report",
        "=" * 72,
        f"Saves: {len(save_paths)} | Engine segments fitted: {len(corrections.engine)} "
        f"| Gearbox segments fitted: {len(corrections.gearbox)}",
        "",
        *format_mass_quality_summary(before_summary, label="Before corrections (supported engines only):"),
        "",
        *format_mass_quality_summary(after_summary, label="After segment corrections (in-sample):"),
        "",
        "Top engine correction segments:",
    ]
    for key, item in sorted(
        corrections.engine.items(),
        key=lambda pair: max((abs(v) for v in pair[1].mean_signed.values()), default=0.0),
        reverse=True,
    )[:10]:
        signed = ", ".join(f"{metric}={value:+.1f}%" for metric, value in item.mean_signed.items())
        fit_report_lines.append(f"  n={item.count} {key} -> {signed}")
    fit_report_lines.extend(["", "Top gearbox correction segments:"])
    for key, item in sorted(
        corrections.gearbox.items(),
        key=lambda pair: max((abs(v) for v in pair[1].mean_signed.values()), default=0.0),
        reverse=True,
    )[:10]:
        signed = ", ".join(f"{metric}={value:+.1f}%" for metric, value in item.mean_signed.items())
        fit_report_lines.append(f"  n={item.count} {key} -> {signed}")

    fit_report_path = out / "calibration_fit_report.txt"
    fit_report_path.write_text("\n".join(fit_report_lines), encoding="utf-8")

    return {
        "corrections": corrections,
        "corrections_path": corrections_path,
        "fit_report_path": fit_report_path,
        "before_summary": before_summary,
        "after_summary": after_summary,
        "engine_df": corrected_engine_df,
        "gearbox_df": corrected_gearbox_df,
        "fit_report_lines": fit_report_lines,
    }
