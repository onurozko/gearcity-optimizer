"""Parse cached GearCity Wiki pages into structured JSON."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd
from bs4 import BeautifulSoup

from gearcity_optimizer.importers.wiki_downloader import project_root_from_module
from gearcity_optimizer.core.models import _parse_bool

FORMULA_KEYWORDS = (
    "=",
    "if",
    "else",
    "Rating_",
    "_Rating",
    "Unit_Costs",
    "Design_Costs",
    "Slider_",
    "Selected_",
    "SubComponent_",
    "Vehicle Type",
    "Buyer Rating",
    "Current Buyer Rating",
    "penalty",
    "Penalty",
    "Price Gouging",
    "Quality to Price",
    "Max_Torque_Support",
    "Comfort_Rating",
    "Performance_Rating",
    "Reliability_Rating",
    "Overall_Rating",
)

WIKI_METADATA_JSON_FILES = frozenset(
    {
        "wiki_formula_index.json",
        "wiki_download_manifest.json",
        "vehicle_type_table_comparison.json",
    }
)

VEHICLE_TYPE_COLUMNS = (
    "vehicle_type",
    "performance",
    "drivability",
    "luxury",
    "safety",
    "fuel",
    "power",
    "cargo",
    "dependability",
    "wealth_demo",
    "military_fleet",
    "civilian_fleet",
)

VEHICLE_TYPE_HEADER_ALIASES = {
    "vehicle_type",
    "performance",
    "drivability",
    "luxury",
    "safety",
    "fuel",
    "power",
    "cargo",
    "dependability",
    "wealth_demo",
    "military_fleet",
    "civilian_fleet",
}

COLUMN_ALIASES = {
    "vehicle_type": "vehicle_type",
    "wealth_demo": "wealth_demo",
    "military_fleet": "military_fleet",
    "civilian_fleet": "civilian_fleet",
    "mil_fleet": "military_fleet",
    "civ_fleet": "civilian_fleet",
}

DOKUWIKI_HEADING_RE = re.compile(r"^(=+)\s*(.+?)\s*\1\s*$")
CODE_BLOCK_RE = re.compile(r"<code[^>]*>(.*?)</code>", re.DOTALL | re.IGNORECASE)
VARIABLE_DEF_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\s*=")


def is_wiki_page_json(path: Path) -> bool:
    """Return True if a JSON file is a parsed wiki page, not metadata."""
    name = path.name
    return (
        name.startswith("wiki_")
        and name.endswith(".json")
        and name not in WIKI_METADATA_JSON_FILES
    )


def is_formula_line(line: str) -> bool:
    """Return True if a line looks like wiki pseudo-code formula text."""
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith("<") and stripped.endswith(">"):
        return False
    lower = stripped.lower()
    return any(keyword.lower() in lower for keyword in FORMULA_KEYWORDS)


def _normalize_column_name(name: str) -> str:
    """Normalize a table column header to a canonical field name."""
    key = name.strip().lower()
    key = re.sub(r"[.\s]+", "_", key)
    key = key.strip("_")
    return COLUMN_ALIASES.get(key, key)


def _split_dokuwiki_cells(line: str, delimiter: str) -> list[str]:
    """Split a DokuWiki table row into stripped cells."""
    stripped = line.strip()
    if stripped.startswith(delimiter):
        stripped = stripped[len(delimiter) :]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    if stripped.endswith("^"):
        stripped = stripped[:-1]
    cells = [cell.strip() for cell in stripped.split(delimiter)]
    while cells and not cells[-1]:
        cells.pop()
    return cells


def parse_dokuwiki_tables(text: str) -> list[dict[str, Any]]:
    """
    Parse DokuWiki tables from raw export text.

    Header rows start with ``^``; data rows start with ``|``.
    """
    tables: list[dict[str, Any]] = []
    current_headers: list[str] | None = None
    current_rows: list[list[str]] = []

    def flush_table() -> None:
        nonlocal current_headers, current_rows
        if current_headers is not None:
            tables.append(
                {
                    "headers": current_headers,
                    "rows": current_rows,
                    "source": "dokuwiki_raw",
                }
            )
        current_headers = None
        current_rows = []

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            flush_table()
            continue

        if stripped.startswith("^") and stripped.endswith("^"):
            flush_table()
            current_headers = [
                cell for cell in _split_dokuwiki_cells(stripped, "^") if cell
            ]
            current_rows = []
            continue

        if stripped.startswith("|") and current_headers is not None:
            row = _split_dokuwiki_cells(stripped, "|")
            if row and not all(set(cell) <= {"-"} for cell in row if cell):
                current_rows.append(row)
            continue

        flush_table()

    flush_table()
    return tables


def extract_dokuwiki_sections(text: str) -> list[dict[str, Any]]:
    """Extract DokuWiki heading sections from raw text."""
    lines = text.splitlines()
    headings: list[tuple[int, int, str]] = []

    for index, line in enumerate(lines):
        match = DOKUWIKI_HEADING_RE.match(line.strip())
        if match:
            headings.append((index, len(match.group(1)), match.group(2).strip()))

    sections: list[dict[str, Any]] = []
    for idx, (start, level, title) in enumerate(headings):
        end = len(lines)
        for next_start, next_level, _ in headings[idx + 1 :]:
            if next_level >= level:
                end = next_start
                break
        body = "\n".join(lines[start + 1 : end]).strip()
        sections.append({"level": level, "title": title, "text": body})

    return sections


def _expand_code_blocks(text: str) -> str:
    """Inline ``<code>`` block contents for formula extraction."""

    def replacer(match: re.Match[str]) -> str:
        return match.group(1)

    return CODE_BLOCK_RE.sub(replacer, text)


def extract_formula_chunks(text: str) -> list[str]:
    """Extract lines that resemble formula pseudo-code."""
    expanded = _expand_code_blocks(text)
    chunks: list[str] = []
    for line in expanded.splitlines():
        cleaned = line.strip()
        if is_formula_line(cleaned):
            chunks.append(cleaned)
    return chunks


def extract_formula_sections_from_raw(text: str) -> dict[str, str]:
    """Group formula-like lines by DokuWiki section headings."""
    sections: dict[str, str] = {}

    for section in extract_dokuwiki_sections(text):
        body = _expand_code_blocks(section["text"])
        formula_lines = [
            line.strip()
            for line in body.splitlines()
            if is_formula_line(line.strip())
        ]
        if formula_lines:
            sections[section["title"]] = "\n".join(formula_lines)
        elif body.strip():
            non_empty = [line.strip() for line in body.splitlines() if line.strip()]
            code_like = [
                line
                for line in non_empty
                if "=" in line or line.startswith("if ") or line.startswith("else")
            ]
            if code_like:
                sections[section["title"]] = "\n".join(code_like[:30])

    return sections


def _dokuwiki_table_to_records(table: dict[str, Any]) -> list[dict[str, str]]:
    """Convert a DokuWiki table dict to row records."""
    headers = [_normalize_column_name(header) for header in table["headers"]]
    records: list[dict[str, str]] = []
    for row in table["rows"]:
        record: dict[str, str] = {}
        for index, header in enumerate(headers):
            if index < len(row):
                record[header] = row[index].strip()
        records.append(record)
    return records


def _is_vehicle_type_table(headers: list[str]) -> bool:
    """Return True if headers look like the vehicle type importance table."""
    normalized = {_normalize_column_name(header) for header in headers}
    required = {
        "vehicle_type",
        "performance",
        "drivability",
        "luxury",
        "safety",
        "fuel",
        "power",
        "cargo",
        "dependability",
    }
    return required.issubset(normalized)


def _table_to_records(table) -> list[dict[str, str]]:
    """Convert an HTML table to a list of row dicts."""
    rows = table.find_all("tr")
    if not rows:
        return []

    headers = [
        _normalize_column_name(cell.get_text(" ", strip=True))
        for cell in rows[0].find_all(["th", "td"])
    ]

    records: list[dict[str, str]] = []
    for row in rows[1:]:
        cells = row.find_all(["td", "th"])
        if not cells:
            continue
        record = {
            headers[i]: cells[i].get_text(" ", strip=True)
            for i in range(min(len(headers), len(cells)))
        }
        records.append(record)
    return records


def _extract_html_sections(soup: BeautifulSoup) -> list[dict[str, Any]]:
    """Extract sections from HTML headings."""
    sections: list[dict[str, Any]] = []
    headings = soup.find_all(re.compile(r"^h[1-6]$"))

    for index, heading in enumerate(headings):
        level = int(heading.name[1])
        title = heading.get_text(" ", strip=True)
        if not title:
            continue

        body_parts: list[str] = []
        for sibling in heading.next_siblings:
            if getattr(sibling, "name", None) in {f"h{i}" for i in range(1, 7)}:
                sibling_level = int(sibling.name[1])
                if sibling_level <= level:
                    break
            if hasattr(sibling, "get_text"):
                text = sibling.get_text("\n", strip=True)
                if text:
                    body_parts.append(text)
            elif isinstance(sibling, str) and sibling.strip():
                body_parts.append(sibling.strip())

        sections.append(
            {
                "level": level,
                "title": title,
                "text": "\n".join(body_parts),
            }
        )

    return sections


def extract_formula_sections_from_html(html: str) -> dict[str, str]:
    """Group formula-like lines by HTML section headings."""
    soup = BeautifulSoup(html, "html.parser")
    sections: dict[str, str] = {}

    for section in _extract_html_sections(soup):
        body = _expand_code_blocks(section["text"])
        formula_lines = [
            line.strip()
            for line in body.splitlines()
            if is_formula_line(line.strip())
        ]
        if formula_lines:
            sections[section["title"]] = "\n".join(formula_lines)

    return sections


def _extract_headings_from_sections(
    sections: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Convert section dicts to heading metadata."""
    return [
        {"level": str(section["level"]), "text": section["title"]}
        for section in sections
    ]


