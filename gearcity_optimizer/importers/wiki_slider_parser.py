"""Parse GearCity Wiki slider variable tables from game mechanics pages."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

MECHANICS_PAGES = frozenset(
    {
        "engine_game_mechanics",
        "chassis_game_mechanics",
        "vehicle_game_mechanics",
        "gearbox_game_mechanics",
    }
)

PAGE_TO_SECTION = {
    "engine_game_mechanics": "engine",
    "chassis_game_mechanics": "chassis",
    "vehicle_game_mechanics": "vehicle",
    "gearbox_game_mechanics": "gearbox",
}

DEMOGRAPHIC_VARIABLES = frozenset(
    {
        "Slider_Demographics_Gender",
        "Slider_Demographics_Wealth",
        "Slider_Demographics_Age",
    }
)

DIMENSIONAL_VARIABLES = frozenset(
    {
        "Slider_Layout_Bore",
        "Slider_Layout_Stroke",
    }
)

UI_PATH_RE = re.compile(
    r"^Sliders?:\s*(.+?)\s*=>\s*(.+)$",
    re.IGNORECASE,
)
VARIABLE_RE = re.compile(r"\*\*(Slider[s]?_[A-Za-z0-9_]+)\s*\*\*", re.IGNORECASE)


@dataclass(frozen=True)
class SliderDefinition:
    """One wiki-backed slider or design control."""

    page: str
    formula_variable: str
    ui_label: str
    wiki_description: str
    section: str
    control_type: str
    min_value: float | None
    max_value: float | None
    default_value: float | None
    source_page: str
    source_section: str
    source_context: str
    confidence: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SliderDefinition:
        migrated = dict(data)
        if "wiki_description" not in migrated:
            migrated["wiki_description"] = migrated.pop("ui_path", migrated.get("notes", ""))
        if "source_page" not in migrated:
            migrated["source_page"] = migrated.pop("source_url", migrated.get("page", ""))
        if "source_context" not in migrated:
            migrated["source_context"] = migrated.get("wiki_description", "")
        for legacy_key in ("ui_path", "source_url", "notes", "internal_field"):
            migrated.pop(legacy_key, None)
        allowed = set(cls.__dataclass_fields__)
        return cls(**{key: value for key, value in migrated.items() if key in allowed})


def _normalize_variable(name: str) -> str:
    return re.sub(r"\s+", "", name.strip())


def _infer_section(page_name: str, wiki_description: str) -> str:
    lowered = wiki_description.lower()
    if "testing" in lowered:
        return "testing"
    if "demographics" in lowered:
        return "demographics"
    return PAGE_TO_SECTION.get(page_name, page_name)


def _classify_control(formula_variable: str, description: str) -> str:
    if formula_variable in DEMOGRAPHIC_VARIABLES:
        return "dropdown"
    if UI_PATH_RE.match(description.strip()):
        return "slider"
    if formula_variable.endswith("_Displacement") or "(" in description:
        return "derived"
    return "unknown"


def _parse_ui_path(description: str) -> tuple[str, str]:
    cleaned = description.strip()
    match = UI_PATH_RE.match(cleaned)
    if not match:
        return cleaned, cleaned
    group_path = match.group(1).strip()
    label = match.group(2).strip()
    return f"{group_path} => {label}", label


def _parse_slider_pairs_from_line(line: str) -> list[tuple[str, str]]:
    if not line.strip().startswith("|"):
        return []
    parts = [part.strip() for part in line.split("|")]
    parts = [part for part in parts if part]
    pairs: list[tuple[str, str]] = []
    index = 0
    while index + 1 < len(parts):
        variable_cell = parts[index]
        description_cell = parts[index + 1]
        variable_match = VARIABLE_RE.search(variable_cell)
        if variable_match:
            variable = _normalize_variable(variable_match.group(1))
            pairs.append((variable, description_cell.strip()))
        index += 2
    return pairs


def parse_sliders_from_wiki_text(
    text: str,
    *,
    page: str,
    source_page: str = "",
) -> list[SliderDefinition]:
    """Extract slider definitions from raw DokuWiki export text."""
    in_sliders = False
    sliders: list[SliderDefinition] = []
    seen: set[str] = set()
    page_name = source_page or page

    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"^={3,4}\s*Sliders\b", stripped, re.IGNORECASE):
            in_sliders = True
            continue
        if in_sliders and re.match(r"^={3,4}\s+\S", stripped):
            break
        if not in_sliders or not line.strip().startswith("|"):
            continue
        if line.strip().startswith("^"):
            continue

        for formula_variable, description in _parse_slider_pairs_from_line(line):
            if formula_variable in seen:
                continue
            seen.add(formula_variable)
            source_context, ui_label = _parse_ui_path(description)
            control_type = _classify_control(formula_variable, description)
            confidence = "confirmed" if control_type in {"slider", "dropdown"} else "inferred"
            sliders.append(
                SliderDefinition(
                    page=PAGE_TO_SECTION.get(page_name, page_name),
                    formula_variable=formula_variable,
                    ui_label=ui_label,
                    wiki_description=description,
                    section=_infer_section(page_name, source_context),
                    control_type=control_type,
                    min_value=(
                        1.0
                        if control_type == "slider"
                        and formula_variable not in DIMENSIONAL_VARIABLES
                        else None
                    ),
                    max_value=(
                        100.0
                        if control_type == "slider"
                        and formula_variable not in DIMENSIONAL_VARIABLES
                        else None
                    ),
                    default_value=None,
                    source_page=page_name,
                    source_section="Sliders",
                    source_context=source_context,
                    confidence=confidence,
                )
            )
    return sliders


def parse_sliders_from_parsed_page(
    parsed_page: dict[str, Any],
    *,
    page_name: str,
    source_page: str = "",
) -> list[SliderDefinition]:
    """Extract slider definitions from a parsed wiki page dict."""
    raw_text = parsed_page.get("raw_text") or parsed_page.get("text") or ""
    if not raw_text:
        sections = parsed_page.get("sections", [])
        raw_text = "\n".join(section.get("text", "") for section in sections)
    if raw_text.strip():
        return parse_sliders_from_wiki_text(
            raw_text,
            page=page_name,
            source_page=source_page or page_name,
        )

    sliders: list[SliderDefinition] = []
    for table in parsed_page.get("dokuwiki_tables", []):
        headers = [header.lower() for header in table.get("headers", [])]
        if "variable" not in headers:
            continue
        var_index = headers.index("variable")
        desc_index = headers.index("description") if "description" in headers else var_index + 1
        for row in table.get("rows", []):
            if var_index >= len(row):
                continue
            variable_match = VARIABLE_RE.search(row[var_index])
            if not variable_match:
                continue
            formula_variable = _normalize_variable(variable_match.group(1))
            description = row[desc_index].strip() if desc_index < len(row) else ""
            source_context, ui_label = _parse_ui_path(description)
            control_type = _classify_control(formula_variable, description)
            sliders.append(
                SliderDefinition(
                    page=PAGE_TO_SECTION.get(page_name, page_name),
                    formula_variable=formula_variable,
                    ui_label=ui_label,
                    wiki_description=description,
                    section=_infer_section(page_name, source_context),
                    control_type=control_type,
                    min_value=None,
                    max_value=None,
                    default_value=None,
                    source_page=source_page or page_name,
                    source_section="Sliders",
                    source_context=source_context,
                    confidence="confirmed" if control_type in {"slider", "dropdown"} else "inferred",
                )
            )
    return sliders
