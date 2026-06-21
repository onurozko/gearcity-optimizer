"""Registry of real GearCity controllable design sliders and inputs."""

from __future__ import annotations

from dataclasses import dataclass

from gearcity_optimizer.formulas.chassis_formula import SLIDER_FIELDS as CHASSIS_SLIDER_FIELDS
from gearcity_optimizer.formulas.chassis_formula import SUBCOMPONENT_FIELDS as CHASSIS_SUBCOMPONENT_FIELDS
from gearcity_optimizer.formulas.engine_formula import SLIDER_FIELDS as ENGINE_SLIDER_FIELDS
from gearcity_optimizer.formulas.engine_formula import SUBCOMPONENT_FIELDS as ENGINE_SUBCOMPONENT_FIELDS
from gearcity_optimizer.formulas.gearbox_formula import SLIDER_FIELDS as GEARBOX_SLIDER_FIELDS

# Keys that are formula outputs, not user-settable controls.
OUTPUT_STAT_KEYS = frozenset(
    {
        "torque",
        "horsepower",
        "hp",
        "fuel_economy",
        "fuel_economy_rating",
        "power_rating",
        "performance_rating",
        "reliability_rating",
        "smoothness_rating",
        "comfort_rating",
        "strength_rating",
        "durability_rating",
        "overall_rating",
        "cargo",
        "cargo_space",
        "dependability",
        "dependability_rating",
        "quality",
        "overall",
        "max_torque",
        "max_torque_support",
        "drivability",
        "luxury",
        "safety",
        "performance",
        "fuel",
        "power",
        "chassis_length",
        "chassis_width",
        "chassis_weight",
        "max_engine_length",
        "max_engine_width",
        "weight",
        "width",
        "length",
        "design_requirements",
        "manufacturing_requirements",
    }
)

# Sub-component stat proxies belong to Components.xml choices, not direct sliders.
SUBCOMPONENT_PROXY_FIELDS = frozenset(CHASSIS_SUBCOMPONENT_FIELDS) | frozenset(
    ENGINE_SUBCOMPONENT_FIELDS
) | frozenset(
    {
        "subcomponent_weight",
        "subcomponent_complexity",
        "subcomponent_smoothness",
        "subcomponent_ease",
        "subcomponent_fuel_rating",
        "subcomponent_performance_rating",
        "subcomponent_unit_costs",
        "subcomponent_design_costs",
    }
)

