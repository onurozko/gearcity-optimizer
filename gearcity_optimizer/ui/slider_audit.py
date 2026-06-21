"""Shared helpers for slider and formula influence audit display."""

from __future__ import annotations

from gearcity_optimizer.core.screenshot_label_fixture import (
    CHASSIS_SLIDER_LABELS,
    ENGINE_SLIDER_LABELS,
    GEARBOX_SLIDER_LABELS,
    screenshot_labels,
)
from gearcity_optimizer.core.slider_registry import (
    RealSlider,
    get_outputs_affected_by_slider,
    get_slider_by_variable,
    list_sliders,
    load_slider_registry,
    validate_registry,
    wiki_model_available,
)
from gearcity_optimizer.importers.wiki_formula_effects import FormulaEffect


def format_slider_audit_row(slider: RealSlider) -> dict[str, object]:
    """Format one registry slider for CLI or Streamlit tables."""
    range_text = (
        "1-100"
        if slider.scale == "percent"
        else f"{slider.min_value:g}-{slider.max_value:g}"
    )
    return {
        "page": slider.section,
        "label": slider.label,
        "formula variable": slider.wiki_formula_variable,
        "control type": slider.control_type,
        "source page": slider.source_page,
        "source section": slider.source_section,
        "confidence": slider.confidence,
        "range": range_text,
        "key": slider.key,
        "affected outputs": ", ".join(slider.affected_outputs),
    }


def slider_definition_rows(*, page: str | None = None) -> list[dict[str, object]]:
    """Return wiki-backed slider definition rows."""
    registry = load_slider_registry()
    rows: list[dict[str, object]] = []
    for definition in registry.sliders:
        if page and definition.page != page.strip().lower():
            continue
        rows.append(
            {
                "page": definition.page,
                "label": definition.ui_label,
                "formula variable": definition.formula_variable,
                "control type": definition.control_type,
                "source page": definition.source_page,
                "source section": definition.source_section,
                "confidence": definition.confidence,
            }
        )
    return rows


def formula_influence_rows(*, page: str | None = None) -> list[dict[str, object]]:
    """Return formula influence rows from parsed wiki mechanics."""
    registry = load_slider_registry()
    rows: list[dict[str, object]] = []
    for effect in registry.effects:
        if page and effect.page != page.strip().lower():
            continue
        rows.append(
            {
                "output": effect.output_label,
                "formula section": effect.section_title,
                "sliders used": ", ".join(effect.slider_variables),
                "component variables used": ", ".join(effect.component_variables),
                "source page": effect.source_page,
                "source section": effect.source_section,
                "confidence": effect.confidence,
            }
        )
    return rows


def screenshot_label_audit_rows(*, section: str | None = None) -> list[dict[str, object]]:
    """Return screenshot-validated labels for audit only (no formula effects)."""
    sections = [section.strip().lower()] if section else ("engine", "chassis", "gearbox")
    rows: list[dict[str, object]] = []
    for page in sections:
        for label in screenshot_labels(page):
            rows.append(
                {
                    "page": page,
                    "label": label,
                    "source": "screenshot fixture",
                    "note": "labels only, no formula effects",
                }
            )
    return rows


def slider_detail(slider_variable: str) -> dict[str, object]:
    """Return per-slider audit detail including formula snippets."""
    definition = get_slider_by_variable(slider_variable)
    if definition is None:
        return {"error": f"Unknown slider variable: {slider_variable}"}
    effects = get_outputs_affected_by_slider(slider_variable)
    return {
        "UI label": definition.ui_label,
        "formula variable": definition.formula_variable,
        "wiki description": definition.wiki_description,
        "control type": definition.control_type,
        "source page": definition.source_page,
        "source section": definition.source_section,
        "confidence": definition.confidence,
        "affected outputs": [effect.output_label for effect in effects],
        "formula sections": [effect.section_title for effect in effects],
        "formula snippets": [effect.formula_text[:240] for effect in effects[:5]],
    }


def slider_audit_rows(*, section: str | None = None) -> list[dict[str, object]]:
    """Return formatted audit rows for all or one section."""
    return [format_slider_audit_row(slider) for slider in list_sliders(section=section)]


def slider_audit_warnings() -> list[str]:
    """Return registry validation warnings."""
    return validate_registry()


def list_slider_variables(*, page: str | None = None) -> list[str]:
    """Return selectable wiki formula variables for detail views."""
    registry = load_slider_registry()
    variables = [item.formula_variable for item in registry.sliders]
    if page:
        variables = [
            item.formula_variable
            for item in registry.sliders
            if item.page == page.strip().lower()
        ]
    return sorted(set(variables))


def screenshot_label_sections() -> dict[str, tuple[str, ...]]:
    """Expose screenshot label fixtures for validation tests."""
    return {
        "engine": ENGINE_SLIDER_LABELS,
        "chassis": CHASSIS_SLIDER_LABELS,
        "gearbox": GEARBOX_SLIDER_LABELS,
    }
