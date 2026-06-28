"""Streamlit tab for save data extraction and formula calibration."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from gearcity_optimizer.importers.save_schema import format_save_schema_report, inspect_save_schema
from gearcity_optimizer.reports.save_calibration import (
    calibrate_save_game,
    format_engine_calibration_lines,
    format_gearbox_calibration_lines,
    report_to_csv_rows,
)
from gearcity_optimizer.reports.save_calibration_dataset import (
    build_save_dataset_pipeline,
    engine_dataset_columns,
    gearbox_dataset_columns,
)
from gearcity_optimizer.reports.save_calibration_research import recommend_fix_buckets
from gearcity_optimizer.reports.save_calibration_validation import run_holdout_validation

TAB_CAPTION = (
    "Upload one or more GearCity save databases (.db) from SaveGames to inspect schema, "
    "extract engine/gearbox datasets, compare wiki formula predictions, and review "
    "residual correction suggestions."
)


def calibration_summary_dataframe(report) -> pd.DataFrame:
    """Build a compact summary table for Streamlit display."""
    rows: list[dict[str, object]] = []
    for item in report.engines:
        record = item.record
        for delta in item.deltas:
            rows.append(
                {
                    "Kind": "engine",
                    "ID": record.engine_id,
                    "Name": record.name,
                    "Year": record.year_built,
                    "Layout": record.layout,
                    "Metric": delta.metric,
                    "Game": round(delta.game_value, 2),
                    "Predicted": round(delta.predicted_value, 2),
                    "Abs error": round(delta.abs_error, 2),
                    "Pct error": round(delta.pct_error, 1) if delta.pct_error is not None else None,
                }
            )
    for item in report.gearboxes:
        record = item.record
        for delta in item.deltas:
            rows.append(
                {
                    "Kind": "gearbox",
                    "ID": record.gearbox_id,
                    "Name": record.name,
                    "Year": record.year_built,
                    "Layout": "",
                    "Metric": delta.metric,
                    "Game": round(delta.game_value, 2),
                    "Predicted": round(delta.predicted_value, 2),
                    "Abs error": round(delta.abs_error, 2),
                    "Pct error": round(delta.pct_error, 1) if delta.pct_error is not None else None,
                }
            )
    return pd.DataFrame(rows)


def _resolve_save_paths(
    uploaded_files,
    manual_paths: str,
) -> list[Path]:
    paths: list[Path] = []
    for line in manual_paths.splitlines():
        candidate = line.strip().strip('"')
        if not candidate:
            continue
        path = Path(candidate)
        if path.is_file():
            paths.append(path)
        else:
            st.error(f"Save file not found: {path}")

    if uploaded_files:
        for uploaded in uploaded_files:
            suffix = Path(uploaded.name).suffix or ".db"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
                handle.write(uploaded.getbuffer())
                paths.append(Path(handle.name))
    return paths


def _schema_summary_table(schema_reports) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for report in schema_reports:
        engine_rows = next(
            (table.row_count for table in report.tables if table.name == "EngineInfo"),
            0,
        )
        gearbox_rows = next(
            (table.row_count for table in report.tables if table.name == "GearboxInfo"),
            0,
        )
        rows.append(
            {
                "Save": report.path.name,
                "Tables": len(report.tables),
                "EngineInfo rows": engine_rows,
                "GearboxInfo rows": gearbox_rows,
                "Missing optional tables": ", ".join(report.missing_expected_tables) or "(none)",
            }
        )
    return pd.DataFrame(rows)


def render_save_calibration_tab() -> None:
    """Render save upload, schema inspection, dataset extraction, and calibration output."""
    st.subheader("Save Data / Calibration")
    st.caption(TAB_CAPTION)

    uploaded = st.file_uploader(
        "GearCity save files (.db)",
        type=["db"],
        accept_multiple_files=True,
        key="save_calibration_upload",
    )
    manual_paths = st.text_area(
        "Or enter local paths (one per line)",
        placeholder="D:\\Games\\GearCity\\SaveGames\\my-save.db",
        key="save_calibration_paths",
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        company_id = st.number_input("Company ID (-1 for all)", min_value=-1, value=-1, step=1)
    with col2:
        limit = st.number_input("Max engines/gearboxes each (per save)", min_value=1, value=10, step=1)
    with col3:
        kind = st.selectbox("Compare", options=["all", "engine", "gearbox"], index=0)

    compare_all = st.checkbox("Compare all designs (ignore limit)", value=False)
    apply_corrections = st.checkbox(
        "Apply bundled save-calibrated segment corrections",
        value=True,
        help="When enabled, optimizer replay uses bundled corrections fitted from save data.",
    )
    run = st.button("Run save data pipeline", type="primary", key="save_calibration_run")

    if not run:
        st.info("Upload save files or enter paths, then click Run save data pipeline.")
        return

    save_paths = _resolve_save_paths(uploaded, manual_paths)
    if not save_paths:
        st.warning("Provide at least one save file before running the pipeline.")
        return

    try:
        schema_reports = [inspect_save_schema(path) for path in save_paths]
    except (FileNotFoundError, ValueError) as exc:
        st.error(str(exc))
        return

    st.markdown("#### Schema summary")
    st.dataframe(_schema_summary_table(schema_reports), use_container_width=True, hide_index=True)
    with st.expander("Schema details", expanded=len(save_paths) == 1):
        for report in schema_reports:
            st.text(format_save_schema_report(report))

    pipeline = None
    try:
        with st.spinner("Extracting datasets and replaying formulas..."):
            pipeline = build_save_dataset_pipeline(
                [str(path) for path in save_paths],
                company_id=company_id if company_id >= 0 else None,
                output_dir=None,
                apply_corrections=apply_corrections,
            )
    except Exception as exc:  # pragma: no cover - surfaced in UI for bad SQLite files
        st.error(f"Could not build save datasets: {exc}")
        return

    engine_df = pipeline["engine_df"]
    gearbox_df = pipeline["gearbox_df"]
    calibration_mode = (
        "save_calibrated" if apply_corrections else "formula_only"
    )
    st.markdown(
        f"**Calibration mode:** `{calibration_mode}`  \n"
        f"**Extracted rows:** {len(engine_df)} engines, {len(gearbox_df)} gearboxes"
    )

    st.markdown("#### Extracted row counts")
    counts = pd.DataFrame(
        [
            {
                "Save": label,
                "Engines extracted": int((engine_df["save"] == label).sum()) if not engine_df.empty else 0,
                "Gearboxes extracted": int((gearbox_df["save"] == label).sum())
                if not gearbox_df.empty
                else 0,
            }
            for label in engine_df["save"].unique().tolist()
            or gearbox_df["save"].unique().tolist()
            or [path.name for path in save_paths]
        ]
    )
    st.dataframe(counts, use_container_width=True, hide_index=True)

    quality_report = pipeline.get("quality_report")
    if quality_report is None:
        quality_report = build_dataset_quality_report(
            pipeline["paths"]["engines"].parent,
            engine_df=engine_df,
            gearbox_df=gearbox_df,
        )

    st.markdown("#### Dataset quality summary")
    quality_summary_rows = [
        {"Metric": "Engine rows", "Value": quality_report.engine_row_count},
        {"Metric": "Gearbox rows", "Value": quality_report.gearbox_row_count},
        {
            "Metric": "Columns with missing values",
            "Value": len(quality_report.missing_values),
        },
        {
            "Metric": "Supported replay metrics",
            "Value": len(quality_report.metric_support),
        },
    ]
    st.dataframe(quality_summary_rows, use_container_width=True, hide_index=True)
    if not quality_report.missing_values.empty:
        with st.expander("Missing value counts"):
            st.dataframe(quality_report.missing_values, use_container_width=True, hide_index=True)

    st.markdown("#### Formula error summary")
    if quality_report.metric_errors.empty:
        st.write("No replay metrics available.")
    else:
        st.dataframe(quality_report.metric_errors, use_container_width=True, hide_index=True)

    col_reliable, col_weak = st.columns(2)
    with col_reliable:
        st.markdown("**Reliable formulas**")
        if quality_report.reliable_metrics.empty:
            st.write("No metrics below the reliability threshold yet.")
        else:
            st.dataframe(quality_report.reliable_metrics, use_container_width=True, hide_index=True)
    with col_weak:
        st.markdown("**Weak formulas**")
        if quality_report.weak_metrics.empty:
            st.write("No metrics above the weak threshold.")
        else:
            st.dataframe(quality_report.weak_metrics, use_container_width=True, hide_index=True)

    st.markdown("#### Strongest systematic residuals")
    if quality_report.strongest_residuals.empty:
        st.write("No grouped residual patterns detected.")
    else:
        st.dataframe(quality_report.strongest_residuals, use_container_width=True, hide_index=True)

    st.markdown("#### Worst prediction gaps")
    if quality_report.worst_errors.empty:
        st.write("No large gaps detected.")
    else:
        st.dataframe(quality_report.worst_errors.head(20), use_container_width=True, hide_index=True)

    st.markdown("#### Calibration confidence by metric/group")
    if quality_report.calibration_confidence.empty:
        st.write("No residual correction segments met the minimum sample count.")
    else:
        st.dataframe(
            quality_report.calibration_confidence,
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("#### Correction suggestions")
    fix_buckets = recommend_fix_buckets(engine_df, gearbox_df)
    engine_corr = pipeline["engine_corrections"]
    gearbox_corr = pipeline["gearbox_corrections"]
    st.write(
        f"Grouped fix buckets: {len(fix_buckets)} | "
        f"Residual lookup segments: {len(engine_corr)} engine, {len(gearbox_corr)} gearbox"
    )
    if not fix_buckets:
        st.write("No grouped fix buckets above threshold.")
    else:
        bucket_rows = [
            {
                "Priority": bucket.priority,
                "Kind": bucket.kind,
                "Metric": bucket.metric,
                "Count": bucket.count,
                "Mean pct error": round(bucket.mean_pct_error, 1),
                "Recommendation": bucket.recommendation,
            }
            for bucket in fix_buckets[:12]
        ]
        st.dataframe(bucket_rows, use_container_width=True, hide_index=True)

    if not engine_corr.empty or not gearbox_corr.empty:
        with st.expander("Residual correction lookup (optional)"):
            if not engine_corr.empty:
                st.markdown("**Engine residual segments**")
                st.dataframe(engine_corr.head(20), use_container_width=True, hide_index=True)
            if not gearbox_corr.empty:
                st.markdown("**Gearbox residual segments**")
                st.dataframe(gearbox_corr.head(20), use_container_width=True, hide_index=True)

    st.markdown("#### Normalized datasets")
    if not engine_df.empty:
        st.caption(f"Engine columns ({len(engine_dataset_columns())} stable fields)")
        st.dataframe(engine_df.head(20), use_container_width=True, hide_index=True)
    if not gearbox_df.empty:
        st.caption(f"Gearbox columns ({len(gearbox_dataset_columns())} stable fields)")
        st.dataframe(gearbox_df.head(20), use_container_width=True, hide_index=True)

    st.markdown("#### Per-design calibration")
    for index, save_path in enumerate(save_paths):
        label = save_path.name
        try:
            report = calibrate_save_game(
                str(save_path),
                company_id=company_id if company_id >= 0 else None,
                engine_limit=None if compare_all else int(limit),
                gearbox_limit=None if compare_all else int(limit),
                apply_corrections=apply_corrections,
            )
        except Exception as exc:  # pragma: no cover
            st.error(f"Could not calibrate {label}: {exc}")
            continue

        year = report.snapshot.current_year
        st.markdown(
            f"**Save `{label}`** | current year: {year if year is not None else 'unknown'} | "
            f"compared {len(report.engines)} engines, {len(report.gearboxes)} gearboxes"
        )

        if report.engine_summary:
            engine_summary_rows = [
                {"Metric": key, "Value": round(value, 2)}
                for key, value in sorted(report.engine_summary.items())
            ]
            st.dataframe(engine_summary_rows, use_container_width=True, hide_index=True)

        if report.gearbox_summary:
            gearbox_summary_rows = [
                {"Metric": key, "Value": round(value, 2)}
                for key, value in sorted(report.gearbox_summary.items())
            ]
            st.dataframe(gearbox_summary_rows, use_container_width=True, hide_index=True)

        detail_rows = calibration_summary_dataframe(report)
        if not detail_rows.empty:
            filtered = detail_rows
            if kind != "all":
                filtered = detail_rows[detail_rows["Kind"] == kind]
            st.dataframe(filtered, use_container_width=True, hide_index=True)

            csv_rows = report_to_csv_rows(report)
            st.download_button(
                f"Download CSV ({label})",
                data=pd.DataFrame(csv_rows).to_csv(index=False),
                file_name=f"{Path(label).stem}-calibration.csv",
                mime="text/csv",
                key=f"download_csv_{index}",
            )

        if kind in {"engine", "all"} and report.engines:
            for item in report.engines:
                with st.expander(
                    f"Engine {item.record.engine_id}: {item.record.name}",
                    expanded=False,
                ):
                    for line in format_engine_calibration_lines(item):
                        st.text(line)

        if kind in {"gearbox", "all"} and report.gearboxes:
            for item in report.gearboxes:
                with st.expander(
                    f"Gearbox {item.record.gearbox_id}: {item.record.name}",
                    expanded=False,
                ):
                    for line in format_gearbox_calibration_lines(item):
                        st.text(line)

    combined = pd.concat(
        [engine_df, gearbox_df],
        ignore_index=True,
        sort=False,
    )
    if not combined.empty:
        st.download_button(
            "Download combined dataset CSV",
            data=combined.to_csv(index=False),
            file_name="save_calibration_dataset.csv",
            mime="text/csv",
            key="download_combined_dataset",
        )
        st.download_button(
            "Download chart data CSV",
            data=quality_report.chart_data.to_csv(index=False),
            file_name="quality_chart_data.csv",
            mime="text/csv",
            key="download_chart_data",
        )
        st.download_button(
            "Download schema summary JSON",
            data=json.dumps(
                [
                    {
                        "save": report.path.name,
                        "tables": [table.name for table in report.tables],
                        "missing_expected_tables": list(report.missing_expected_tables),
                    }
                    for report in schema_reports
                ],
                indent=2,
            ),
            file_name="save_schema_summary.json",
            mime="application/json",
            key="download_schema_json",
        )

    st.markdown("---")
    st.markdown("### Holdout validation (train vs test)")
    st.caption(
        "Build corrections from train saves only, then compare formula-only and "
        "save-calibrated predictions on held-out test saves."
    )
    train_uploads = st.file_uploader(
        "Train saves (.db)",
        type=["db"],
        accept_multiple_files=True,
        key="save_validation_train_upload",
    )
    test_uploads = st.file_uploader(
        "Test saves (.db)",
        type=["db"],
        accept_multiple_files=True,
        key="save_validation_test_upload",
    )
    train_manual = st.text_area(
        "Train save paths (one per line)",
        key="save_validation_train_paths",
    )
    test_manual = st.text_area(
        "Test save paths (one per line)",
        key="save_validation_test_paths",
    )
    run_validation = st.button(
        "Run holdout validation",
        type="secondary",
        key="save_validation_run",
    )
    if run_validation:
        train_paths = _resolve_save_paths(train_uploads, train_manual)
        test_paths = _resolve_save_paths(test_uploads, test_manual)
        if not train_paths:
            st.warning("Provide at least one train save.")
        elif not test_paths:
            st.warning("Provide at least one test save.")
        else:
            try:
                with st.spinner("Running holdout validation..."):
                    validation = run_holdout_validation(
                        [str(path) for path in train_paths],
                        [str(path) for path in test_paths],
                        company_id=company_id if company_id >= 0 else None,
                    )
            except ValueError as exc:
                st.error(str(exc))
            except Exception as exc:  # pragma: no cover
                st.error(f"Holdout validation failed: {exc}")
            else:
                st.markdown(
                    f"**Train data:** {', '.join(f'`{name}`' for name in validation.train_saves)}  \n"
                    f"**Test data:** {', '.join(f'`{name}`' for name in validation.test_saves)}  \n"
                    f"**Train correction segments:** {validation.correction_segments}  \n"
                    f"**Formula fallback rows:** {validation.fallback_count}"
                )
                st.markdown("#### Metric comparison (test holdout)")
                if validation.metric_comparison.empty:
                    st.write("No metrics evaluated.")
                else:
                    st.dataframe(
                        validation.metric_comparison,
                        use_container_width=True,
                        hide_index=True,
                    )
                col_worse, col_better = st.columns(2)
                with col_worse:
                    st.markdown("**Worst regressions**")
                    if validation.worst_regressions.empty:
                        st.write("None")
                    else:
                        st.dataframe(
                            validation.worst_regressions.head(10),
                            use_container_width=True,
                            hide_index=True,
                        )
                with col_better:
                    st.markdown("**Best improvements**")
                    if validation.best_improvements.empty:
                        st.write("None")
                    else:
                        st.dataframe(
                            validation.best_improvements.head(10),
                            use_container_width=True,
                            hide_index=True,
                        )
                st.download_button(
                    "Download validation metric comparison CSV",
                    data=validation.metric_comparison.to_csv(index=False),
                    file_name="validation_metric_comparison.csv",
                    mime="text/csv",
                    key="download_validation_metrics",
                )

    st.markdown("---")
    st.markdown("### Calibration policy")
    st.caption(
        "Use holdout validation results to gate save calibration per metric. "
        "Calibration is enabled only where validation status is improved."
    )
    from gearcity_optimizer.prediction.calibration_policy import (
        build_calibration_policy,
        default_calibration_policy_dir,
        default_validation_dir,
        export_calibration_policy,
        load_calibration_policy,
    )

    policy_validation_dir = st.text_input(
        "Validation output directory",
        value=str(default_validation_dir()),
        key="calibration_policy_validation_dir",
    )
    policy_output_dir = st.text_input(
        "Policy export directory (optional)",
        value=str(default_calibration_policy_dir()),
        key="calibration_policy_output_dir",
    )
    build_policy = st.button(
        "Build calibration policy",
        type="secondary",
        key="calibration_policy_build",
    )
    if build_policy:
        try:
            validation_path = Path(policy_validation_dir)
            if not validation_path.is_dir():
                st.warning(f"Validation directory not found: {validation_path}")
            else:
                policy = build_calibration_policy(validation_path)
                export_calibration_policy(policy, policy_output_dir)
                st.success(f"Calibration policy built from `{validation_path}`.")
                st.session_state["calibration_policy"] = policy
        except Exception as exc:  # pragma: no cover
            st.error(f"Failed to build calibration policy: {exc}")

    policy = st.session_state.get("calibration_policy")
    if policy is None:
        policy_json = Path(policy_output_dir) / "calibration_policy.json"
        if policy_json.is_file():
            try:
                policy = load_calibration_policy(policy_json)
                st.session_state["calibration_policy"] = policy
            except Exception:
                policy = None
    if policy is None:
        validation_path = Path(policy_validation_dir)
        metric_csv = validation_path / "validation_metric_comparison.csv"
        if metric_csv.is_file():
            try:
                policy = build_calibration_policy(validation_path)
                st.session_state["calibration_policy"] = policy
            except Exception:
                policy = None

    if policy is None:
        st.info(
            "Run holdout validation or point to a directory with "
            "`validation_metric_comparison.csv` to review the calibration policy."
        )
    else:
        enabled_rows = [row for row in policy.metric_rows if row.calibration_enabled]
        disabled_rows = [row for row in policy.metric_rows if not row.calibration_enabled]
        st.markdown(
            f"**Policy mode:** `{policy.mode.value}`  \n"
            f"**Validation source:** `{policy.validation_dir or policy_validation_dir}`  \n"
            f"**Calibration enabled:** {len(enabled_rows)} metrics  \n"
            f"**Formula-only (safer):** {len(disabled_rows)} metrics"
        )
        col_enabled, col_disabled = st.columns(2)
        enabled_df = pd.DataFrame(
            [
                {
                    "Kind": row.kind,
                    "Metric": row.metric,
                    "Status": row.validation_status,
                    "Reason": row.reason,
                    "Samples": row.sample_count,
                    "Improvement %": row.improvement_pct,
                }
                for row in enabled_rows
            ]
        )
        disabled_df = pd.DataFrame(
            [
                {
                    "Kind": row.kind,
                    "Metric": row.metric,
                    "Status": row.validation_status,
                    "Reason": row.reason,
                    "Samples": row.sample_count,
                    "Improvement %": row.improvement_pct,
                }
                for row in disabled_rows
            ]
        )
        with col_enabled:
            st.markdown("**Metrics with calibration enabled**")
            if enabled_df.empty:
                st.write("None")
            else:
                st.dataframe(enabled_df, use_container_width=True, hide_index=True)
        with col_disabled:
            st.markdown("**Metrics where formula-only is safer**")
            if disabled_df.empty:
                st.write("None")
            else:
                st.dataframe(disabled_df, use_container_width=True, hide_index=True)
        if policy.group_rows:
            st.markdown("**Group-level rules**")
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Kind": row.kind,
                            "Metric": row.metric,
                            "Year band": row.year_band,
                            "Layout": row.layout,
                            "Fuel": row.fuel_type,
                            "Gearbox type": row.gearbox_type,
                            "Status": row.validation_status,
                            "Enabled": row.calibration_enabled,
                            "Samples": row.sample_count,
                            "Improvement %": row.improvement_pct,
                        }
                        for row in policy.group_rows
                    ]
                ),
                use_container_width=True,
                hide_index=True,
            )