CHASSIS_SLIDER_META: dict[str, dict[str, object]] = {
    "fd_length": {
        "label": "Frame design: length",
        "formula_variable": "Slider_FD_Length",
        "affects_outputs": ["chassis_length", "cargo_space", "max_engine_length"],
    },
    "fd_width": {
        "label": "Frame design: width",
        "formula_variable": "Slider_FD_Width",
        "affects_outputs": ["chassis_width", "max_engine_width"],
    },
    "fd_height": {
        "label": "Frame design: height",
        "formula_variable": "Slider_FD_Height",
        "affects_outputs": ["chassis_weight", "cargo_space"],
    },
    "fd_weight": {
        "label": "Frame design: weight focus",
        "formula_variable": "Slider_FD_Weight",
        "affects_outputs": ["chassis_weight", "fuel_economy"],
    },
    "fd_engine_width": {
        "label": "Frame design: engine bay width",
        "formula_variable": "Slider_FD_ENG_Width",
        "affects_outputs": ["max_engine_width"],
    },
    "fd_engine_length": {
        "label": "Frame design: engine bay length",
        "formula_variable": "Slider_FD_ENG_Length",
        "affects_outputs": ["max_engine_length"],
    },
    "sus_stability": {
        "label": "Suspension: stability",
        "formula_variable": "Slider_SUS_Stability",
        "affects_outputs": ["comfort_rating", "performance_rating"],
    },
    "sus_comfort": {
        "label": "Suspension: comfort",
        "formula_variable": "Slider_SUS_Comfort",
        "affects_outputs": ["comfort_rating", "drivability"],
    },
    "sus_performance": {
        "label": "Suspension: performance",
        "formula_variable": "Slider_SUS_Performance",
        "affects_outputs": ["performance_rating"],
    },
    "sus_braking": {
        "label": "Suspension: braking",
        "formula_variable": "Slider_SUS_Braking",
        "affects_outputs": ["performance_rating", "safety"],
    },
    "sus_durability": {
        "label": "Suspension: durability",
        "formula_variable": "Slider_SUS_Durability",
        "affects_outputs": ["durability_rating", "dependability"],
    },
    "design_performance": {
        "label": "Chassis design focus: performance",
        "formula_variable": "Slider_DE_Performance",
        "affects_outputs": ["performance_rating"],
    },
    "design_control": {
        "label": "Chassis design focus: control",
        "formula_variable": "Slider_DE_Control",
        "affects_outputs": ["drivability", "comfort_rating"],
    },
    "design_strength": {
        "label": "Chassis design focus: strength",
        "formula_variable": "Slider_DE_Str",
        "affects_outputs": ["strength_rating", "safety"],
    },
    "design_dependability": {
        "label": "Chassis design focus: dependability",
        "formula_variable": "Slider_DE_Depend",
        "affects_outputs": ["durability_rating", "dependability"],
    },
    "design_pace": {
        "label": "Chassis design pace",
        "formula_variable": "Slider_DesignPace",
        "affects_outputs": ["design_requirements", "manufacturing_requirements"],
    },
    "tech_materials": {
        "label": "Chassis technology: materials",
        "formula_variable": "Slider_TECH_Materials",
        "affects_outputs": ["strength_rating", "durability_rating", "cost"],
    },
    "tech_components": {
        "label": "Chassis technology: components",
        "formula_variable": "Slider_TECH_Compoenents",
        "affects_outputs": ["performance_rating", "dependability"],
    },
    "tech_techniques": {
        "label": "Chassis technology: techniques",
        "formula_variable": "Slider_TECH_Techniques",
        "affects_outputs": ["performance_rating", "comfort_rating"],
    },
    "tech_technology": {
        "label": "Chassis technology: technology",
        "formula_variable": "Slider_TECH_Tech",
        "affects_outputs": ["performance_rating", "safety"],
    },
}

ENGINE_SLIDER_META: dict[str, dict[str, object]] = {
    "design_performance": {
        "label": "Engine design focus: performance",
        "formula_variable": "Slider_DesignFocus_Performance",
        "affects_outputs": ["torque", "horsepower", "power_rating"],
    },
    "design_fuel_economy": {
        "label": "Engine design focus: fuel economy",
        "formula_variable": "Slider_DesignFocus_FuelEconomy",
        "affects_outputs": ["fuel_economy", "fuel_economy_rating"],
    },
    "design_dependability": {
        "label": "Engine design focus: reliability",
        "formula_variable": "Slider_DesignFocus_Dependability",
        "affects_outputs": ["reliability_rating", "dependability"],
    },
    "design_smoothness": {
        "label": "Engine design focus: smoothness",
        "formula_variable": "Slider_DesignFocus_Smoothness",
        "affects_outputs": ["smoothness_rating", "luxury", "drivability"],
    },
    "design_pace": {
        "label": "Engine design pace",
        "formula_variable": "Slider_DesignFocus_DesignPace",
        "affects_outputs": ["design_requirements", "manufacturing_requirements"],
    },
    "tech_materials": {
        "label": "Engine technology: materials",
        "formula_variable": "Slider_Technology_Materials",
        "affects_outputs": ["reliability_rating", "weight"],
    },
    "tech_components": {
        "label": "Engine technology: components",
        "formula_variable": "Slider_Technology_Components",
        "affects_outputs": ["torque", "reliability_rating"],
    },
    "tech_techniques": {
        "label": "Engine technology: techniques",
        "formula_variable": "Slider_Technology_Techniques",
        "affects_outputs": ["fuel_economy", "performance_rating"],
    },
    "tech_technology": {
        "label": "Engine technology: technology",
        "formula_variable": "Slider_Technology_Technology",
        "affects_outputs": ["horsepower", "reliability_rating"],
    },
    "fuel_system_quality": {
        "label": "Fuel system quality focus",
        "formula_variable": "Slider_FuelSystemQuality",
        "affects_outputs": ["fuel_economy", "reliability_rating"],
        "confidence": "likely",
    },
    "aspiration_quality": {
        "label": "Aspiration / induction quality focus",
        "formula_variable": "Slider_AspirationQuality",
        "affects_outputs": ["horsepower", "torque", "fuel_economy"],
        "confidence": "likely",
    },
}

