"""Screenshot-validated UI labels for audit/debug only (not optimizer source)."""

from __future__ import annotations

ENGINE_SLIDER_LABELS: tuple[str, ...] = (
    "Bore",
    "Stroke",
    "Length",
    "Width",
    "Weight",
    "Revolutions",
    "Engine Torque",
    "Fuel Economy",
    "Material Quality",
    "Component Quality",
    "Technology",
    "Manufacturing Techniques",
    "Focus on Performance",
    "Focus on Fuel Economy",
    "Focus on Dependability",
    "Development Pace",
)

CHASSIS_SLIDER_LABELS: tuple[str, ...] = (
    "Wheelbase (Length)",
    "Track (Width)",
    "Frame Height",
    "Frame Weight",
    "Maximum Supported Engine Length",
    "Maximum Supported Engine Width",
    "Stability",
    "Ride Comfort",
    "Performance",
    "Braking",
    "Durability",
    "Design Performance",
    "Design Ride Control",
    "Design Strength",
    "Design Dependability",
    "Material Quality",
    "Component Quality",
    "Technology",
    "Manufacturing Techniques",
    "Development Pace",
)

GEARBOX_SLIDER_LABELS: tuple[str, ...] = (
    "Material Quality",
    "Component Quality",
    "Technology",
    "Manufacturing Techniques",
    "Performance Focus",
    "Fuel Economy",
    "Shifting Ease",
    "Gearbox Dependability",
    "Low End Gearing",
    "High End Gearing",
    "Maximum Torque Input",
    "Development Pace",
)

SCREENSHOT_LABELS_BY_SECTION = {
    "engine": ENGINE_SLIDER_LABELS,
    "chassis": CHASSIS_SLIDER_LABELS,
    "gearbox": GEARBOX_SLIDER_LABELS,
}


def screenshot_labels(section: str) -> tuple[str, ...]:
    """Return screenshot-validated labels for one section (audit only)."""
    return SCREENSHOT_LABELS_BY_SECTION[section.strip().lower()]
