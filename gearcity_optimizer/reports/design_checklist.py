"""Deterministic vehicle design checklists from vehicle type weights and priorities."""

from __future__ import annotations

from dataclasses import dataclass, field

from gearcity_optimizer.core.component_priorities import (
    calculate_component_priorities,
    enrich_priorities_for_display,
    format_stat_label,
    get_adjusted_vehicle_weights,
)
from gearcity_optimizer.core.component_models import ComponentPriority
from gearcity_optimizer.core.models import VehicleType
from gearcity_optimizer.core.terminology import (
    DESIGN_SLIDER_SECTION_TITLE,
    FINAL_VEHICLE_RATING_SECTION_TITLE,
    VEHICLE_TYPE_RATING_KEYS,
    format_final_vehicle_rating_label,
    format_final_vehicle_rating_line,
    format_quality_universal_line,
)

DEPENDABILITY_HEAVY_GUIDANCE = (
    "Final vehicle dependability matters for this vehicle type. Support it "
    "through reliable engine choices, durable chassis choices, reliable gearbox "
    "choices, dependability focus, material quality, and reliability testing."
)

CHASSIS_STAT_BULLETS: dict[str, str] = {
    "strength": (
        "Prioritize chassis strength, frame strength, braking support, "
        "and safety-related structure."
    ),
    "durability": (
        "Prioritize Chassis Durability Rating, but remember this is a "
        "component-level stat, not the final Vehicle Dependability Rating "
        "by itself."
    ),
    "comfort": (
        "Prioritize Comfort Rating and control, especially for luxury or "
        "family-oriented models."
    ),
    "performance": (
        "Prioritize chassis performance, control, and suspension performance."
    ),
    "low_weight": (
        "Keep chassis weight under control because fuel/performance matters "
        "for this vehicle type."
    ),
    "cargo_space": (
        "Favor cargo-supporting dimensions and utility-focused design."
    ),
    "engine_fit_room": (
        "Make sure engine bay width/length can fit the engine you plan to use."
    ),
}

ENGINE_STAT_BULLETS: dict[str, str] = {
    "fuel_economy": (
        "Prioritize fuel economy sliders, efficient displacement, and "
        "efficient fuel system choices."
    ),
    "torque": (
        "Prioritize torque enough to move the vehicle well, especially for "
        "cargo/power-focused types."
    ),
    "horsepower": (
        "Prioritize horsepower and performance-focused tuning."
    ),
    "reliability": (
        "Prioritize Engine Reliability Rating when final vehicle dependability "
        "matters."
    ),
    "smoothness": (
        "Prioritize engine smoothness for luxury/driveability-sensitive vehicles."
    ),
    "compact_size": (
        "Keep engine size reasonable so it fits the chassis and preserves "
        "cargo/packaging."
    ),
    "low_weight": (
        "Keep engine weight reasonable when fuel economy or packaging matters."
    ),
}

GEARBOX_STAT_BULLETS: dict[str, str] = {
    "max_torque": (
        "Make sure max torque supports engine torque; torque mismatch can hurt "
        "quality/dependability."
    ),
    "fuel_economy": (
        "Prioritize fuel economy gearing and efficient gearbox design."
    ),
    "reliability": (
        "Prioritize Gearbox Reliability Rating and make sure max torque supports "
        "engine torque; torque mismatch can hurt quality/dependability."
    ),
    "performance": (
        "Prioritize performance gearing for acceleration/top speed."
    ),
    "comfort": (
        "Prioritize Gearbox Comfort Rating, influenced by shifting ease/smoothness "
        "variables."
    ),
    "low_weight": (
        "Keep gearbox weight reasonable when fuel economy matters."
    ),
}

VEHICLE_DESIGN_BULLETS: dict[str, str] = {
    "safety_focus": "Raise Design Focus: Safety.",
    "dependability_focus": (
        "Raise Design Focus: Dependability (supports final vehicle dependability)."
    ),
    "cargo_focus": "Raise Design Focus: Cargo.",
    "luxury_focus": "Raise Design Focus: Luxury.",
    "style_focus": "Raise Design Focus: Style (secondary luxury/performance cue).",
    "material_quality": (
        "Use decent material quality; quality matters strongly in buyer rating."
    ),
    "testing_reliability": "Invest in reliability testing.",
    "testing_fuel": "Invest in fuel economy testing.",
    "testing_performance": "Invest in performance testing.",
    "testing_utility": "Invest in utility testing.",
}