ENGINE_DIMENSIONAL_META: dict[str, dict[str, object]] = {
    "bore": {
        "label": "Bore (mm)",
        "formula_variable": "Slider_Layout_Bore",
        "min_value": 50.0,
        "max_value": 150.0,
        "default_value": 75.0,
        "step": 1.0,
        "affects_outputs": ["torque", "horsepower", "displacement", "weight"],
        "confidence": "confirmed",
    },
    "stroke": {
        "label": "Stroke (mm)",
        "formula_variable": "Slider_Layout_Stroke",
        "min_value": 50.0,
        "max_value": 150.0,
        "default_value": 75.0,
        "step": 1.0,
        "affects_outputs": ["torque", "horsepower", "displacement", "fuel_economy"],
        "confidence": "confirmed",
    },
    "displacement": {
        "label": "Displacement (cc)",
        "formula_variable": "Layout_Displacement",
        "min_value": 200.0,
        "max_value": 8000.0,
        "default_value": 1200.0,
        "step": 50.0,
        "affects_outputs": ["torque", "horsepower", "fuel_economy", "weight"],
        "confidence": "confirmed",
        "notes": "Used when bore/stroke are not supplied separately.",
    },
    "cylinders": {
        "label": "Cylinder count",
        "formula_variable": "Layout_CylinderCount",
        "min_value": 1.0,
        "max_value": 18.0,
        "default_value": 4.0,
        "step": 1.0,
        "affects_outputs": ["torque", "horsepower", "smoothness_rating"],
        "confidence": "confirmed",
    },
}

ENGINE_BOOLEAN_META: dict[str, dict[str, object]] = {
    "is_supercharged": {
        "label": "Supercharged",
        "formula_variable": "ForcedInduction_Supercharged",
        "min_value": 0.0,
        "max_value": 1.0,
        "default_value": 0.0,
        "step": 1.0,
        "affects_outputs": ["horsepower", "torque", "fuel_economy"],
        "confidence": "confirmed",
    },
    "is_turbocharged": {
        "label": "Turbocharged",
        "formula_variable": "ForcedInduction_Turbocharged",
        "min_value": 0.0,
        "max_value": 1.0,
        "default_value": 0.0,
        "step": 1.0,
        "affects_outputs": ["horsepower", "torque", "fuel_economy"],
        "confidence": "confirmed",
    },
    "has_fuel_injection": {
        "label": "Fuel injection",
        "formula_variable": "FuelInjection",
        "min_value": 0.0,
        "max_value": 1.0,
        "default_value": 0.0,
        "step": 1.0,
        "affects_outputs": ["fuel_economy", "reliability_rating"],
        "confidence": "likely",
    },
    "has_overhead_cam": {
        "label": "Overhead cam",
        "formula_variable": "OverheadCam",
        "min_value": 0.0,
        "max_value": 1.0,
        "default_value": 0.0,
        "step": 1.0,
        "affects_outputs": ["horsepower", "smoothness_rating"],
        "confidence": "likely",
    },
}

