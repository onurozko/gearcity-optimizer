"""Deterministic vehicle design checklists from vehicle type weights and priorities."""

from __future__ import annotations

from dataclasses import dataclass, field

from gearcity_optimizer.core.component_priorities import (
    RATING_NAMES,
    calculate_component_priorities,
    format_stat_label,
    get_adjusted_vehicle_weights,
)
from gearcity_optimizer.core.component_models import ComponentPriority
from gearcity_optimizer.core.models import VehicleType

FINAL_STAT_LABELS: dict[str, str] = {
    "performance": "Performance",
    "drivability": "Drivability",
    "luxury": "Luxury",
    "safety": "Safety",
    "fuel": "Fuel economy",
    "power": "Power / torque",
    "cargo": "Cargo / utility",
    "dependability": "Dependability",
    "quality": "Quality",
}

CHASSIS_STAT_BULLETS: dict[str, str] = {
    "strength": (
        "Prioritize chassis strength, frame strength, braking support, "
        "and safety-related structure."
    ),
    "durability": (
        "Prioritize durability and dependable suspension/frame choices."
    ),
    "comfort": (
        "Prioritize comfort and control, especially for luxury or "
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
        "Prioritize reliability/dependability and avoid overly complex "
        "engine choices."
    ),
    "smoothness": (
        "Prioritize engine smoothness for luxury/drivability-sensitive vehicles."
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
        "Gearbox max torque must exceed engine torque; otherwise "
        "quality/dependability can suffer."
    ),
    "fuel_economy": (
        "Prioritize fuel economy gearing and efficient gearbox design."
    ),
    "reliability": (
        "Prioritize gearbox reliability and dependable/simple design."
    ),
    "performance": (
        "Prioritize performance gearing for acceleration/top speed."
    ),
    "comfort": (
        "Prioritize shifting ease/comfort for luxury or drivability-sensitive "
        "models."
    ),
    "low_weight": (
        "Keep gearbox weight reasonable when fuel economy matters."
    ),
}

VEHICLE_DESIGN_BULLETS: dict[str, str] = {
    "safety_focus": "Raise Design Focus: Safety.",
    "dependability_focus": "Raise Design Focus: Dependability.",
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
    """Sort final vehicle stats by adjusted importance weight."""
    return sorted(
        ((name, weights[name]) for name in RATING_NAMES if name in weights),
        key=lambda item: item[1],
        reverse=True,
    )


def _format_final_priority_summary(priorities: list[tuple[str, float]]) -> list[str]:
    """Build a short numbered summary of the most important final stats."""
    lines: list[str] = []
    for index, (stat, value) in enumerate(priorities[:5], start=1):
        label = FINAL_STAT_LABELS.get(stat, stat.replace("_", " ").title())
        level = weight_level(value)
        lines.append(f"{index}. {label} ({level}, {value:.2f})")

    moderate = [
        FINAL_STAT_LABELS.get(stat, stat)
        for stat, value in priorities[5:8]
        if value >= 0.35
    ]
    if moderate:
        lines.append(
            f"{len(lines) + 1}. {', '.join(moderate)} moderate"
        )
    return lines


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
) -> list[str]:
    """Build vehicle body/design/testing checklist bullets."""
    bullets: list[str] = []
    seen: set[str] = set()

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


def render_design_checklist_markdown(report: DesignChecklistReport) -> str:
    """Render a design checklist report as Markdown."""
    lines = [
        f"# {report.vehicle_type} Design Checklist, {report.year}",
        "",
        "## Most important final vehicle stats",
        "",
    ]
    for line in _format_final_priority_summary(report.final_stat_priorities):
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
            title="Vehicle body / design focus",
            bullets=_vehicle_design_bullets(priorities["vehicle_design"]),
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
        "Most important final vehicle stats:",
        "",
    ]
    lines.extend(_format_final_priority_summary(report.final_stat_priorities))
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
    lines: list[str] = []
    for index, item in enumerate(priorities, start=1):
        label = format_stat_label(component, item.stat)
        lines.append(f"  {index}. {label} ({item.priority:.1f})")
    return lines