COMPONENT_HIGH_PRIORITY_THRESHOLD = 55.0
TOP_COMPONENT_STATS = 4


@dataclass
class DesignChecklistSection:
    """One section of a design checklist report."""

    title: str
    bullets: list[str]


@dataclass
class DesignChecklistReport:
    """Full design checklist for a vehicle type and year."""

    vehicle_type: str
    year: int
    final_stat_priorities: list[tuple[str, float]]
    sections: list[DesignChecklistSection]
    warnings: list[str]
    markdown: str


def weight_level(weight: float) -> str:
    """Map an importance weight to a human-readable level."""
    if weight >= 0.75:
        return "critical"
    if weight >= 0.60:
        return "high"
    if weight >= 0.40:
        return "medium"
    if weight >= 0.20:
        return "low"
    return "minor"


def _weight(w: dict[str, float], key: str) -> float:
    return w.get(key, 0.0)


def _is_component_stat_high(item: ComponentPriority, rank: int) -> bool:
    """Return True when a component stat priority is meaningfully high."""
    return rank <= TOP_COMPONENT_STATS or item.priority >= COMPONENT_HIGH_PRIORITY_THRESHOLD


def _top_final_stat_priorities(
    weights: dict[str, float],
) -> list[tuple[str, float]]:
    """Sort vehicle-type final stats by adjusted importance weight."""
    return sorted(
        ((name, weights[name]) for name in VEHICLE_TYPE_RATING_KEYS if name in weights),
        key=lambda item: item[1],
        reverse=True,
    )


def _final_stat_label(stat: str) -> str:
    """Return a GearCity-aligned label for a final vehicle stat."""
    return format_final_vehicle_rating_label(stat)


def format_final_vehicle_rating_priorities(
    weights: dict[str, float],
    *,
    include_stars: bool = False,
) -> list[str]:
    """Build display lines for final vehicle rating priorities plus quality note."""
    lines: list[str] = []
    for index, (stat, value) in enumerate(_top_final_stat_priorities(weights), start=1):
        lines.append(
            format_final_vehicle_rating_line(
                stat,
                value,
                include_stars=include_stars,
                numbered=index,
            )
        )
    if "quality" in weights:
        lines.append(format_quality_universal_line(weights["quality"], include_stars=include_stars))
    return lines


def _format_final_priority_summary(priorities: list[tuple[str, float]]) -> list[str]:
    """Build a short numbered summary of the most important final stats."""
    lines: list[str] = []
    for index, (stat, value) in enumerate(priorities[:5], start=1):
        label = _final_stat_label(stat)
        level = weight_level(value)
        lines.append(f"{index}. {label} ({level}, {value:.2f})")

    moderate = [
        _final_stat_label(stat)
        for stat, value in priorities[5:8]
        if value >= 0.35
    ]
    if moderate:
        lines.append(
            f"{len(lines) + 1}. {', '.join(moderate)} moderate"
        )
    return lines


def format_final_vehicle_rating_priorities_from_vehicle_type(
    vehicle_type: VehicleType,
    *,
    include_stars: bool = False,
) -> list[str]:
    """Build final vehicle rating priority lines for a vehicle type."""
    weights = get_adjusted_vehicle_weights(vehicle_type)
    return format_final_vehicle_rating_priorities(weights, include_stars=include_stars)


