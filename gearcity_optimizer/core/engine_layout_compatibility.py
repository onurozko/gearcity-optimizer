"""Backward-compatible wrappers for wiki-backed component compatibility."""

from __future__ import annotations

from gearcity_optimizer.core.wiki_component_compatibility import (
    compatibility_violations,
    filter_compatible_candidates,
    is_valid_component_choices,
    is_valid_partial_choices,
    layout_cylinder_bank_arrangement,
    parse_cylinder_count,
    resolve_engine_layout_key,
    validate_component_choices,
)
from gearcity_optimizer.importers.component_choices import ComponentChoice


def layout_family(choice: ComponentChoice) -> str:
    """Return a coarse layout family string for legacy callers."""
    key = resolve_engine_layout_key(choice)
    if key is None:
        return "unknown"
    return key.lower()


def allowed_cylinder_counts(layout: ComponentChoice) -> set[int] | None:
    """Return allowed cylinder counts for a layout from wiki rules."""
    from gearcity_optimizer.core.wiki_component_compatibility import load_wiki_compatibility_rules

    key = resolve_engine_layout_key(layout)
    if key is None:
        return None
    counts = load_wiki_compatibility_rules()["engine_layouts"][key].get("cylinder_counts", [])
    return set(counts) if counts else {1} if key == "Single" else None


def is_valid_layout_cylinder_combo(
    layout: ComponentChoice | None,
    cylinder: ComponentChoice | None,
) -> bool:
    """Return True when layout and cylinder choices satisfy wiki rules."""
    if layout is None or cylinder is None:
        return True
    return is_valid_partial_choices(
        {"engine_layout": layout, "cylinder_count": cylinder}
    )


def compatibility_penalty_reason(
    layout: ComponentChoice | None,
    cylinder: ComponentChoice | None,
) -> str | None:
    """Return a human-readable reason when a layout/cylinder combo is invalid."""
    if layout is None or cylinder is None:
        return None
    violations = validate_component_choices(
        {"engine_layout": layout, "cylinder_count": cylinder}
    ).violations
    return violations[0] if violations else None
