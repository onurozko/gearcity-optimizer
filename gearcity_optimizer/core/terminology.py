"""Terminology mapping with evidence-backed verification."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from gearcity_optimizer.core.terminology_verification import (
    TerminologyEntry,
    TerminologyEvidence,
    VERIFICATION_BUILDERS,
    format_audit_entry_text,
    search_terminology_sources,
    sources_available,
    verify_chassis_durability_mapping,
    verify_drivability_handling_mapping,
    verify_engine_reliability_mapping,
    verify_gearbox_comfort_mapping,
    verify_gearbox_reliability_mapping,
    verify_term_search,
)

__all__ = [
    "TerminologyEntry",
    "TerminologyEvidence",
    "TerminologyLayer",
    "VERIFICATION_BUILDERS",
    "format_audit_entry_text",
    "search_terminology_sources",
    "verify_term_search",
]


@dataclass(frozen=True)
class TerminologyLayer:
    """Describes a rating concept and how it differs from related concepts."""

    name: str
    level: str
    description: str
    related_but_not_same_as: tuple[str, ...]


@dataclass(frozen=True)
class _TerminologySpec:
    component: str
    internal_key: str
    formula_label: str
    observed_game_label: str | None
    layer: str
    display_label: str | None = None
    search_terms: tuple[str, ...] = ()


TERMINOLOGY_LAYERS: tuple[TerminologyLayer, ...] = (
    TerminologyLayer(
        name="Engine Reliability Rating",
        level="component stat",
        description=(
            "Reliability/dependability of the engine component itself. This affects "
            "how suitable the engine is for dependable vehicles and contributes to "
            "final vehicle dependability through vehicle formulas."
        ),
        related_but_not_same_as=(
            "Chassis Durability Rating",
            "Gearbox Reliability Rating",
            "Vehicle Dependability Rating",
            "Overall Rating",
        ),
    ),
    TerminologyLayer(
        name="Chassis Durability Rating",
        level="component stat",
        description=(
            "Durability/dependability-related rating of the chassis component. "
            "This is not automatically the same as final vehicle dependability."
        ),
        related_but_not_same_as=(
            "Engine Reliability Rating",
            "Vehicle Dependability Rating",
            "Dependability Importance",
        ),
    ),
    TerminologyLayer(
        name="Gearbox Reliability Rating",
        level="component stat",
        description=(
            "Reliability/dependability of the gearbox component itself. Gearbox "
            "torque mismatch can also hurt final quality/dependability."
        ),
        related_but_not_same_as=(
            "Engine Reliability Rating",
            "Vehicle Dependability Rating",
            "Overall Rating",
        ),
    ),
    TerminologyLayer(
        name="Vehicle Dependability Rating",
        level="final vehicle stat",
        description=(
            "The assembled vehicle's dependability rating (Rating_Dependability). "
            "It depends on component ratings, design focus, testing, materials, "
            "and penalties."
        ),
        related_but_not_same_as=(
            "Engine Reliability Rating",
            "Chassis Durability Rating",
            "Gearbox Reliability Rating",
            "Dependability Importance",
            "Overall Rating",
        ),
    ),
    TerminologyLayer(
        name="Dependability Importance",
        level="vehicle type weight",
        description=(
            "How much this vehicle type's buyers care about final vehicle "
            "dependability."
        ),
        related_but_not_same_as=(
            "Vehicle Dependability Rating",
            "Engine Reliability Rating",
            "Overall Rating",
        ),
    ),
    TerminologyLayer(
        name="Overall Rating",
        level="summary rating",
        description=(
            "Overall is a broad summary rating. It should not be treated as the "
            "same thing as dependability."
        ),
        related_but_not_same_as=(
            "Vehicle Dependability Rating",
            "Engine Reliability Rating",
            "Chassis Durability Rating",
            "Gearbox Reliability Rating",
        ),
    ),
)


TERMINOLOGY_SPECS: dict[tuple[str, str], _TerminologySpec] = {
    ("chassis", "comfort"): _TerminologySpec(
        "chassis", "comfort", "Comfort Rating", "Ride comfort", "component stat",
        search_terms=("Comfort Rating", "Comfort_Rating"),
    ),
    ("chassis", "performance"): _TerminologySpec(
        "chassis", "performance", "Performance Rating", None, "component stat",
        search_terms=("Performance Rating", "Performance_Rating"),
    ),
    ("chassis", "strength"): _TerminologySpec(
        "chassis", "strength", "Strength Rating", None, "component stat",
        search_terms=("Strength Rating", "Strength_Rating"),
    ),
    ("chassis", "low_weight"): _TerminologySpec(
        "chassis", "low_weight", "Low weight", None, "component stat",
    ),
    ("chassis", "cargo_space"): _TerminologySpec(
        "chassis", "cargo_space", "Cargo space", None, "component stat",
    ),
    ("chassis", "engine_fit_room"): _TerminologySpec(
        "chassis", "engine_fit_room", "Engine fit room", None, "component stat",
    ),
    ("engine", "horsepower"): _TerminologySpec(
        "engine", "horsepower", "Horsepower", None, "component stat",
        search_terms=("Horsepower",),
    ),
    ("engine", "torque"): _TerminologySpec(
        "engine", "torque", "Torque", None, "component stat",
        search_terms=("Torque",),
    ),
    ("engine", "power_rating"): _TerminologySpec(
        "engine",
        "power_rating",
        "Power Rating",
        "Power",
        "component stat",
        search_terms=("Power Rating", "Power_Rating", "Horsepower", "Torque"),
    ),
    ("engine", "fuel_economy"): _TerminologySpec(
        "engine", "fuel_economy", "Fuel Economy Rating", None, "component stat",
        search_terms=("Fuel Economy Rating", "Fuel_Economy"),
    ),
    ("engine", "smoothness"): _TerminologySpec(
        "engine", "smoothness", "Smoothness Rating", None, "component stat",
        search_terms=("Smoothness Rating", "Smoothness_Rating"),
    ),
    ("engine", "low_weight"): _TerminologySpec(
        "engine", "low_weight", "Low weight", None, "component stat",
    ),
    ("engine", "compact_size"): _TerminologySpec(
        "engine", "compact_size", "Compact size", None, "component stat",
    ),
    ("gearbox", "max_torque"): _TerminologySpec(
        "gearbox",
        "max_torque",
        "Maximum Torque Support",
        "Max torque",
        "component stat",
        search_terms=("Maximum Torque", "Max Torque", "max_torque"),
    ),
    ("gearbox", "power"): _TerminologySpec(
        "gearbox", "power", "Power Rating", "Power", "component stat",
        search_terms=("Power Rating",),
    ),
    ("gearbox", "fuel_economy"): _TerminologySpec(
        "gearbox", "fuel_economy", "Fuel Economy Rating", None, "component stat",
        search_terms=("Fuel Economy Rating",),
    ),
    ("gearbox", "performance"): _TerminologySpec(
        "gearbox", "performance", "Performance Rating", None, "component stat",
        search_terms=("Performance Rating",),
    ),
    ("gearbox", "low_weight"): _TerminologySpec(
        "gearbox", "low_weight", "Low weight", None, "component stat",
    ),
    ("vehicle_design", "safety_focus"): _TerminologySpec(
        "vehicle_design",
        "safety_focus",
        "Design Focus: Safety",
        "Design Focus: Safety",
        "design sliders & testing focus",
        display_label="Design Focus: Safety",
        search_terms=("Design Focus: Safety", "Slider_Safety"),
    ),
    ("vehicle_design", "dependability_focus"): _TerminologySpec(
        "vehicle_design",
        "dependability_focus",
        "Design Focus: Dependability",
        "Design Focus: Dependability",
        "design sliders & testing focus",
        display_label="Design Focus: Dependability",
        search_terms=("Design Focus: Dependability",),
    ),
    ("vehicle_design", "cargo_focus"): _TerminologySpec(
        "vehicle_design",
        "cargo_focus",
        "Design Focus: Cargo",
        "Design Focus: Cargo",
        "design sliders & testing focus",
        display_label="Design Focus: Cargo",
    ),
    ("vehicle_design", "luxury_focus"): _TerminologySpec(
        "vehicle_design",
        "luxury_focus",
        "Design Focus: Luxury",
        "Design Focus: Luxury",
        "design sliders & testing focus",
        display_label="Design Focus: Luxury",
    ),
    ("vehicle_design", "style_focus"): _TerminologySpec(
        "vehicle_design",
        "style_focus",
        "Design Focus: Style",
        "Design Focus: Style",
        "design sliders & testing focus",
        display_label="Design Focus: Style",
    ),
    ("vehicle_design", "material_quality"): _TerminologySpec(
        "vehicle_design",
        "material_quality",
        "Material quality",
        None,
        "design sliders & testing focus",
        display_label="Materials: Material Quality",
    ),
    ("vehicle_design", "testing_reliability"): _TerminologySpec(
        "vehicle_design",
        "testing_reliability",
        "Testing: Reliability",
        None,
        "design sliders & testing focus",
        display_label="Testing: Reliability",
    ),
    ("vehicle_design", "testing_fuel"): _TerminologySpec(
        "vehicle_design",
        "testing_fuel",
        "Testing: Fuel economy",
        None,
        "design sliders & testing focus",
        display_label="Testing: Fuel Economy",
    ),
    ("vehicle_design", "testing_performance"): _TerminologySpec(
        "vehicle_design",
        "testing_performance",
        "Testing: Performance",
        None,
        "design sliders & testing focus",
        display_label="Testing: Performance",
    ),
    ("vehicle_design", "testing_utility"): _TerminologySpec(
        "vehicle_design",
        "testing_utility",
        "Testing: Utility",
        None,
        "design sliders & testing focus",
        display_label="Testing: Utility",
    ),
    ("vehicle", "luxury"): _TerminologySpec(
        "vehicle", "luxury", "Luxury Rating", None, "final vehicle stat",
        display_label="Luxury", search_terms=("Luxury",),
    ),
    ("vehicle", "safety"): _TerminologySpec(
        "vehicle", "safety", "Safety Rating", None, "final vehicle stat",
        display_label="Safety", search_terms=("Safety",),
    ),
    ("vehicle", "dependability"): _TerminologySpec(
        "vehicle",
        "dependability",
        "Dependability Rating",
        "Dependability",
        "final vehicle stat",
        display_label="Dependability",
        search_terms=("Dependability", "Dependability Rating", "Rating_Dependability"),
    ),
    ("vehicle", "quality"): _TerminologySpec(
        "vehicle",
        "quality",
        "Quality Rating",
        None,
        "final vehicle stat",
        display_label="Quality",
        search_terms=("Quality Rating", "Quality"),
    ),
    ("vehicle", "fuel"): _TerminologySpec(
        "vehicle", "fuel", "Fuel Economy Rating", "Fuel", "final vehicle stat",
        display_label="Fuel economy", search_terms=("Fuel", "Fuel Economy"),
    ),
    ("vehicle", "performance"): _TerminologySpec(
        "vehicle", "performance", "Performance Rating", None, "final vehicle stat",
        display_label="Performance", search_terms=("Performance",),
    ),
    ("vehicle", "power"): _TerminologySpec(
        "vehicle", "power", "Power Rating", "Power", "final vehicle stat",
        display_label="Power", search_terms=("Power Rating", "Power", "Rating_Power"),
    ),
    ("vehicle", "cargo"): _TerminologySpec(
        "vehicle", "cargo", "Cargo Rating", "Cargo", "final vehicle stat",
        display_label="Cargo", search_terms=("Cargo",),
    ),
    ("vehicle", "overall"): _TerminologySpec(
        "vehicle", "overall", "Overall Rating", "Overall", "summary rating",
        display_label="Overall rating", search_terms=("Overall Rating", "Overall"),
    ),
    ("vehicle_type", "dependability"): _TerminologySpec(
        "vehicle_type",
        "dependability",
        "Dependability Importance",
        None,
        "vehicle type weight",
        display_label="Dependability Importance",
    ),
}

_VERIFIED_CACHE: dict[tuple[str, str, str], TerminologyEntry] = {}


def clear_terminology_cache() -> None:
    """Clear cached verified terminology entries (for tests)."""
    _VERIFIED_CACHE.clear()


def _cache_key(component: str, internal_key: str, root: Path | None) -> tuple[str, str, str]:
    base = str((root or Path(".")).resolve())
    return (component, internal_key, base)


def _build_generic_entry(
    spec: _TerminologySpec,
    *,
    root: Path | None,
) -> TerminologyEntry:
    terms = list(spec.search_terms) if spec.search_terms else [spec.formula_label]
    evidence = search_terminology_sources(terms, root=root)
    display = spec.display_label or spec.formula_label

    if spec.component == "vehicle_type":
        status = "confirmed"
        explanation = (
            f"{spec.formula_label} comes from vehicle_types.csv for this project."
        )
    elif evidence:
        status = "confirmed"
        explanation = (
            f"Local sources reference {spec.formula_label}. "
            f"Layer: {spec.layer}."
        )
    elif not sources_available(root):
        status = "unknown"
        explanation = (
            "Terminology sources are missing. Run setup-sources or download-wiki "
            f"and import-wiki before verifying {spec.formula_label}."
        )
    else:
        status = "unknown"
        explanation = (
            f"No local source matches for {spec.formula_label} yet. "
            f"Layer: {spec.layer}."
        )

    return TerminologyEntry(
        component=spec.component,
        internal_key=spec.internal_key,
        formula_label=spec.formula_label,
        observed_game_label=spec.observed_game_label,
        display_label=display,
        status=status,
        evidence=evidence,
        explanation=explanation,
        layer=spec.layer,
    )


def get_verified_terminology_entry(
    component: str,
    internal_key: str,
    *,
    root: Path | None = None,
) -> TerminologyEntry:
    """Return an evidence-backed terminology entry."""
    key = _cache_key(component, internal_key, root)
    if key in _VERIFIED_CACHE:
        return _VERIFIED_CACHE[key]

    builder = VERIFICATION_BUILDERS.get((component, internal_key))
    if builder is not None:
        entry = builder(root=root)
    else:
        spec = TERMINOLOGY_SPECS.get((component, internal_key))
        if spec is None:
            fallback = internal_key.replace("_", " ").title()
            entry = TerminologyEntry(
                component=component,
                internal_key=internal_key,
                formula_label=fallback,
                observed_game_label=None,
                display_label=fallback,
                status="unknown",
                evidence=[],
                explanation="No terminology mapping defined yet.",
                layer="unknown",
            )
        else:
            entry = _build_generic_entry(spec, root=root)

    _VERIFIED_CACHE[key] = entry
    return entry


def get_terminology_entry(
    component: str,
    internal_key: str,
    *,
    root: Path | None = None,
) -> TerminologyEntry:
    """Return terminology mapping for a component stat key."""
    return get_verified_terminology_entry(component, internal_key, root=root)


def format_priority_label(
    component: str,
    internal_key: str,
    *,
    root: Path | None = None,
) -> str:
    """Return a display label based on verified terminology status."""
    return get_verified_terminology_entry(
        component, internal_key, root=root
    ).display_label


FINAL_VEHICLE_RATING_SECTION_TITLE = "Final vehicle rating priorities"
DESIGN_SLIDER_SECTION_TITLE = "Design sliders & testing focus"

VEHICLE_TYPE_RATING_KEYS: tuple[str, ...] = (
    "luxury",
    "safety",
    "dependability",
    "fuel",
    "performance",
    "power",
    "drivability",
    "cargo",
)

QUALITY_UNIVERSAL_NOTE = (
    "universal buyer-rating factor, not vehicle-type-specific"
)


def format_final_vehicle_stat_label(stat: str, *, root: Path | None = None) -> str:
    """Return a GearCity-aligned label for a final vehicle stat key."""
    return format_final_vehicle_rating_label(stat, root=root)


FINAL_VEHICLE_RATING_LABELS: dict[str, str] = {
    "luxury": "Luxury",
    "safety": "Safety",
    "dependability": "Dependability",
    "quality": "Quality",
    "fuel": "Fuel economy",
    "performance": "Performance",
    "power": "Power",
    "drivability": "Driveability",
    "cargo": "Cargo",
}


def format_final_vehicle_rating_label(stat: str, *, root: Path | None = None) -> str:
    """Return the canonical display label for a final vehicle rating key."""
    if stat in FINAL_VEHICLE_RATING_LABELS:
        return FINAL_VEHICLE_RATING_LABELS[stat]
    return get_verified_terminology_entry("vehicle", stat, root=root).display_label


def importance_stars(weight: float) -> str:
    """Map an importance weight to a display-only star level."""
    if weight >= 0.80:
        return "★★★★★ Critical"
    if weight >= 0.60:
        return "★★★★ High"
    if weight >= 0.40:
        return "★★★ Medium"
    if weight >= 0.20:
        return "★★ Low"
    return "★ Minor"


def format_final_vehicle_rating_line(
    stat: str,
    weight: float,
    *,
    include_stars: bool = False,
    numbered: int | None = None,
    root: Path | None = None,
) -> str:
    """Format one final vehicle rating priority line for display."""
    label = format_final_vehicle_rating_label(stat, root=root)
    prefix = f"{numbered}. " if numbered is not None else ""
    suffix = importance_stars(weight) if include_stars else f"{weight:.2f}"
    return f"{prefix}{label} — {suffix}"


def format_quality_universal_line(
    weight: float,
    *,
    include_stars: bool = False,
) -> str:
    """Format the universal quality note separately from vehicle type weights."""
    suffix = importance_stars(weight) if include_stars else f"{weight:.2f}"
    return f"Quality — {suffix} — {QUALITY_UNIVERSAL_NOTE}"


HOW_TO_READ_PRIORITIES_MARKDOWN = """\
GearCity has several layers. **Final vehicle rating priorities** tell you what \
the completed vehicle needs to be good at. **Component priorities** translate \
those needs into chassis, engine, and gearbox focus areas. **Design sliders & \
testing focus** tells you which vehicle design sliders and testing areas support \
those final stats.