GEARBOX_SLIDER_META: dict[str, dict[str, object]] = {
    "low_gear_ratio": {
        "label": "Low gear ratio",
        "formula_variable": "Slider_GearRatio_Low",
        "affects_outputs": ["max_torque_support", "performance_rating"],
    },
    "high_gear_ratio": {
        "label": "High gear ratio",
        "formula_variable": "Slider_GearRatio_High",
        "affects_outputs": ["fuel_economy", "performance_rating"],
    },
    "torque_max_input": {
        "label": "Max torque input (design)",
        "formula_variable": "Slider_TorqueMaxInput",
        "affects_outputs": ["max_torque_support", "reliability_rating"],
    },
    "design_ease": {
        "label": "Gearbox design focus: ease",
        "formula_variable": "Slider_DesignFocus_Ease",
        "affects_outputs": ["manufacturing_requirements", "cost"],
    },
    "design_dependability": {
        "label": "Gearbox design focus: dependability",
        "formula_variable": "Slider_DesignFocus_Dependability",
        "affects_outputs": ["reliability_rating", "dependability"],
    },
    "design_fuel_economy": {
        "label": "Gearbox design focus: fuel economy",
        "formula_variable": "Slider_DesignFocus_FuelEconomy",
        "affects_outputs": ["fuel_economy", "fuel_economy_rating"],
    },
    "design_performance": {
        "label": "Gearbox design focus: performance",
        "formula_variable": "Slider_DesignFocus_Performance",
        "affects_outputs": ["performance_rating", "power"],
    },
    "tech_material": {
        "label": "Gearbox technology: material",
        "formula_variable": "Slider_Technology_Material",
        "affects_outputs": ["weight", "reliability_rating"],
    },
    "tech_components": {
        "label": "Gearbox technology: components",
        "formula_variable": "Slider_Technology_Components",
        "affects_outputs": ["max_torque_support", "performance_rating"],
    },
    "tech_technology": {
        "label": "Gearbox technology: technology",
        "formula_variable": "Slider_Technology_Technology",
        "affects_outputs": ["performance_rating", "comfort_rating"],
    },
    "tech_techniques": {
        "label": "Gearbox technology: techniques",
        "formula_variable": "Slider_Technology_Techniques",
        "affects_outputs": ["fuel_economy", "comfort_rating"],
    },
}

GEARBOX_DISCRETE_META: dict[str, dict[str, object]] = {
    "number_of_gears": {
        "label": "Number of gears",
        "formula_variable": "GearCount",
        "min_value": 1.0,
        "max_value": 8.0,
        "default_value": 3.0,
        "step": 1.0,
        "affects_outputs": ["fuel_economy", "performance_rating", "comfort_rating"],
        "confidence": "confirmed",
    },
    "has_limited_slip": {
        "label": "Limited slip differential",
        "formula_variable": "HasLimitedSlip",
        "min_value": 0.0,
        "max_value": 1.0,
        "default_value": 0.0,
        "step": 1.0,
        "affects_outputs": ["performance_rating", "drivability"],
        "confidence": "confirmed",
    },
    "has_overdrive": {
        "label": "Overdrive",
        "formula_variable": "HasOverdrive",
        "min_value": 0.0,
        "max_value": 1.0,
        "default_value": 0.0,
        "step": 1.0,
        "affects_outputs": ["fuel_economy"],
        "confidence": "confirmed",
    },
    "has_transaxle": {
        "label": "Transaxle",
        "formula_variable": "HasTransaxle",
        "min_value": 0.0,
        "max_value": 1.0,
        "default_value": 0.0,
        "step": 1.0,
        "affects_outputs": ["weight", "packaging"],
        "confidence": "confirmed",
    },
    "has_reverse": {
        "label": "Reverse gear",
        "formula_variable": "HasReverse",
        "min_value": 0.0,
        "max_value": 1.0,
        "default_value": 1.0,
        "step": 1.0,
        "affects_outputs": ["utility"],
        "confidence": "confirmed",
    },
}

