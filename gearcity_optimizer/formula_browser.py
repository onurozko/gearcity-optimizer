"""Browse and search parsed GearCity wiki formula sections."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gearcity_optimizer.importers.wiki_downloader import project_root_from_module

FORMULA_INDEX_MISSING_MSG = """Formula index not found. This is normal for a fresh clone. Run:
python -m gearcity_optimizer.cli download-wiki
python -m gearcity_optimizer.cli import-wiki"""

GENERATED_FILES_MISSING_MSG = (
    "Generated files are missing. Recreate them with import-wiki."
)

WIKI_SOURCES_MISSING_MSG = """Wiki cache and generated parser outputs are not present yet. This is normal for a fresh clone. Run:

python -m gearcity_optimizer.cli download-wiki
python -m gearcity_optimizer.cli import-wiki

to enable formula browsing and generated wiki data."""


def wiki_sources_missing(status: dict[str, object]) -> bool:
    """Return True when wiki cache or generated parser outputs are absent."""
    return not status.get("formula_index_exists") or (
        status.get("wiki_html_count", 0) == 0 and status.get("wiki_raw_count", 0) == 0
    )


def wiki_sources_missing_message() -> str:
    """Return the fresh-clone guidance message for missing wiki/generated files."""
    return WIKI_SOURCES_MISSING_MSG


class FormulaIndexError(Exception):
    """Raised when the formula index cannot be loaded or queried."""


def _resolve_path(path: str | Path) -> Path:
    """Resolve a path relative to the project root."""
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = project_root_from_module() / resolved
    return resolved


def load_formula_index(
    path: str | Path = "generated/raw_parsed/wiki_formula_index.json",
) -> dict[str, dict[str, str]]:
    """Load the wiki formula index JSON file."""
    index_path = _resolve_path(path)
    if not index_path.exists():
        raise FormulaIndexError(FORMULA_INDEX_MISSING_MSG)
    with index_path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return data


def list_formula_pages(formula_index: dict[str, dict[str, str]]) -> list[str]:
    """Return sorted page names in the formula index."""
    return sorted(formula_index.keys())


def list_formula_sections(
    formula_index: dict[str, dict[str, str]],
    page_name: str,
) -> list[str]:
    """Return sorted section names for a wiki page."""
    page = _get_page(formula_index, page_name)
    return sorted(page.keys())


def _get_page(
    formula_index: dict[str, dict[str, str]],
    page_name: str,
) -> dict[str, str]:
    """Return a page dict or raise with available pages."""
    if page_name not in formula_index:
        available = ", ".join(list_formula_pages(formula_index))
        raise FormulaIndexError(
            f"Unknown page {page_name!r}. Available pages: {available}"
        )
    return formula_index[page_name]


def _normalize_text(text: str, case_sensitive: bool) -> str:
    return text if case_sensitive else text.lower()


def _find_section_name(page: dict[str, str], section_name: str) -> str | None:
    """Find an exact or case-insensitive section name match."""
    if section_name in page:
        return section_name
    lowered = section_name.lower()
    for name in page:
        if name.lower() == lowered:
            return name
    for name in page:
        if lowered in name.lower() or name.lower() in lowered:
            return name
    return None


def search_formulas(
    formula_index: dict[str, dict[str, str]],
    query: str,
    page_name: str | None = None,
    case_sensitive: bool = False,
) -> list[dict[str, Any]]:
    """Search formula sections for a query string."""
    if not query.strip():
        return []

    pages = [page_name] if page_name else list_formula_pages(formula_index)
    if page_name:
        _get_page(formula_index, page_name)

    needle = _normalize_text(query, case_sensitive)
    results: list[dict[str, Any]] = []

    for page in pages:
        sections = formula_index[page]
        for section_name, text in sections.items():
            haystack_name = _normalize_text(section_name, case_sensitive)
            haystack_text = _normalize_text(text, case_sensitive)
            if needle not in haystack_name and needle not in haystack_text:
                continue

            matching_lines = [
                line.strip()
                for line in text.splitlines()
                if needle in _normalize_text(line, case_sensitive)
            ]
            if not matching_lines and needle in haystack_name:
                matching_lines = [line.strip() for line in text.splitlines() if line.strip()][:3]

            results.append(
                {
                    "page": page,
                    "section": section_name,
                    "matching_lines": matching_lines,
                    "text": text,
                }
            )

    return results


def get_formula_section(
    formula_index: dict[str, dict[str, str]],
    page_name: str,
    section_name: str,
) -> str:
    """Return formula text for a page section with fuzzy name matching."""
    page = _get_page(formula_index, page_name)
    resolved = _find_section_name(page, section_name)
    if resolved is None:
        available = ", ".join(list_formula_sections(formula_index, page_name))
        raise FormulaIndexError(
            f"Unknown section {section_name!r} on page {page_name!r}. "
            f"Available sections: {available}"
        )
    return page[resolved]


def export_formula_markdown(
    formula_index: dict[str, dict[str, str]],
    output_path: str | Path = "generated/raw_parsed/wiki_formula_index.md",
) -> Path:
    """Export the formula index to a Markdown file."""
    out = _resolve_path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = ["# GearCity Wiki Formula Index", ""]
    for page_name in list_formula_pages(formula_index):
        lines.append(f"## {page_name}")
        lines.append("")
        for section_name in list_formula_sections(formula_index, page_name):
            lines.append(f"### {section_name}")
            lines.append("")
            lines.append("```")
            lines.append(formula_index[page_name][section_name].strip())
            lines.append("```")
            lines.append("")

    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def excerpt_text(text: str, max_lines: int = 5) -> str:
    """Return a shortened excerpt of formula text."""
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) <= max_lines:
        return "\n".join(lines)
    return "\n".join(lines[:max_lines] + ["..."])