def _extract_variable_definitions(text: str) -> list[str]:
    """Extract lines that look like variable definitions."""
    expanded = _expand_code_blocks(text)
    return [
        line.strip()
        for line in expanded.splitlines()
        if VARIABLE_DEF_RE.match(line.strip())
    ]


def parse_html_content(html: str, source_type: str) -> dict[str, Any]:
    """Parse wiki HTML into structured fields."""
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    sections = _extract_html_sections(soup)
    headings = _extract_headings_from_sections(sections)
    html_tables = [_table_to_records(table) for table in soup.find_all("table")]
    text = soup.get_text("\n", strip=True)

    return {
        "title": title,
        "source_type": source_type,
        "headings": headings,
        "sections": sections,
        "tables": html_tables,
        "html_tables": html_tables,
        "dokuwiki_tables": [],
        "variable_definitions": _extract_variable_definitions(text),
        "formula_chunks": extract_formula_chunks(text),
        "formula_sections": extract_formula_sections_from_html(html),
        "text": text,
    }


def parse_raw_content(raw: str) -> dict[str, Any]:
    """Parse DokuWiki raw export text."""
    title = ""
    for line in raw.splitlines()[:15]:
        match = DOKUWIKI_HEADING_RE.match(line.strip())
        if match and len(match.group(1)) >= 5:
            title = match.group(2).strip()
            break

    dokuwiki_tables = parse_dokuwiki_tables(raw)
    sections = extract_dokuwiki_sections(raw)
    headings = _extract_headings_from_sections(sections)
    record_tables = [_dokuwiki_table_to_records(table) for table in dokuwiki_tables]

    return {
        "title": title,
        "source_type": "raw",
        "headings": headings,
        "sections": sections,
        "tables": record_tables,
        "html_tables": [],
        "dokuwiki_tables": dokuwiki_tables,
        "variable_definitions": _extract_variable_definitions(raw),
        "formula_chunks": extract_formula_chunks(raw),
        "formula_sections": extract_formula_sections_from_raw(raw),
        "text": raw,
    }