VEHICLE_DESIGN_META: dict[str, dict[str, object]] = {
    "safety_focus": {
        "label": "Design focus: safety",
        "formula_variable": "Slider_Vehicle_SafetyFocus",
        "section": "vehicle",
        "affects_outputs": ["safety", "dependability"],
        "confidence": "likely",
    },
    "dependability_focus": {
        "label": "Design focus: dependability",
        "formula_variable": "Slider_Vehicle_DependabilityFocus",
        "section": "vehicle",
        "affects_outputs": ["dependability", "quality"],
        "confidence": "likely",
    },
    "cargo_focus": {
        "label": "Design focus: cargo",
        "formula_variable": "Slider_Vehicle_CargoFocus",
        "section": "vehicle",
        "affects_outputs": ["cargo"],
        "confidence": "likely",
    },
    "luxury_focus": {
        "label": "Design focus: luxury",
        "formula_variable": "Slider_Vehicle_LuxuryFocus",
        "section": "vehicle",
        "affects_outputs": ["luxury", "quality"],
        "confidence": "likely",
    },
    "style_focus": {
        "label": "Design focus: style",
        "formula_variable": "Slider_Vehicle_StyleFocus",
        "section": "vehicle",
        "affects_outputs": ["luxury", "performance"],
        "confidence": "likely",
    },
    "material_quality": {
        "label": "Materials: material quality",
        "formula_variable": "Slider_Vehicle_MaterialQuality",
        "section": "vehicle",
        "affects_outputs": ["quality", "luxury", "safety"],
        "confidence": "likely",
    },
    "testing_reliability": {
        "label": "Testing: reliability",
        "formula_variable": "Slider_Testing_Reliability",
        "section": "testing",
        "affects_outputs": ["dependability", "quality"],
        "confidence": "likely",
    },
    "testing_fuel": {
        "label": "Testing: fuel economy",
        "formula_variable": "Slider_Testing_FuelEconomy",
        "section": "testing",
        "affects_outputs": ["fuel", "fuel_economy"],
        "confidence": "likely",
    },
    "testing_performance": {
        "label": "Testing: performance",
        "formula_variable": "Slider_Testing_Performance",
        "section": "testing",
        "affects_outputs": ["performance", "drivability"],
        "confidence": "likely",
    },
    "testing_utility": {
        "label": "Testing: utility",
        "formula_variable": "Slider_Testing_Utility",
        "section": "testing",
        "affects_outputs": ["cargo", "dependability"],
        "confidence": "likely",
    },
}


@dataclass(frozen=True)
class RealSlider:
    """One controllable GearCity design slider or input."""

    key: str
    label: str
    section: str
    field_name: str
    formula_variable: str | None
    min_value: float
    max_value: float
    default_value: float
    step: float
    affects_outputs: list[str]
    source: str
    confidence: str
    notes: str


def _registry_key(section: str, field_name: str) -> str:
    return f"{section}.{field_name}"


def _build_normalized_slider(
    field_name: str,
    section: str,
    meta: dict[str, object],
    *,
    source: str,
) -> RealSlider:
    return RealSlider(
        key=_registry_key(section, field_name),
        label=str(meta["label"]),
        section=str(meta.get("section", section)),
        field_name=field_name,
        formula_variable=str(meta.get("formula_variable")) if meta.get("formula_variable") else None,
        min_value=0.0,
        max_value=1.0,
        default_value=0.5,
        step=0.01,
        affects_outputs=[str(item) for item in meta.get("affects_outputs", [])],
        source=source,
        confidence=str(meta.get("confidence", "confirmed")),
        notes=str(meta.get("notes", "")),
    )


def _build_ranged_slider(
    field_name: str,
    section: str,
    meta: dict[str, object],
    *,
    source: str,
) -> RealSlider:
    return RealSlider(
        key=_registry_key(section, field_name),
        label=str(meta["label"]),
        section=str(meta.get("section", section)),
        field_name=field_name,
        formula_variable=str(meta.get("formula_variable")) if meta.get("formula_variable") else None,
        min_value=float(meta.get("min_value", 0.0)),
        max_value=float(meta.get("max_value", 1.0)),
        default_value=float(meta.get("default_value", 0.5)),
        step=float(meta.get("step", 1.0)),
        affects_outputs=[str(item) for item in meta.get("affects_outputs", [])],
        source=source,
        confidence=str(meta.get("confidence", "confirmed")),
        notes=str(meta.get("notes", "")),
    )


