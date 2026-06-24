"""Schema-aware component choice parsing from Components.xml."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from gearcity_optimizer.importers.components_xml import (
    CHASSIS_TYPES,
    ENGINE_TYPES,
    GEARBOX_TYPES,
    ComponentCatalog,
    ComponentTech,
    _normalize_key,
    _pick_float,
    _pick_int,
    _prepare_xml_bytes,
    infer_skill_category,
    is_component_available,
    load_imported_components_catalog,
    parse_components_xml,
    validate_year_input,
)

METADATA_KEYS = frozenset(
    {
        "name",
        "id",
        "type",
        "year",
        "start",
        "startyear",
        "death",
        "end",
        "skill",
        "skillreq",
        "reqskill",
        "designskill",
        "picture",
        "pic",
        "icon",
        "description",
        "comment",
    }
)

CHOICE_TYPE_LABELS: dict[str, str] = {
    "engine_layout": "Engine layout",
    "cylinder_count": "Cylinder count / layout count",
    "fuel_type": "Fuel type",
    "valvetrain": "Valvetrain",
    "forced_induction": "Forced induction",
    "transverse_engine": "Transverse engine",
    "frame": "Frame",
    "suspension_front": "Front suspension",
    "suspension_rear": "Rear suspension",
    "suspension": "Suspension",
    "drivetrain": "Drivetrain",
    "gearbox_type": "Gearbox type",
    "gear_count": "Gear count",
    "overdrive": "Overdrive",
    "vehicle_body": "Vehicle body",
    "unknown": "Unknown choice",
}


@dataclass(frozen=True)
class ComponentChoice:
    """One selectable component/dropdown option from Components.xml."""

    id: str | None
    name: str
    display_name: str
    section: str
    choice_type: str
    start_year: int | None
    end_year: int | None
    required_skill: float | None
    stats: dict[str, float]
    raw_attributes: dict[str, str]
    source_path: Path | None
    confidence: str


@dataclass(frozen=True)
class ComponentChoiceCatalog:
    """Parsed selectable component choices."""

    choices: list[ComponentChoice]
    source_path: Path | None
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SchemaAuditSection:
    """One Components.xml section summary."""

    section_tag: str
    child_tags: tuple[str, ...]
    attributes: tuple[str, ...]
    guessed_section: str
    guessed_choice_types: tuple[str, ...]
    sample_rows: tuple[dict[str, str], ...]

@dataclass(frozen=True)
class ChoiceTypeAuditRow:
    """Summary of one parsed component choice type."""

    choice_type: str
    section: str
    count: int
    sample_names: tuple[str, ...]
    stat_keys_used: tuple[str, ...]
    high_confidence_count: int
    low_confidence_count: int


@dataclass(frozen=True)
class ComponentsChoiceTypeAudit:
    """Choice-type counts and samples from a parsed Components.xml catalog."""

    choice_types: tuple[ChoiceTypeAuditRow, ...]
    total_entries: int
    unknown_count: int
    sections: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ComponentsSchemaAudit:
    """Structural audit of a Components.xml file."""

    root_tag: str
    sections: list[SchemaAuditSection]
    warnings: list[str]
    choice_type_audit: ComponentsChoiceTypeAudit | None = None


def choice_type_label(choice_type: str) -> str:
    """Return a human label for a choice type key."""
    return CHOICE_TYPE_LABELS.get(choice_type, choice_type.replace("_", " ").title())


def _extract_stats(attributes: dict[str, str]) -> dict[str, float]:
    stats: dict[str, float] = {}
    for key, raw in attributes.items():
        normalized = _normalize_key(key)
        if normalized in METADATA_KEYS:
            continue
        try:
            stats[normalized] = float(raw)
        except ValueError:
            continue
    return stats


def _guess_suspension_type(name: str, attributes: dict[str, str]) -> str:
    text = " ".join(
        [
            name,
            attributes.get("picture", ""),
            attributes.get("type", ""),
            attributes.get("name", ""),
        ]
    ).lower()
    if "front" in text:
        return "suspension_front"
    if "rear" in text or "back" in text:
        return "suspension_rear"
    return "suspension"


def infer_choice_type(
    *,
    section: str,
    subcategory: str | None,
    element_tag: str | None,
    name: str,
    attributes: dict[str, str],
) -> tuple[str, str]:
    """Map a catalog entry to a discrete choice type and confidence."""
    subtype = (subcategory or element_tag or "").lower()
    tag = (element_tag or "").lower()
    section_key = section.lower()

    if section_key == "engine" or subtype in ENGINE_TYPES or tag in ENGINE_TYPES:
        if subtype in {"layout"} or tag == "layout":
            return "engine_layout", "high"
        if subtype in {"cylinder", "cylinders"} or tag == "cylinder":
            return "cylinder_count", "high"
        if subtype in {"fuel"} or tag == "fuel":
            return "fuel_type", "high"
        if subtype in {"valve", "valvetrain"} or tag in {"valve", "valvetrain"}:
            return "valvetrain", "high"
        if subtype in {"induction", "aspiration"} or tag in {"induction", "aspiration"}:
            return "forced_induction", "high"
        if "transverse" in name.lower() or attributes.get("transverse", "").lower() in {
            "1",
            "true",
            "yes",
        }:
            return "transverse_engine", "medium"
        return "unknown", "low"

    if section_key == "chassis" or subtype in CHASSIS_TYPES or tag in CHASSIS_TYPES:
        if subtype == "frame" or tag == "chassis":
            return "frame", "high"
        if subtype == "suspension" or tag == "suspension":
            return _guess_suspension_type(name, attributes), "medium"
        if subtype == "drivetrain" or tag == "drivetrain":
            return "drivetrain", "high"
        return "unknown", "low"

    if section_key == "gearbox" or subtype in GEARBOX_TYPES or tag in GEARBOX_TYPES:
        if subtype in {"transmission", "gearbox"} or tag in {"gearbox", "transmission"}:
            return "gearbox_type", "high"
        if subtype in {"gear", "gears"} or tag in {"gear", "gears"}:
            return "gear_count", "high"
        if "overdrive" in name.lower() or subtype == "overdrive":
            return "overdrive", "medium"
        return "unknown", "low"

    if section_key == "vehicle":
        return "vehicle_body", "medium"

    return "unknown", "low"


def component_tech_to_choice(component: ComponentTech) -> ComponentChoice:
    """Convert a parsed ComponentTech row into a ComponentChoice."""
    element_tag = component.raw_attributes.get("_element_tag")
    choice_type, confidence = infer_choice_type(
        section=component.category,
        subcategory=component.subcategory,
        element_tag=element_tag,
        name=component.name,
        attributes=component.raw_attributes,
    )
    return ComponentChoice(
        id=component.id,
        name=component.name,
        display_name=component.name,
        section=infer_skill_category(component) if infer_skill_category(component) != "unknown" else component.category,
        choice_type=choice_type,
        start_year=component.start_year,
        end_year=component.end_year,
        required_skill=component.required_skill,
        stats=_extract_stats(component.raw_attributes),
        raw_attributes=component.raw_attributes,
        source_path=component.source_path,
        confidence=confidence,
    )


def parse_component_choice_catalog(catalog: ComponentCatalog) -> ComponentChoiceCatalog:
    """Build a choice catalog from a parsed Components.xml catalog."""
    warnings: list[str] = []
    choices = [component_tech_to_choice(component) for component in catalog.components]
    unknown_count = sum(1 for choice in choices if choice.choice_type == "unknown")
    if unknown_count:
        warnings.append(
            f"{unknown_count} entries could not be mapped to a known choice type. "
            "Run components-schema-audit for details."
        )
    low_confidence = sum(1 for choice in choices if choice.confidence == "low")
    if low_confidence:
        warnings.append(
            f"{low_confidence} entries were classified with low confidence."
        )
    return ComponentChoiceCatalog(
        choices=choices,
        source_path=catalog.source_path,
        warnings=warnings,
    )


def load_component_choice_catalog() -> ComponentChoiceCatalog | None:
    """Load imported Components.xml as a choice catalog."""
    catalog = load_imported_components_catalog()
    if catalog is None:
        return None
    return parse_component_choice_catalog(catalog)


def get_available_component_choices(
    year: int,
    chassis_skill: float,
    engine_skill: float,
    gearbox_skill: float,
    vehicle_skill: float,
    *,
    quarter: int = 4,
    catalog: ComponentCatalog | None = None,
) -> list[ComponentChoice]:
    """Return component choices available for the given year and skills."""
    validate_year_input(year)
    loaded = catalog if catalog is not None else load_imported_components_catalog()
    if loaded is None:
        return []

    skill_levels = {
        "chassis": chassis_skill,
        "engine": engine_skill,
        "gearbox": gearbox_skill,
        "vehicle": vehicle_skill,
    }
    choice_catalog = parse_component_choice_catalog(loaded)
    available: list[ComponentChoice] = []
    for choice in choice_catalog.choices:
        tech = ComponentTech(
            id=choice.id,
            name=choice.name,
            category=choice.section,
            subcategory=choice.raw_attributes.get("type"),
            start_year=choice.start_year,
            end_year=choice.end_year,
            required_skill=choice.required_skill,
            raw_attributes=choice.raw_attributes,
            source_path=choice.source_path,
        )
        if is_component_available(tech, year, skill_levels, quarter=quarter):
            available.append(choice)
    return available


def audit_component_choice_types(catalog: ComponentCatalog) -> ComponentsChoiceTypeAudit:
    """Summarize parsed choice types, samples, and scoring attributes."""
    choice_catalog = parse_component_choice_catalog(catalog)
    grouped: dict[str, list[ComponentChoice]] = {}
    for choice in choice_catalog.choices:
        grouped.setdefault(choice.choice_type, []).append(choice)

    rows: list[ChoiceTypeAuditRow] = []
    for choice_type in sorted(grouped):
        items = grouped[choice_type]
        section = items[0].section if items else "unknown"
        stat_keys: set[str] = set()
        for item in items:
            stat_keys.update(item.stats.keys())
        rows.append(
            ChoiceTypeAuditRow(
                choice_type=choice_type,
                section=section,
                count=len(items),
                sample_names=tuple(item.display_name for item in items[:5]),
                stat_keys_used=tuple(sorted(stat_keys)),
                high_confidence_count=sum(1 for item in items if item.confidence == "high"),
                low_confidence_count=sum(1 for item in items if item.confidence == "low"),
            )
        )

    unknown_count = sum(1 for choice in choice_catalog.choices if choice.choice_type == "unknown")
    sections = tuple(sorted({choice.section for choice in choice_catalog.choices}))
    warnings = tuple(choice_catalog.warnings)
    return ComponentsChoiceTypeAudit(
        choice_types=tuple(rows),
        total_entries=len(choice_catalog.choices),
        unknown_count=unknown_count,
        sections=sections,
        warnings=warnings,
    )


def format_choice_type_audit_summary(
    audit: ComponentsChoiceTypeAudit,
) -> list[dict[str, object]]:
    """Render choice-type audit rows for tables."""
    return [
        {
            "Choice type": choice_type_label(row.choice_type),
            "Section": row.section,
            "Count": row.count,
            "Sample names": ", ".join(row.sample_names),
            "Scoring attributes": ", ".join(row.stat_keys_used) or "(none parsed)",
            "High confidence": row.high_confidence_count,
            "Low confidence": row.low_confidence_count,
        }
        for row in audit.choice_types
    ]


def audit_components_schema(path: Path) -> ComponentsSchemaAudit:
    """Inspect Components.xml structure for parser reliability."""
    xml_bytes = _prepare_xml_bytes(path.read_bytes())
    root = ET.fromstring(xml_bytes)
    warnings: list[str] = []
    sections: list[SchemaAuditSection] = []

    for section in root:
        child_tags: dict[str, int] = {}
        attribute_names: set[str] = set()
        samples: list[dict[str, str]] = []
        guessed_types: set[str] = set()

        for node in section:
            if not node.attrib:
                continue
            child_tags[node.tag] = child_tags.get(node.tag, 0) + 1
            attribute_names.update(node.attrib.keys())
            attributes = dict(node.attrib)
            attributes["_element_tag"] = node.tag
            choice_type, _ = infer_choice_type(
                section=_section_from_tag(section.tag),
                subcategory=attributes.get("type"),
                element_tag=node.tag,
                name=attributes.get("picture") or attributes.get("name") or node.tag,
                attributes=attributes,
            )
            guessed_types.add(choice_type)
            if len(samples) < 3:
                samples.append(
                    {
                        "tag": node.tag,
                        "name": attributes.get("name", ""),
                        "type": attributes.get("type", ""),
                        "choice_type": choice_type,
                    }
                )

        if not child_tags:
            warnings.append(f"Section <{section.tag}> has no child component nodes.")
        sections.append(
            SchemaAuditSection(
                section_tag=section.tag,
                child_tags=tuple(sorted(child_tags.keys())),
                attributes=tuple(sorted(attribute_names)),
                guessed_section=_section_from_tag(section.tag),
                guessed_choice_types=tuple(sorted(guessed_types)),
                sample_rows=tuple(samples),
            )
        )

    if not sections:
        warnings.append("No top-level component sections were found under the XML root.")

    choice_type_audit: ComponentsChoiceTypeAudit | None = None
    try:
        catalog = parse_components_xml(path)
        choice_type_audit = audit_component_choice_types(catalog)
        if choice_type_audit.unknown_count:
            warnings.append(
                f"{choice_type_audit.unknown_count} entries mapped to unknown choice types."
            )
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Could not build choice-type audit: {exc}")

    return ComponentsSchemaAudit(
        root_tag=root.tag,
        sections=sections,
        warnings=warnings,
        choice_type_audit=choice_type_audit,
    )


def _section_from_tag(section_tag: str) -> str:
    mapping = {
        "ChassisComponents": "chassis",
        "SuspensionComponents": "chassis",
        "DrivetrainComponents": "chassis",
        "EngineComponents": "engine",
        "GearboxComponents": "gearbox",
        "NewCarType": "vehicle",
        "CarModels": "vehicle",
        "AccessoriesModels": "vehicle",
    }
    return mapping.get(section_tag, section_tag)


def format_schema_audit_report(audit: ComponentsSchemaAudit) -> str:
    """Render a schema audit as plain text."""
    lines = [f"XML root: <{audit.root_tag}>"]
    for warning in audit.warnings:
        lines.append(f"WARNING: {warning}")
    for section in audit.sections:
        lines.append("")
        lines.append(f"Section: <{section.section_tag}>")
        lines.append(f"  Guessed category: {section.guessed_section}")
        lines.append(f"  Child tags: {', '.join(section.child_tags) or '(none)'}")
        lines.append(f"  Attributes: {', '.join(section.attributes) or '(none)'}")
        lines.append(
            "  Guessed choice types: "
            + (", ".join(section.guessed_choice_types) or "(none)")
        )
        if section.sample_rows:
            lines.append("  Sample rows:")
            for row in section.sample_rows:
                lines.append(
                    "    - tag={tag}, name={name}, type={type}, choice_type={choice_type}".format(
                        **row
                    )
                )
    if audit.choice_type_audit is not None:
        lines.append("")
        lines.append("Choice type summary:")
        for row in audit.choice_type_audit.choice_types:
            samples = ", ".join(row.sample_names) or "(none)"
            stats = ", ".join(row.stat_keys_used) or "(none)"
            lines.append(
                f"  - {row.choice_type} ({row.section}): count={row.count}, "
                f"samples={samples}, scoring attrs={stats}"
            )
    return "\n".join(lines)