def resolve_page_source(
    name: str,
    raw_dir: Path,
    text_dir: Path,
    html_dir: Path,
) -> tuple[str, str] | None:
    """Resolve the best available cached source for a wiki page."""
    raw_path = raw_dir / f"{name}.txt"
    text_path = text_dir / f"{name}.html"
    html_path = html_dir / f"{name}.html"

    if raw_path.exists():
        return "raw", raw_path.read_text(encoding="utf-8")
    if text_path.exists():
        return "xhtmlbody", text_path.read_text(encoding="utf-8")
    if html_path.exists():
        return "html", html_path.read_text(encoding="utf-8")
    return None


def parse_wiki_page(name: str, content: str, source_type: str) -> dict[str, Any]:
    """Parse wiki content based on source type."""
    if source_type == "raw":
        parsed = parse_raw_content(content)
    else:
        parsed = parse_html_content(content, source_type)
    parsed["name"] = name
    return parsed


def build_formula_index(parsed_pages: dict[str, dict[str, Any]]) -> dict[str, dict[str, str]]:
    """Build formula index from parsed wiki pages."""
    formula_pages = (
        "chassis_game_mechanics",
        "engine_game_mechanics",
        "gearbox_game_mechanics",
        "dynamic_reports",
    )
    index: dict[str, dict[str, str]] = {}

    for page_name in formula_pages:
        if page_name not in parsed_pages:
            continue
        page = parsed_pages[page_name]
        sections = page.get("formula_sections", {})
        if sections:
            index[page_name] = sections

    return index


def _parse_float(value: str) -> float:
    return float(str(value).strip())


