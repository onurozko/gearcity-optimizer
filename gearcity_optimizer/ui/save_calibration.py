"""Streamlit tab for comparing wiki formulas against GearCity save designs."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from gearcity_optimizer.reports.save_calibration import (
    calibrate_save_game,
    format_engine_calibration_lines,
    format_gearbox_calibration_lines,
    report_to_csv_rows,
)

TAB_CAPTION = (
    "Upload a GearCity save database (.db) from SaveGames to compare in-game "
    "EngineInfo and GearboxInfo stats against our wiki formula predictions."
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


def _resolve_save_path(uploaded_file, manual_path: str) -> Path | None:
    manual = manual_path.strip().strip('"')
    if manual:
        path = Path(manual)
        if path.is_file():
            return path
        st.error(f"Save file not found: {path}")
        return None
    if uploaded_file is not None:
        suffix = Path(uploaded_file.name).suffix or ".db"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            handle.write(uploaded_file.getbuffer())
            return Path(handle.name)
    return None


def render_save_calibration_tab() -> None:
    """Render save upload, filters, and formula comparison output."""
    st.subheader("Save Calibration")
    st.caption(TAB_CAPTION)

    uploaded = st.file_uploader(
        "GearCity save (.db)",
        type=["db"],
        key="save_calibration_upload",
    )
    manual_path = st.text_input(
        "Or enter a local path to a save file",
        placeholder=r"D:\Games\GearCity\SaveGames\my-save.db",
        key="save_calibration_path",
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        company_id = st.number_input("Company ID (-1 for all)", min_value=-1, value=0, step=1)
    with col2:
        limit = st.number_input("Max engines/gearboxes each", min_value=1, value=10, step=1)
    with col3:
        kind = st.selectbox("Compare", options=["all", "engine", "gearbox"], index=0)

    compare_all = st.checkbox("Compare all designs (ignore limit)", value=False)
    run = st.button("Run calibration", type="primary", key="save_calibration_run")

    if not run:
        st.info("Upload a save or enter a path, then click Run calibration.")
        return

    save_path = _resolve_save_path(uploaded, manual_path)
    if save_path is None:
        st.warning("Provide a save file before running calibration.")
        return

    try:
        report = calibrate_save_game(
            str(save_path),
            company_id=company_id if company_id >= 0 else None,
            engine_limit=None if compare_all else int(limit),
            gearbox_limit=None if compare_all else int(limit),
        )
    except FileNotFoundError as exc:
        st.error(str(exc))
        return
    except Exception as exc:  # pragma: no cover - surfaced in UI for bad SQLite files
        st.error(f"Could not read save file: {exc}")
        return

    year = report.snapshot.current_year
    st.markdown(
        f"**Save:** `{report.snapshot.path.name}`  \n"
        f"**Current year:** {year if year is not None else 'unknown'}  \n"
        f"**Loaded:** {len(report.snapshot.engines)} engines, "
        f"{len(report.snapshot.gearboxes)} gearboxes  \n"
        f"**Compared:** {len(report.engines)} engines, {len(report.gearboxes)} gearboxes"
    )

    if report.engine_summary:
        st.markdown("#### Engine mean errors")
        engine_summary_rows = [
            {"Metric": key, "Value": round(value, 2)}
            for key, value in sorted(report.engine_summary.items())
        ]
        st.dataframe(engine_summary_rows, use_container_width=True, hide_index=True)

    if report.gearbox_summary:
        st.markdown("#### Gearbox mean errors")
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
        st.markdown("#### Detailed comparisons")
        st.dataframe(filtered, use_container_width=True, hide_index=True)

        csv_rows = report_to_csv_rows(report)
        st.download_button(
            "Download CSV",
            data=pd.DataFrame(csv_rows).to_csv(index=False),
            file_name=f"{report.snapshot.path.stem}-calibration.csv",
            mime="text/csv",
        )

    if kind in {"engine", "all"} and report.engines:
        st.markdown("#### Engine notes")
        for item in report.engines:
            with st.expander(
                f"Engine {item.record.engine_id}: {item.record.name}",
                expanded=len(report.engines) <= 3,
            ):
                for line in format_engine_calibration_lines(item):
                    st.text(line)

    if kind in {"gearbox", "all"} and report.gearboxes:
        st.markdown("#### Gearbox notes")
        for item in report.gearboxes:
            with st.expander(
                f"Gearbox {item.record.gearbox_id}: {item.record.name}",
                expanded=len(report.gearboxes) <= 3,
            ):
                for line in format_gearbox_calibration_lines(item):
                    st.text(line)
