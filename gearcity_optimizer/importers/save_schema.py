"""Inspect GearCity SQLite save file structure without assuming a fixed schema."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SaveColumnInfo:
    """One column in a save table."""

    name: str
    declared_type: str
    not_null: bool
    primary_key: bool


@dataclass(frozen=True)
class SaveTableInfo:
    """Metadata and sample rows for one save table."""

    name: str
    columns: tuple[SaveColumnInfo, ...]
    row_count: int
    sample_rows: tuple[dict[str, Any], ...]
    read_error: str | None = None


@dataclass(frozen=True)
class SaveSchemaReport:
    """Full schema inspection result for one save file."""

    path: Path
    tables: tuple[SaveTableInfo, ...]
    missing_expected_tables: tuple[str, ...]
    read_errors: tuple[str, ...]


KNOWN_CALIBRATION_TABLES = (
    "GameInfo",
    "LayoutComponents",
    "EngineInfo",
    "GearboxInfo",
)


def _open_readonly(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _safe_cell(value: object) -> object:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<{len(value)} bytes>"
    if value is None:
        return None
    return value


def _sample_rows(
    conn: sqlite3.Connection,
    table: str,
    *,
    limit: int = 3,
) -> tuple[dict[str, Any], ...]:
    try:
        cursor = conn.execute(f'SELECT * FROM "{table}" LIMIT ?', (limit,))
    except sqlite3.Error:
        return ()
    rows: list[dict[str, Any]] = []
    for row in cursor.fetchall():
        rows.append({key: _safe_cell(row[key]) for key in row.keys()})
    return tuple(rows)


def _table_row_count(conn: sqlite3.Connection, table: str) -> int | None:
    try:
        row = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    return int(row[0])


def inspect_save_schema(
    path: str | Path,
    *,
    sample_limit: int = 3,
) -> SaveSchemaReport:
    """List tables, columns, types, row counts, and sample rows from a save database."""
    db_path = Path(path)
    if not db_path.is_file():
        raise FileNotFoundError(f"Save game not found: {db_path}")

    read_errors: list[str] = []
    tables: list[SaveTableInfo] = []

    try:
        conn = _open_readonly(db_path)
    except sqlite3.Error as exc:
        raise ValueError(f"Could not open save database: {exc}") from exc

    try:
        try:
            table_names = [
                str(row[0])
                for row in conn.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                    "ORDER BY name"
                )
            ]
        except sqlite3.Error as exc:
            read_errors.append(f"Could not list tables: {exc}")
            table_names = []

        for table in table_names:
            try:
                column_rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
            except sqlite3.Error as exc:
                tables.append(
                    SaveTableInfo(
                        name=table,
                        columns=(),
                        row_count=0,
                        sample_rows=(),
                        read_error=str(exc),
                    )
                )
                read_errors.append(f"{table}: {exc}")
                continue

            columns = tuple(
                SaveColumnInfo(
                    name=str(row[1]),
                    declared_type=str(row[2] or ""),
                    not_null=bool(row[3]),
                    primary_key=bool(row[5]),
                )
                for row in column_rows
            )
            row_count = _table_row_count(conn, table)
            if row_count is None:
                read_errors.append(f"{table}: could not count rows")
                row_count = 0

            sample = _sample_rows(conn, table, limit=sample_limit)
            tables.append(
                SaveTableInfo(
                    name=table,
                    columns=columns,
                    row_count=row_count,
                    sample_rows=sample,
                )
            )
    finally:
        conn.close()

    present = {table.name for table in tables}
    missing = tuple(name for name in KNOWN_CALIBRATION_TABLES if name not in present)

    return SaveSchemaReport(
        path=db_path,
        tables=tuple(tables),
        missing_expected_tables=missing,
        read_errors=tuple(read_errors),
    )


def format_save_schema_report(report: SaveSchemaReport) -> str:
    """Render a human-readable schema inspection report."""
    lines: list[str] = []
    lines.append(f"Save schema: {report.path.name}")
    lines.append(f"Path: {report.path}")
    lines.append(f"Tables: {len(report.tables)}")
    if report.missing_expected_tables:
        lines.append(
            "Missing optional calibration tables: "
            + ", ".join(report.missing_expected_tables)
        )
    if report.read_errors:
        lines.append("Read warnings:")
        for error in report.read_errors:
            lines.append(f"  - {error}")
    lines.append("")

    for table in report.tables:
        lines.append(f"Table: {table.name} ({table.row_count} rows)")
        if table.read_error:
            lines.append(f"  ERROR: {table.read_error}")
            lines.append("")
            continue
        if not table.columns:
            lines.append("  (no columns)")
        else:
            for column in table.columns:
                flags: list[str] = []
                if column.primary_key:
                    flags.append("PK")
                if column.not_null:
                    flags.append("NOT NULL")
                flag_text = f" [{', '.join(flags)}]" if flags else ""
                type_text = column.declared_type or "?"
                lines.append(f"  - {column.name}: {type_text}{flag_text}")
        if table.sample_rows:
            lines.append("  Sample rows:")
            for index, row in enumerate(table.sample_rows, start=1):
                preview = ", ".join(f"{key}={value!r}" for key, value in list(row.items())[:8])
                if len(row) > 8:
                    preview += ", ..."
                lines.append(f"    {index}. {preview}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