def _parse_vehicle_type_row(row: dict[str, str]) -> dict[str, Any] | None:
    """Parse one vehicle type table row into a normalized dict."""
    normalized = {_normalize_column_name(k): v for k, v in row.items()}
    vehicle_name = normalized.get("vehicle_type")
    if not vehicle_name:
        return None

    try:
        return {
            "vehicle_type": vehicle_name.strip(),
            "performance": _parse_float(normalized["performance"]),
            "drivability": _parse_float(normalized["drivability"]),
            "luxury": _parse_float(normalized["luxury"]),
            "safety": _parse_float(normalized["safety"]),
            "fuel": _parse_float(normalized["fuel"]),
            "power": _parse_float(normalized["power"]),
            "cargo": _parse_float(normalized["cargo"]),
            "dependability": _parse_float(normalized["dependability"]),
            "wealth_demo": int(float(normalized["wealth_demo"])),
            "military_fleet": _parse_bool(normalized.get("military_fleet", False)),
            "civilian_fleet": _parse_bool(normalized.get("civilian_fleet", False)),
        }
    except (KeyError, ValueError):
        return None


def extract_vehicle_type_importance(
    parsed_page: dict[str, Any],
) -> list[dict[str, Any]]:
    """Extract vehicle type importance rows from parsed wiki tables."""
    rows: list[dict[str, Any]] = []

    for table in parsed_page.get("dokuwiki_tables", []):
        if not _is_vehicle_type_table(table.get("headers", [])):
            continue
        for record in _dokuwiki_table_to_records(table):
            parsed_row = _parse_vehicle_type_row(record)
            if parsed_row:
                rows.append(parsed_row)

    for table in parsed_page.get("tables", []):
        if not table:
            continue
        sample_keys = list(table[0].keys()) if table else []
        if not _is_vehicle_type_table(sample_keys):
            continue
        for record in table:
            parsed_row = _parse_vehicle_type_row(record)
            if parsed_row:
                rows.append(parsed_row)

    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        deduped[row["vehicle_type"]] = row
    return list(deduped.values())


def _serialize_value(value: Any) -> Any:
    """Convert pandas/numpy values to JSON-serializable Python types."""
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, (int, float, str)):
        return value
    return str(value)


def compare_vehicle_type_tables(
    existing_csv: str | Path,
    generated_csv: str | Path,
) -> dict[str, Any]:
    """Compare existing and wiki-generated vehicle type CSV files."""
    existing = pd.read_csv(existing_csv)
    generated = pd.read_csv(generated_csv)

    existing_types = set(existing["vehicle_type"].astype(str))
    generated_types = set(generated["vehicle_type"].astype(str))

    missing = sorted(existing_types - generated_types)
    extra = sorted(generated_types - existing_types)

    changed: list[dict[str, Any]] = []
    common = existing_types & generated_types
    compare_cols = [col for col in VEHICLE_TYPE_COLUMNS if col != "vehicle_type"]

    existing_indexed = existing.set_index("vehicle_type")
    generated_indexed = generated.set_index("vehicle_type")

    for vehicle_type in sorted(common):
        for column in compare_cols:
            old_val = existing_indexed.loc[vehicle_type, column]
            new_val = generated_indexed.loc[vehicle_type, column]
            if column in {"military_fleet", "civilian_fleet"}:
                if _parse_bool(old_val) != _parse_bool(new_val):
                    changed.append(
                        {
                            "vehicle_type": vehicle_type,
                            "column": column,
                            "existing": _serialize_value(old_val),
                            "generated": _serialize_value(new_val),
                        }
                    )
                continue

            try:
                if float(old_val) != float(new_val):
                    changed.append(
                        {
                            "vehicle_type": vehicle_type,
                            "column": column,
                            "existing": _serialize_value(old_val),
                            "generated": _serialize_value(new_val),
                        }
                    )
            except (TypeError, ValueError):
                if str(old_val) != str(new_val):
                    changed.append(
                        {
                            "vehicle_type": vehicle_type,
                            "column": column,
                            "existing": _serialize_value(old_val),
                            "generated": _serialize_value(new_val),
                        }
                    )

    return {
        "match": bool(not missing and not extra and not changed),
        "missing_vehicle_types": missing,
        "extra_vehicle_types": extra,
        "changed_values": changed,
        "missing_count": len(missing),
        "extra_count": len(extra),
        "changed_count": len(changed),
    }