def _chassis_bullets(
    chassis_priorities: list[ComponentPriority],
    weights: dict[str, float],
) -> list[str]:
    """Build chassis design checklist bullets."""
    bullets: list[str] = []
    seen: set[str] = set()

    for rank, item in enumerate(chassis_priorities, start=1):
        if not _is_component_stat_high(item, rank):
            continue
        text = CHASSIS_STAT_BULLETS.get(item.stat)
        if text and text not in seen:
            bullets.append(text)
            seen.add(text)

    if _weight(weights, "fuel") >= 0.60:
        bullets.append("Avoid unnecessary chassis weight.")
    if _weight(weights, "safety") >= 0.60:
        bullets.append(
            "Do not sacrifice strength/braking just to save cost."
        )
    if _weight(weights, "performance") <= 0.20:
        bullets.append("Do not overspend on pure chassis performance.")

    return bullets


def _engine_bullets(
    engine_priorities: list[ComponentPriority],
    weights: dict[str, float],
) -> list[str]:
    """Build engine design checklist bullets."""
    bullets: list[str] = []
    seen: set[str] = set()

    for rank, item in enumerate(engine_priorities, start=1):
        if not _is_component_stat_high(item, rank):
            continue
        text = ENGINE_STAT_BULLETS.get(item.stat)
        if text and text not in seen:
            bullets.append(text)
            seen.add(text)

    if _weight(weights, "fuel") >= 0.60 and _weight(weights, "performance") <= 0.40:
        bullets.append(
            "Do not chase horsepower at the expense of fuel economy."
        )
    if _weight(weights, "power") >= 0.70 or _weight(weights, "cargo") >= 0.70:
        bullets.append("Make sure torque is strong enough for utility use.")
    if _weight(weights, "luxury") >= 0.70:
        bullets.append("Engine smoothness matters a lot.")

    return bullets


def _gearbox_bullets(
    gearbox_priorities: list[ComponentPriority],
    weights: dict[str, float],
) -> list[str]:
    """Build gearbox design checklist bullets."""
    bullets: list[str] = []
    seen: set[str] = set()

    for rank, item in enumerate(gearbox_priorities, start=1):
        if not _is_component_stat_high(item, rank):
            continue
        text = GEARBOX_STAT_BULLETS.get(item.stat)
        if text and text not in seen:
            bullets.append(text)
            seen.add(text)

    bullets.append(
        "Check gearbox max torque against engine torque before finalizing the vehicle."
    )

    if _weight(weights, "fuel") >= 0.60:
        bullets.append(
            "Avoid performance gearing that damages fuel economy unless the "
            "model needs it."
        )
    if _weight(weights, "dependability") >= 0.60:
        bullets.append("Avoid unnecessary gearbox complexity.")

    return bullets


def _vehicle_design_bullets(
    design_priorities: list[ComponentPriority],
    weights: dict[str, float],
) -> list[str]:
    """Build vehicle body/design/testing checklist bullets."""
    bullets: list[str] = []
    seen: set[str] = set()

    if _weight(weights, "dependability") >= 0.60:
        bullets.append(DEPENDABILITY_HEAVY_GUIDANCE)
        seen.add(DEPENDABILITY_HEAVY_GUIDANCE)

    for rank, item in enumerate(design_priorities, start=1):
        if not _is_component_stat_high(item, rank):
            continue
        text = VEHICLE_DESIGN_BULLETS.get(item.stat)
        if text and text not in seen:
            bullets.append(text)
            seen.add(text)

    bullets.append("Do not max every slider; slider costs rise quickly.")
    bullets.append(
        "Focus high sliders on the vehicle type's important stats."
    )
    return bullets


def _things_to_avoid(weights: dict[str, float]) -> list[str]:
    """Build caution bullets for the checklist."""
    warnings: list[str] = [
        "Gearbox max torque lower than engine torque.",
    ]

    if _weight(weights, "performance") <= 0.45:
        warnings.append(
            "Too much performance cost for a vehicle type that does not "
            "value performance highly."
        )
    if _weight(weights, "fuel") >= 0.55:
        warnings.append(
            "Heavy chassis choices when fuel economy is already weak or important."
        )
    if _weight(weights, "luxury") < 0.55:
        warnings.append(
            "Luxury overbuilding unless targeting wealthier buyers."
        )
    if _weight(weights, "cargo") >= 0.70:
        warnings.append(
            "Underbuilding torque or gearbox max torque for utility workloads."
        )
    if _weight(weights, "safety") >= 0.60:
        warnings.append(
            "Cutting chassis strength or braking focus to save money."
        )

    return warnings