def _build_registry() -> tuple[RealSlider, ...]:
    sliders: list[RealSlider] = []

    for key in CHASSIS_SLIDER_FIELDS:
        meta = CHASSIS_SLIDER_META.get(key, {"label": key.replace("_", " ").title()})
        sliders.append(
            _build_normalized_slider(
                key, "chassis", meta, source="gearcity_optimizer.formulas.chassis_formula"
            )
        )

    for key in ENGINE_SLIDER_FIELDS:
        meta = ENGINE_SLIDER_META.get(key, {"label": key.replace("_", " ").title()})
        sliders.append(
            _build_normalized_slider(
                key, "engine", meta, source="gearcity_optimizer.formulas.engine_formula"
            )
        )

    for key, meta in ENGINE_DIMENSIONAL_META.items():
        sliders.append(
            _build_ranged_slider(
                key, "engine", meta, source="gearcity_optimizer.formulas.engine_formula"
            )
        )

    for key, meta in ENGINE_BOOLEAN_META.items():
        sliders.append(
            _build_ranged_slider(
                key, "engine", meta, source="gearcity_optimizer.formulas.engine_formula"
            )
        )

    for key in GEARBOX_SLIDER_FIELDS:
        meta = GEARBOX_SLIDER_META.get(key, {"label": key.replace("_", " ").title()})
        sliders.append(
            _build_normalized_slider(
                key, "gearbox", meta, source="gearcity_optimizer.formulas.gearbox_formula"
            )
        )

    for key, meta in GEARBOX_DISCRETE_META.items():
        sliders.append(
            _build_ranged_slider(
                key, "gearbox", meta, source="gearcity_optimizer.formulas.gearbox_formula"
            )
        )

    for key, meta in VEHICLE_DESIGN_META.items():
        section = str(meta.get("section", "vehicle"))
        sliders.append(
            _build_normalized_slider(
                key,
                section,
                meta,
                source="gearcity_optimizer.core.component_priorities",
            )
        )

    return tuple(sliders)


REAL_SLIDERS: tuple[RealSlider, ...] = _build_registry()


def is_output_stat_key(key: str) -> bool:
    """Return True when a key names a formula output stat, not a control."""
    normalized = key.lower().strip()
    if normalized in OUTPUT_STAT_KEYS:
        return True
    return any(normalized.endswith(suffix) for suffix in ("_rating", "_requirements"))


def is_subcomponent_proxy_key(key: str) -> bool:
    """Return True when a key is a sub-component proxy, not a direct UI slider."""
    return key in SUBCOMPONENT_PROXY_FIELDS


def validate_registry() -> list[str]:
    """Return validation warnings for the slider registry."""
    warnings: list[str] = []
    seen: set[str] = set()
    for slider in REAL_SLIDERS:
        if slider.key in seen:
            warnings.append(f"Duplicate slider key: {slider.key}")
        seen.add(slider.key)
        if is_output_stat_key(slider.field_name):
            warnings.append(
                f"Output stat field incorrectly registered as slider: {slider.key}"
            )
        if is_subcomponent_proxy_key(slider.field_name):
            warnings.append(f"Sub-component proxy registered as slider: {slider.key}")
    return warnings


def list_sliders(*, section: str | None = None) -> list[RealSlider]:
    """Return registry sliders, optionally filtered by section."""
    if section is None:
        return list(REAL_SLIDERS)
    normalized = section.strip().lower()
    return [slider for slider in REAL_SLIDERS if slider.section == normalized]


def get_slider(key: str) -> RealSlider | None:
    """Return one registry slider by key."""
    for slider in REAL_SLIDERS:
        if slider.key == key:
            return slider
    return None


def registry_sections() -> list[str]:
    """Return sorted unique registry sections."""
    return sorted({slider.section for slider in REAL_SLIDERS})