The in-game overview screen may show labels such as Handling for what the wiki \
formulas call Driveability. This tool uses Driveability as the formula-backed \
label for that final vehicle stat.
"""


DRIVEABILITY_HANDLING_NOTE = (
    "The GearCity wiki formulas use `Driveability` / `Rating_Drivability` for "
    "the final vehicle stat. Chassis steering/handling subcomponent values feed "
    "into this rating. Some in-game screens may display Handling, but this tool "
    "uses Driveability as the formula-backed label."
)

DEPENDABILITY_LAYER_NOTE = (
    "Component reliability/durability ratings help produce final vehicle "
    "dependability, but they are not the same stat. Overall Rating is also "
    "separate from dependability."
)

GEARBOX_COMFORT_NOTE = (
    "Gearbox Comfort Rating is influenced by shifting ease and gearbox smoothness "
    "variables in the formulas. Do not treat it as confirmed identical to a UI "
    "Smoothness label unless separately verified."
)

ENGINE_POWER_NOTE = (
    "Engine Power Rating is a separate formula rating. Horsepower and torque are "
    "specs that contribute to engine/vehicle behavior, but Power Rating should "
    "not be treated as cosmetic."
)


def list_verified_terminology_keys() -> list[tuple[str, str]]:
    """Return all terminology keys with specs or verification builders."""
    keys = set(TERMINOLOGY_SPECS.keys()) | set(VERIFICATION_BUILDERS.keys())
    return sorted(keys)


def list_terminology_entries(*, root: Path | None = None) -> list[TerminologyEntry]:
    """Return all verified terminology entries sorted for audit display."""
    return [
        get_verified_terminology_entry(component, internal_key, root=root)
        for component, internal_key in list_verified_terminology_keys()
    ]


def list_terminology_layers() -> tuple[TerminologyLayer, ...]:
    """Return rating layer concept definitions."""
    return TERMINOLOGY_LAYERS


def list_terminology_audit_rows(*, root: Path | None = None) -> list[dict[str, str]]:
    """Return terminology entries as dict rows for Streamlit audit tables."""
    return [
        {
            "component": entry.component,
            "internal key": entry.internal_key,
            "formula label": entry.formula_label,
            "observed UI label": entry.observed_game_label or "",
            "status": entry.status,
            "display label": entry.display_label,
            "layer": entry.layer,
            "evidence count": str(len(entry.evidence)),
            "explanation": entry.explanation,
        }
        for entry in list_terminology_entries(root=root)
    ]


def list_priority_audit_entries(*, root: Path | None = None) -> list[TerminologyEntry]:
    """Return priority-relevant verified mappings for audit display."""
    priority_keys = list(VERIFICATION_BUILDERS.keys()) + [
        ("vehicle", "quality"),
    ]
    return [
        get_verified_terminology_entry(component, key, root=root)
        for component, key in priority_keys
    ]


DEPENDABILITY_LAYERS_MARKDOWN = """\
Think of it as layers:

**Component-level**

- Engine Reliability Rating
- Chassis Durability Rating
- Gearbox Reliability Rating

**Final vehicle-level**

- Vehicle Dependability Rating

**Vehicle type table**

- Dependability Importance

**Summary**

- Overall Rating

Component reliability/durability ratings help produce final vehicle dependability, \
but they are not the same stat. Overall Rating is also separate from dependability.

Gearbox max torque mismatch can hurt quality/dependability even if the gearbox \
has a good reliability rating.
"""

TERMINOLOGY_AUDIT_CLI_HINT = (
    "Run `python -m gearcity_optimizer.cli terminology-audit --term Driveability "
    "--full` or `--term Handling --full` for source evidence and conclusions."
)
