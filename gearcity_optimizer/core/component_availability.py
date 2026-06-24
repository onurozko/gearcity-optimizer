"""Shared component availability context for Design Optimizer and Tech Availability."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gearcity_optimizer.importers.component_sources import components_missing_message
from gearcity_optimizer.importers.components_xml import (
    ComponentAvailabilityRow,
    ComponentCatalog,
    ComponentTech,
    classify_components,
    load_imported_components_catalog,
)

MISSING_CATALOG_WARNING = (
    "Components.xml has not been imported. Import your GearCity Components.xml "
    "file to enable tech unlock and part availability analysis."
)


@dataclass(frozen=True)
class ComponentAvailabilityContext:
    """Filtered component availability for a year and skill setup."""

    year: int
    quarter: int
    catalog_loaded: bool
    source_path: Path | None
    available_components: list[ComponentTech]
    locked_components: list[ComponentTech]
    available_rows: list[ComponentAvailabilityRow]
    locked_rows: list[ComponentAvailabilityRow]
    available_count: int
    locked_count: int
    warnings: list[str]


def _skill_levels(
    *,
    chassis_skill: float,
    engine_skill: float,
    gearbox_skill: float,
    vehicle_skill: float,
) -> dict[str, float]:
    return {
        "chassis": chassis_skill,
        "engine": engine_skill,
        "gearbox": gearbox_skill,
        "vehicle": vehicle_skill,
    }


def get_component_availability_context(
    year: int,
    chassis_skill: float,
    engine_skill: float,
    gearbox_skill: float,
    vehicle_skill: float,
    *,
    quarter: int = 4,
    category_filter: str | None = None,
    name_search: str | None = None,
    catalog: ComponentCatalog | None = None,
) -> ComponentAvailabilityContext:
    """Load catalog and return available/locked components for year and skills."""
    loaded_catalog = catalog if catalog is not None else load_imported_components_catalog()
    if loaded_catalog is None:
        return ComponentAvailabilityContext(
            year=year,
            quarter=quarter,
            catalog_loaded=False,
            source_path=None,
            available_components=[],
            locked_components=[],
            available_rows=[],
            locked_rows=[],
            available_count=0,
            locked_count=0,
            warnings=[MISSING_CATALOG_WARNING, components_missing_message()],
        )

    skill_levels = _skill_levels(
        chassis_skill=chassis_skill,
        engine_skill=engine_skill,
        gearbox_skill=gearbox_skill,
        vehicle_skill=vehicle_skill,
    )
    available_rows, locked_rows = classify_components(
        loaded_catalog,
        year,
        skill_levels,
        quarter=quarter,
        category_filter=category_filter,
        name_search=name_search,
    )
    available_components = [row.component for row in available_rows]
    locked_components = [row.component for row in locked_rows]
    return ComponentAvailabilityContext(
        year=year,
        quarter=quarter,
        catalog_loaded=True,
        source_path=loaded_catalog.source_path,
        available_components=available_components,
        locked_components=locked_components,
        available_rows=available_rows,
        locked_rows=locked_rows,
        available_count=len(available_components),
        locked_count=len(locked_components),
        warnings=[],
    )
