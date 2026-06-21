"""Shared helpers for slider audit display."""

from __future__ import annotations

from gearcity_optimizer.core.slider_registry import RealSlider, list_sliders, validate_registry


def format_slider_audit_row(slider: RealSlider) -> dict[str, object]:
    """Format one registry slider for CLI or Streamlit tables."""
    if slider.max_value <= 1.0 and slider.min_value >= 0.0 and slider.field_name not in {
        "cylinders",
        "number_of_gears",
    } and not slider.field_name.startswith(("has_", "is_")):
        range_text = "0-100 (normalized 0-1 in formulas)"
    else:
        range_text = f"{slider.min_value:g}-{slider.max_value:g}"
    return {
        "key": slider.key,
        "label": slider.label,
        "section": slider.section,
        "formula variable": slider.formula_variable or "",
        "range": range_text,
        "affected outputs": ", ".join(slider.affects_outputs),
        "confidence": slider.confidence,
        "source": slider.source,
    }


def slider_audit_rows(*, section: str | None = None) -> list[dict[str, object]]:
    """Return formatted audit rows for all or one section."""
    return [format_slider_audit_row(slider) for slider in list_sliders(section=section)]


def slider_audit_warnings() -> list[str]:
    """Return registry validation warnings."""
    return validate_registry()