def import_wiki_pages(
    urls_file: str | Path = "sources/wiki_urls.json",
    raw_dir: str | Path = "sources/wiki_raw",
    text_dir: str | Path = "sources/wiki_text",
    html_dir: str | Path = "sources/wiki_html",
    output_dir: str | Path = "generated/raw_parsed",
    normalized_dir: str | Path = "generated/normalized",
    existing_vehicle_types_csv: str | Path = "data/vehicle_types.csv",
    debug: bool = False,
) -> dict[str, Any]:
    """Parse all cached wiki pages and write structured JSON outputs."""
    root = project_root_from_module()
    urls_path = Path(urls_file)
    if not urls_path.is_absolute():
        urls_path = root / urls_path

    raw_path = Path(raw_dir)
    text_path = Path(text_dir)
    html_path = Path(html_dir)
    output_path = Path(output_dir)
    normalized_path = Path(normalized_dir)
    if not raw_path.is_absolute():
        raw_path = root / raw_path
    if not text_path.is_absolute():
        text_path = root / text_path
    if not html_path.is_absolute():
        html_path = root / html_path
    if not output_path.is_absolute():
        output_path = root / output_path
    if not normalized_path.is_absolute():
        normalized_path = root / normalized_path

    for directory in (raw_path, text_path, html_path, output_path, normalized_path):
        directory.mkdir(parents=True, exist_ok=True)

    with urls_path.open(encoding="utf-8") as handle:
        entries = json.load(handle)

    parsed_pages: dict[str, dict[str, Any]] = {}
    summary: dict[str, Any] = {
        "parsed": [],
        "missing_sources": [],
        "vehicle_types_from_wiki": None,
        "vehicle_type_comparison": None,
        "vehicle_type_comparison_path": None,
        "debug": debug,
    }

    for entry in entries:
        name = entry["name"]
        source = resolve_page_source(name, raw_path, text_path, html_path)
        if source is None:
            summary["missing_sources"].append(name)
            continue

        source_type, content = source
        parsed = parse_wiki_page(name, content, source_type)
        parsed_pages[name] = parsed

        out_file = output_path / f"wiki_{name}.json"
        out_file.write_text(json.dumps(parsed, indent=2), encoding="utf-8")

        page_summary = {
            "name": name,
            "source_type": source_type,
            "title": parsed.get("title", ""),
            "tables": len(parsed.get("tables", [])),
            "dokuwiki_tables": len(parsed.get("dokuwiki_tables", [])),
            "html_tables": len(parsed.get("html_tables", [])),
            "sections": len(parsed.get("sections", [])),
            "formula_chunks": len(parsed.get("formula_chunks", [])),
            "formula_sections": len(parsed.get("formula_sections", {})),
            "output": str(out_file),
        }
        summary["parsed"].append(page_summary)

        if debug:
            print(
                f"[debug] {name}: source={source_type}, "
                f"dokuwiki_tables={page_summary['dokuwiki_tables']}, "
                f"html_tables={page_summary['html_tables']}, "
                f"sections={page_summary['sections']}, "
                f"formula_sections={page_summary['formula_sections']}"
            )

    formula_index = build_formula_index(parsed_pages)
    formula_index_file = output_path / "wiki_formula_index.json"
    formula_index_file.write_text(
        json.dumps(formula_index, indent=2),
        encoding="utf-8",
    )
    summary["formula_index_path"] = str(formula_index_file)
    summary["formula_index_counts"] = {
        page: len(sections) for page, sections in formula_index.items()
    }

    if "vehicle_type_importance" in parsed_pages:
        vehicle_rows = extract_vehicle_type_importance(
            parsed_pages["vehicle_type_importance"]
        )
        if vehicle_rows:
            wiki_csv = normalized_path / "vehicle_types_from_wiki.csv"
            df = pd.DataFrame(vehicle_rows)
            df = df[list(VEHICLE_TYPE_COLUMNS)]
            df.to_csv(wiki_csv, index=False)
            summary["vehicle_types_from_wiki"] = str(wiki_csv)
            summary["vehicle_types_row_count"] = len(df)

            existing_csv = Path(existing_vehicle_types_csv)
            if not existing_csv.is_absolute():
                existing_csv = root / existing_csv
            if existing_csv.exists():
                comparison = compare_vehicle_type_tables(existing_csv, wiki_csv)
                summary["vehicle_type_comparison"] = comparison
                comparison_file = output_path / "vehicle_type_table_comparison.json"
                comparison_file.write_text(
                    json.dumps(comparison, indent=2),
                    encoding="utf-8",
                )
                summary["vehicle_type_comparison_path"] = str(comparison_file)

    if debug:
        print(
            f"[debug] vehicle_types_from_wiki written: "
            f"{summary.get('vehicle_types_from_wiki') is not None}"
        )
        print(f"[debug] formula_index sections: {summary.get('formula_index_counts')}")

    return summary
