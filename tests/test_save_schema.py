"""Tests for GearCity save schema inspection."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from gearcity_optimizer.importers.save_schema import (
    KNOWN_CALIBRATION_TABLES,
    format_save_schema_report,
    inspect_save_schema,
)


def test_inspect_save_schema_lists_tables_and_columns(sample_save_db: Path):
    report = inspect_save_schema(sample_save_db)

    assert report.path == sample_save_db
    table_names = {table.name for table in report.tables}
    assert "EngineInfo" in table_names
    assert "GearboxInfo" in table_names
    assert report.missing_expected_tables == ()

    engine_table = next(table for table in report.tables if table.name == "EngineInfo")
    column_names = {column.name for column in engine_table.columns}
    assert "Engine_ID" in column_names
    assert "Layout" in column_names
    assert engine_table.row_count == 1
    assert len(engine_table.sample_rows) == 1
    assert engine_table.sample_rows[0]["Engine_ID"] == 707


def test_inspect_save_schema_missing_tables_do_not_crash(tmp_path: Path):
    db_path = tmp_path / "partial.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("CREATE TABLE OnlyEngines (Engine_ID INTEGER PRIMARY KEY, Name TEXT)")
        conn.execute("INSERT INTO OnlyEngines VALUES (1, 'Test')")
        conn.commit()
    finally:
        conn.close()

    report = inspect_save_schema(db_path)

    assert len(report.tables) == 1
    assert report.tables[0].name == "OnlyEngines"
    assert report.tables[0].row_count == 1
    missing = set(report.missing_expected_tables)
    assert "EngineInfo" in missing
    assert "GearboxInfo" in missing
    assert "GameInfo" in missing


def test_inspect_save_schema_missing_file_raises():
    with pytest.raises(FileNotFoundError, match="Save game not found"):
        inspect_save_schema("/nonexistent/save.db")


def test_format_save_schema_report_includes_table_summary(sample_save_db: Path):
    report = inspect_save_schema(sample_save_db)
    text = format_save_schema_report(report)

    assert "Save schema:" in text
    assert "Table: EngineInfo" in text
    assert "Engine_ID" in text
    assert "Sample rows:" in text


def test_known_calibration_tables_cover_core_entities():
    assert "EngineInfo" in KNOWN_CALIBRATION_TABLES
    assert "GearboxInfo" in KNOWN_CALIBRATION_TABLES
