"""Parse GearCity Components.xml and filter tech availability by year and skill."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from gearcity_optimizer.importers.component_sources import (
    COMPONENTS_FILENAME,
    discover_components_source,
)
from gearcity_optimizer.core.design_skill_decay import effective_required_skill

MIN_AVAILABILITY_YEAR = 1900
OPEN_ENDED_DEATH_YEARS = frozenset({5050, 9999, 30000})

START_YEAR_KEYS = ("year", "start", "startyear", "startingyear", "startYear")
END_YEAR_KEYS = ("death", "end", "endyear", "stopyear", "stop", "stopYear")
SKILL_KEYS = ("skill", "skillreq", "reqskill", "designskill", "skillReq")

# GearCity's shipped Components.xml occasionally omits a space between attributes.
_ATTR_GLUE_PATTERN = re.compile(r'(?<=[\w.])"([A-Za-z_])')

SECTION_CATEGORY_MAP: dict[str, str] = {
    "ChassisComponents": "chassis",
    "SuspensionComponents": "chassis",
    "DrivetrainComponents": "chassis",
    "EngineComponents": "engine",
    "GearboxComponents": "gearbox",
    "NewCarType": "vehicle",
    "CarModels": "vehicle",
    "AccessoriesModels": "vehicle",
}

CHASSIS_TYPES = frozenset({"frame", "suspension", "drivetrain", "chassis"})
ENGINE_TYPES = frozenset(
    {"layout", "cylinder", "fuel", "valve", "induction", "engine"}
)
GEARBOX_TYPES = frozenset({"transmission", "gear", "gears", "gearbox", "addons"})
VEHICLE_TYPES = frozenset({"car", "access", "body", "vehicle"})


class ComponentsValidationError(ValueError):
    """Raised when Components.xml fails structural validation."""


@dataclass(frozen=True)
class ComponentsValidationResult:
    """Outcome of a Components.xml validation pass."""

    success: bool
    warnings: tuple[str, ...]
    detected_categories: tuple[str, ...]


@dataclass(frozen=True)
class ComponentTech:
    """One unlockable sub-component or vehicle-related entry from Components.xml."""

    id: str | None
    name: str
    category: str
    subcategory: str | None
    start_year: int | None
    end_year: int | None
    required_skill: float | None
    raw_attributes: dict[str, str]
    source_path: Path | None


@dataclass(frozen=True)
class ComponentCatalog:
    """Parsed Components.xml catalog."""

    components: list[ComponentTech]
    source_path: Path | None


@dataclass(frozen=True)
class ComponentAvailabilityRow:
    """One component with availability status for display."""

    component: ComponentTech
    status: str
    reason: str
    skill_category: str


def _prepare_xml_bytes(xml_content: bytes | str) -> bytes:
    """Normalize Components.xml bytes and repair common attribute gluing typos."""
    if isinstance(xml_content, str):
        text = xml_content
    else:
        text = xml_content.decode("utf-8", errors="replace")
    text = _ATTR_GLUE_PATTERN.sub(r'" \1', text)
    return text.encode("utf-8")


def validate_year_input(year: int) -> None:
    """Reject years below the minimum supported availability year."""
    if year < MIN_AVAILABILITY_YEAR:
        raise ValueError(
            f"Year must be {MIN_AVAILABILITY_YEAR} or later (got {year})."
        )


def _normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.lower())


def _pick_int(attributes: dict[str, str], keys: tuple[str, ...]) -> int | None:
    normalized = {_normalize_key(key): value for key, value in attributes.items()}
    for key in keys:
        raw = normalized.get(_normalize_key(key))
        if raw is None or raw == "":
            continue
        try:
            return int(float(raw))
        except ValueError:
            continue
    return None


def _pick_float(attributes: dict[str, str], keys: tuple[str, ...]) -> float | None:
    normalized = {_normalize_key(key): value for key, value in attributes.items()}
    for key in keys:
        raw = normalized.get(_normalize_key(key))
        if raw is None or raw == "":
            continue
        try:
            return float(raw)
        except ValueError:
            continue
    return None


def _normalize_end_year(value: int | None) -> int | None:
    if value is None:
        return None
    if value in OPEN_ENDED_DEATH_YEARS or value >= 5000:
        return None
    return value


def _display_name(attributes: dict[str, str]) -> str:
    picture = attributes.get("picture", "").strip()
    if picture:
        stem = Path(picture).stem
        if stem:
            return stem
    name = attributes.get("name", "").strip()
    if name:
        return name
    type_value = attributes.get("type", "").strip()
    if type_value:
        return type_value
    return "unknown"


def _section_category(section_tag: str) -> str:
    return SECTION_CATEGORY_MAP.get(section_tag, section_tag)


def infer_skill_category(component: ComponentTech) -> str:
    """Map a component to a research skill category."""
    subcategory = (component.subcategory or "").lower()
    tag_category = component.category.lower()

    if subcategory in CHASSIS_TYPES or tag_category in {"chassis", "suspension", "drivetrain"}:
        return "chassis"
    if subcategory in ENGINE_TYPES or tag_category == "engine":
        return "engine"
    if subcategory in GEARBOX_TYPES or tag_category == "gearbox":
        return "gearbox"
    if subcategory in VEHICLE_TYPES or tag_category == "vehicle":
        return "vehicle"
    return "unknown"


def _parse_leaf_component(
    node: ET.Element,
    *,
    section_tag: str,
    source_path: Path | None,
) -> ComponentTech:
    attributes = dict(node.attrib)
    attributes["_element_tag"] = node.tag
    subcategory = attributes.get("type") or node.tag
    start_year = _pick_int(attributes, START_YEAR_KEYS)
    end_year = _normalize_end_year(_pick_int(attributes, END_YEAR_KEYS))
    required_skill = _pick_float(attributes, SKILL_KEYS)
    component_id = attributes.get("name") or attributes.get("id")

    return ComponentTech(
        id=component_id,
        name=_display_name(attributes),
        category=_section_category(section_tag),
        subcategory=subcategory,
        start_year=start_year,
        end_year=end_year,
        required_skill=required_skill,
        raw_attributes=attributes,
        source_path=source_path,
    )


def validate_components_xml(xml_content: bytes | str) -> ComponentsValidationResult:
    """Validate Components.xml structure before saving."""
    warnings: list[str] = []
    detected_categories: set[str] = set()

    if isinstance(xml_content, str):
        xml_bytes = _prepare_xml_bytes(xml_content)
    else:
        xml_bytes = _prepare_xml_bytes(xml_content)

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise ComponentsValidationError(
            "Could not parse XML. Make sure you selected a valid Components.xml file."
        ) from exc

    root_tag = root.tag
    if root_tag not in {"Components", "components"}:
        warnings.append(
            f"Unexpected root element <{root_tag}>. Expected <Components>."
        )

    component_nodes = 0
    for child in root:
        section_tag = child.tag
        leaves = list(child)
        if leaves:
            detected_categories.add(_section_category(section_tag))
            component_nodes += len(leaves)

    if component_nodes == 0:
        for node in root.iter():
            if node is root:
                continue
            if node.attrib:
                component_nodes += 1
                parent = _parent_section_tag(node, root)
                if parent:
                    detected_categories.add(_section_category(parent))

    if component_nodes == 0:
        raise ComponentsValidationError(
            "Invalid Components file: no recognizable component entries were found."
        )

    if not detected_categories:
        warnings.append(
            "Component sections were not recognized. Parsing will still preserve "
            "raw XML attributes for inspection."
        )

    return ComponentsValidationResult(
        success=True,
        warnings=tuple(warnings),
        detected_categories=tuple(sorted(detected_categories)),
    )


def _parent_section_tag(node: ET.Element, root: ET.Element) -> str | None:
    for parent in root:
        if node in list(parent):
            return parent.tag
    return None


def parse_components_xml(path: Path) -> ComponentCatalog:
    """Parse a Components.xml file into a catalog model."""
    xml_bytes = _prepare_xml_bytes(path.read_bytes())
    validate_components_xml(xml_bytes)
    root = ET.fromstring(xml_bytes)

    components: list[ComponentTech] = []
    for section in root:
        section_tag = section.tag
        for node in section:
            if not node.attrib:
                continue
            components.append(
                _parse_leaf_component(
                    node,
                    section_tag=section_tag,
                    source_path=path,
                )
            )

    if not components:
        for node in root.iter():
            if node is root or not node.attrib:
                continue
            parent_tag = _parent_section_tag(node, root) or root.tag
            components.append(
                _parse_leaf_component(
                    node,
                    section_tag=parent_tag,
                    source_path=path,
                )
            )

    return ComponentCatalog(components=components, source_path=path)


def load_imported_components_catalog() -> ComponentCatalog | None:
    """Load the user-imported Components.xml catalog, if present."""
    source = discover_components_source()
    if source is None:
        return None
    return parse_components_xml(source.components_file)


def _skill_for_component(
    component: ComponentTech,
    skill_levels: dict[str, float],
) -> float | None:
    skill_category = infer_skill_category(component)
    if skill_category == "unknown":
        return None
    return skill_levels.get(skill_category)


def availability_reason(
    component: ComponentTech,
    year: int,
    skill_levels: dict[str, float],
    *,
    quarter: int = 4,
) -> tuple[str, str]:
    """Return availability status and human-readable reason."""
    if component.start_year is not None and year < component.start_year:
        return (
            "locked",
            f"Unlocks in {component.start_year}",
        )

    if component.end_year is not None and year > component.end_year:
        return (
            "expired",
            f"Expired after {component.end_year}",
        )

    user_skill = _skill_for_component(component, skill_levels)
    required = effective_required_skill(
        component.required_skill,
        component.start_year,
        year,
        quarter=quarter,
    )
    if (
        required is not None
        and user_skill is not None
        and user_skill < required
    ):
        skill_category = infer_skill_category(component)
        base = component.required_skill
        if base is not None and base != required:
            requirement_text = (
                f"{required:.2f} {skill_category} skill "
                f"({base:g} base, adjusted for {year} Q{quarter})"
            )
        else:
            requirement_text = f"{required:g} {skill_category} skill"
        return (
            "locked",
            f"Requires {requirement_text} (have {user_skill:g})",
        )

    if component.start_year is None and component.required_skill is None:
        return ("available", "No year or skill requirement recorded")

    return ("available", "Meets year and skill requirements")


def adjusted_skill_requirement(
    component: ComponentTech,
    year: int,
    *,
    quarter: int = 4,
) -> float | None:
    """Expose decay-adjusted skill requirement for UI and tooling."""
    return effective_required_skill(
        component.required_skill,
        component.start_year,
        year,
        quarter=quarter,
    )


def is_component_available(
    component: ComponentTech,
    year: int,
    skill_levels: dict[str, float],
    *,
    quarter: int = 4,
) -> bool:
    """Return True when a component meets year and skill requirements."""
    validate_year_input(year)
    status, _ = availability_reason(component, year, skill_levels, quarter=quarter)
    return status == "available"


def filter_available_components(
    catalog: ComponentCatalog,
    year: int,
    skill_levels: dict[str, float],
    *,
    quarter: int = 4,
) -> list[ComponentTech]:
    """Return components available at the given year and skill levels."""
    validate_year_input(year)
    return [
        component
        for component in catalog.components
        if is_component_available(component, year, skill_levels, quarter=quarter)
    ]


def classify_components(
    catalog: ComponentCatalog,
    year: int,
    skill_levels: dict[str, float],
    *,
    quarter: int = 4,
    category_filter: str | None = None,
    name_search: str | None = None,
) -> tuple[list[ComponentAvailabilityRow], list[ComponentAvailabilityRow]]:
    """Split components into available and locked/expired rows."""
    validate_year_input(year)
    available: list[ComponentAvailabilityRow] = []
    locked: list[ComponentAvailabilityRow] = []

    search = (name_search or "").strip().lower()
    category = (category_filter or "").strip().lower()

    for component in catalog.components:
        skill_category = infer_skill_category(component)
        if category and skill_category != category and component.category.lower() != category:
            continue
        if search and search not in component.name.lower():
            if search not in (component.id or "").lower():
                continue

        status, reason = availability_reason(
            component, year, skill_levels, quarter=quarter
        )
        row = ComponentAvailabilityRow(
            component=component,
            status=status,
            reason=reason,
            skill_category=skill_category,
        )
        if status == "available":
            available.append(row)
        else:
            locked.append(row)

    return available, locked


def catalog_summary(catalog: ComponentCatalog) -> dict[str, int]:
    """Return counts grouped by parsed category."""
    summary: dict[str, int] = {}
    for component in catalog.components:
        summary[component.category] = summary.get(component.category, 0) + 1
    return summary


# Re-export component choice helpers for a single import surface.
from gearcity_optimizer.importers.component_choices import (  # noqa: E402
    ComponentChoice,
    ComponentChoiceCatalog,
    ComponentsSchemaAudit,
    SchemaAuditSection,
    audit_components_schema,
    choice_type_label,
    component_tech_to_choice,
    format_schema_audit_report,
    get_available_component_choices,
    infer_choice_type,
    load_component_choice_catalog,
    parse_component_choice_catalog,
)