def format_checklist_final_stat_label(stat: str) -> str:
    """Return a layer-aware label for a final vehicle stat in checklists."""
    return _final_stat_label(stat)


def render_design_checklist_markdown(report: DesignChecklistReport) -> str:
    """Render a design checklist report as Markdown."""
    lines = [
        f"# {report.vehicle_type} Design Checklist, {report.year}",
        "",
        f"Selected vehicle type: **{report.vehicle_type}**",
        "",
        f"## {FINAL_VEHICLE_RATING_SECTION_TITLE}",
        "",
    ]
    for line in format_final_vehicle_rating_priorities(_weights_from_report(report)):
        lines.append(line)
    lines.append("")

    for section in report.sections:
        lines.append(f"## {section.title}")
        lines.append("")
        for bullet in section.bullets:
            lines.append(f"- {bullet}")
        lines.append("")

    if report.warnings:
        lines.append("## Things to avoid")
        lines.append("")
        for warning in report.warnings:
            lines.append(f"- {warning}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _weights_from_report(report: DesignChecklistReport) -> dict[str, float]:
    """Reconstruct weight dict from report final priorities plus quality default."""
    from gearcity_optimizer.core.component_priorities import QUALITY_BACKGROUND_WEIGHT

    weights = dict(report.final_stat_priorities)
    weights["quality"] = QUALITY_BACKGROUND_WEIGHT
    return weights


def build_design_checklist(
    vehicle_type: VehicleType,
    year: int = 1901,
) -> DesignChecklistReport:
    """Build a deterministic design checklist for a vehicle type."""
    weights = get_adjusted_vehicle_weights(vehicle_type)
    priorities = calculate_component_priorities(vehicle_type)
    final_priorities = _top_final_stat_priorities(weights)

    sections = [
        DesignChecklistSection(
            title="Chassis focus",
            bullets=_chassis_bullets(priorities["chassis"], weights),
        ),
        DesignChecklistSection(
            title="Engine focus",
            bullets=_engine_bullets(priorities["engine"], weights),
        ),
        DesignChecklistSection(
            title="Gearbox focus",
            bullets=_gearbox_bullets(priorities["gearbox"], weights),
        ),
        DesignChecklistSection(
            title=DESIGN_SLIDER_SECTION_TITLE,
            bullets=_vehicle_design_bullets(priorities["vehicle_design"], weights),
        ),
    ]

    warnings = _things_to_avoid(weights)
    report = DesignChecklistReport(
        vehicle_type=vehicle_type.name,
        year=year,
        final_stat_priorities=final_priorities,
        sections=sections,
        warnings=warnings,
        markdown="",
    )
    report.markdown = render_design_checklist_markdown(report)
    return report


def format_checklist_for_cli(report: DesignChecklistReport) -> str:
    """Render checklist as plain text for terminal output."""
    lines = [
        f"{report.vehicle_type} Design Checklist, {report.year}",
        "",
        f"Selected vehicle type: {report.vehicle_type}",
        "",
        f"{FINAL_VEHICLE_RATING_SECTION_TITLE}:",
        "",
    ]
    lines.extend(format_final_vehicle_rating_priorities(_weights_from_report(report)))
    lines.append("")

    for section in report.sections:
        lines.append(f"{section.title}:")
        for bullet in section.bullets:
            lines.append(f"  * {bullet}")
        lines.append("")

    lines.append("Things to avoid:")
    for warning in report.warnings:
        lines.append(f"  * {warning}")

    return "\n".join(lines)


def format_priority_table(
    priorities: list[ComponentPriority],
    component: str,
) -> list[str]:
    """Format ranked component priorities for display."""
    display_priorities = enrich_priorities_for_display(component, priorities)
    lines: list[str] = []
    for index, item in enumerate(display_priorities, start=1):
        label = format_stat_label(component, item.stat)
        lines.append(f"  {index}. {label} ({item.priority:.1f})")
    return lines
