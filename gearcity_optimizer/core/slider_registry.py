"""Wiki-backed GearCity slider registry and formula influence map."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from gearcity_optimizer.core.wiki_variable_classification import is_output_stat_key, is_wiki_control_variable
from gearcity_optimizer.importers.wiki_downloader import project_root_from_module
from gearcity_optimizer.importers.wiki_formula_effects import FormulaEffect
from gearcity_optimizer.importers.wiki_knowledge_builder import (
    FORMULA_EFFECTS_FILENAME,
    SLIDER_REGISTRY_FILENAME,
    load_formula_effects_from_file,
    load_slider_definitions_from_file,
)
from gearcity_optimizer.importers.wiki_slider_parser import SliderDefinition

SliderScale = Literal["percent", "dimensional"]

WIKI_MISSING_WARNING = (
    "Wiki mechanics sources are missing. Run `gearcity-optimizer setup-sources` "
    "to build the source-backed optimizer model."
)
WIKI_LOADED_MESSAGE = "Source-backed GearCity Wiki mechanics model loaded."

FORMULA_VARIABLE_TO_INTERNAL: dict[str, str] = {
    "Slider_Layout_Bore": "bore",
    "Slider_Layout_Stroke": "stroke",
    "Slider_Layout_Length": "layout_length",
    "Slider_Layout_Width": "layout_width",
    "Slider_Layout_Weight": "layout_weight",
    "Slider_Performance_Revolutions": "revolutions",
    "Slider_Performance_Torque": "aspiration_quality",
    "Slider_Performance_FuelEconomy": "fuel_system_quality",
    "Slider_DesignFocus_Performance": "design_performance",
    "Slider_DesignFocus_FuelEconomy": "design_fuel_economy",
    "Slider_DesignFocus_Dependability": "design_dependability",
    "Slider_DesignFocus_DesignPace": "design_pace",
    "Slider_Technology_Materials": "tech_materials",
    "Slider_Technology_Components": "tech_components",
    "Slider_Technology_Technologies": "tech_technology",
    "Slider_Technology_Techniques": "tech_techniques",
    "Slider_FD_Length": "fd_length",
    "Slider_FD_Width": "fd_width",
    "Slider_FD_Height": "fd_height",
    "Slider_FD_Weight": "fd_weight",
    "Slider_FD_ENG_Width": "fd_engine_width",
    "Slider_FD_ENG_Length": "fd_engine_length",
    "Slider_SUS_Stability": "sus_stability",
    "Slider_SUS_Comfort": "sus_comfort",
    "Slider_SUS_Performance": "sus_performance",
    "Slider_SUS_Braking": "sus_braking",
    "Slider_SUS_Durability": "sus_durability",
    "Slider_DE_Performance": "design_performance",
    "Slider_DE_Control": "design_control",
    "Slider_DE_Str": "design_strength",
    "Slider_DE_Depend": "design_dependability",
    "Slider_DesignPace": "design_pace",
    "Slider_TECH_Materials": "tech_materials",
    "Slider_TECH_Compoenents": "tech_components",
    "Slider_TECH_Techniques": "tech_techniques",
    "Slider_TECH_Tech": "tech_technology",
    "Sliders_LowGear_Ratio": "low_gear_ratio",
    "Sliders_HighGear_Ratio": "high_gear_ratio",
    "Sliders_Torque_Max_Input": "torque_max_input",
    "Sliders_Tech_Material": "tech_material",
    "Sliders_Tech_Components": "tech_components",
    "Sliders_Tech_Technology": "tech_technology",
    "Sliders_Tech_Techniques": "tech_techniques",
    "Sliders_Design_Ease": "design_ease",
    "Sliders_Design_Dependability": "design_dependability",
    "Sliders_Design_DesignPace": "development_pace",
    "Sliders_Design_FuelEconomy": "design_fuel_economy",
    "Sliders_Design_Performance": "design_performance",
}

SUBCOMPONENT_PROXY_FIELDS = frozenset(
    {
        "layout_weight",
        "layout_width",
        "layout_length",
        "layout_smoothness",
        "layout_reliability",
        "layout_performance",
        "layout_manufacturing",
        "layout_design",
        "fuel_system_performance",
        "fuel_system_fuel_economy",
        "fuel_system_reliability",
        "aspiration_performance",
        "aspiration_fuel_economy",
        "aspiration_reliability",
    }
)


@dataclass(frozen=True)
class RealSlider:
    """One wiki-defined controllable input mapped for formula modules."""

    key: str
    label: str
    section: str
    field_name: str
    formula_field: str | None
    min_value: float
    max_value: float
    default_value: float
    step: float
    scale: SliderScale
    confidence: str
    wiki_formula_variable: str
    source_page: str
    source_section: str
    source_context: str
    control_type: str
    affected_outputs: tuple[str, ...] = ()


@dataclass
class SliderRegistry:
    """Loaded wiki slider definitions and formula influence map."""

    sliders: list[SliderDefinition]
    effects: list[FormulaEffect]
    source_mode: str
    warnings: list[str]


def _registry_paths() -> tuple[Path, Path]:
    root = project_root_from_module()
    parsed_dir = root / "generated" / "raw_parsed"
    return parsed_dir / SLIDER_REGISTRY_FILENAME, parsed_dir / FORMULA_EFFECTS_FILENAME


def _definition_to_real_slider(
    definition: SliderDefinition,
    *,
    affected_outputs: tuple[str, ...],
) -> RealSlider | None:
    if not is_wiki_control_variable(
        definition.formula_variable,
        control_type=definition.control_type,
    ):
        return None
    if definition.page not in {"engine", "chassis", "gearbox"}:
        return None

    internal = FORMULA_VARIABLE_TO_INTERNAL.get(definition.formula_variable)
    if internal is None:
        return None

    if definition.formula_variable in {"Slider_Layout_Bore", "Slider_Layout_Stroke"}:
        scale: SliderScale = "dimensional"
        min_value = definition.min_value or 50.0
        max_value = definition.max_value or 150.0
        default_value = definition.default_value or 75.0
    else:
        scale = "percent"
        min_value = definition.min_value or 1.0
        max_value = definition.max_value or 100.0
        default_value = definition.default_value or 40.0

    return RealSlider(
        key=f"{definition.page}.{internal}",
        label=definition.ui_label,
        section=definition.page,
        field_name=internal,
        formula_field=internal,
        min_value=min_value,
        max_value=max_value,
        default_value=default_value,
        step=0.1,
        scale=scale,
        confidence=definition.confidence,
        wiki_formula_variable=definition.formula_variable,
        source_page=definition.source_page,
        source_section=definition.source_section,
        source_context=definition.source_context,
        control_type=definition.control_type,
        affected_outputs=affected_outputs,
    )


@lru_cache(maxsize=1)
def load_slider_registry() -> SliderRegistry:
    """Load wiki-backed slider registry. Returns empty registry when wiki artifacts are missing."""
    slider_path, effects_path = _registry_paths()
    warnings: list[str] = []

    if slider_path.exists() and effects_path.exists():
        sliders = load_slider_definitions_from_file(slider_path)
        effects = load_formula_effects_from_file(effects_path)
        if sliders and effects:
            return SliderRegistry(
                sliders=sliders,
                effects=effects,
                source_mode="wiki",
                warnings=warnings,
            )

    warnings.append(WIKI_MISSING_WARNING)
    return SliderRegistry(
        sliders=[],
        effects=[],
        source_mode="missing",
        warnings=warnings,
    )


def wiki_model_available() -> bool:
    """Return True when wiki slider registry and formula effect map are loaded."""
    registry = load_slider_registry()
    return registry.source_mode == "wiki" and bool(registry.sliders) and bool(registry.effects)


def registry_source_mode() -> str:
    """Return current registry source mode."""
    return load_slider_registry().source_mode


def registry_status_message() -> str | None:
    """Return a user-facing status message for the current registry mode."""
    if wiki_model_available():
        return WIKI_LOADED_MESSAGE
    return WIKI_MISSING_WARNING


def get_sliders_by_page(page: str) -> list[SliderDefinition]:
    """Return slider definitions for one page."""
    normalized = page.strip().lower()
    return [slider for slider in load_slider_registry().sliders if slider.page == normalized]


def get_slider_by_variable(variable: str) -> SliderDefinition | None:
    """Return one slider definition by wiki formula variable."""
    target = variable.strip()
    for slider in load_slider_registry().sliders:
        if slider.formula_variable == target:
            return slider
    return None


def get_outputs_affected_by_slider(variable: str) -> list[FormulaEffect]:
    """Return formula effects that reference a slider variable."""
    target = variable.strip()
    return [
        effect
        for effect in load_slider_registry().effects
        if target in effect.slider_variables
    ]


def is_subcomponent_proxy_key(key: str) -> bool:
    """Return True when a key is a sub-component proxy, not a wiki control."""
    return key in SUBCOMPONENT_PROXY_FIELDS


def validate_registry() -> list[str]:
    """Return validation warnings for the loaded wiki registry."""
    registry = load_slider_registry()
    warnings = list(registry.warnings)
    if not wiki_model_available():
        return warnings

    seen: set[str] = set()
    for definition in registry.sliders:
        if definition.formula_variable in seen:
            warnings.append(f"Duplicate wiki slider variable: {definition.formula_variable}")
        seen.add(definition.formula_variable)
        if is_output_stat_key(definition.formula_variable):
            warnings.append(
                f"Output stat incorrectly registered as control: {definition.formula_variable}"
            )

    real_sliders = list_sliders()
    for slider in real_sliders:
        if is_output_stat_key(slider.wiki_formula_variable):
            warnings.append(
                f"Output stat incorrectly registered as slider: {slider.key}"
            )
    return warnings


def list_sliders(*, section: str | None = None) -> list[RealSlider]:
    """Return wiki-defined optimizer controls. Empty when wiki model is missing."""
    registry = load_slider_registry()
    if not wiki_model_available():
        return []

    outputs_by_variable: dict[str, list[str]] = {}
    for effect in registry.effects:
        for variable in effect.slider_variables:
            outputs_by_variable.setdefault(variable, []).append(effect.output_label)

    real_sliders: list[RealSlider] = []
    for definition in registry.sliders:
        affected = tuple(sorted(set(outputs_by_variable.get(definition.formula_variable, []))))
        converted = _definition_to_real_slider(definition, affected_outputs=affected)
        if converted is not None:
            real_sliders.append(converted)

    if section is None:
        return real_sliders
    normalized = section.strip().lower()
    return [slider for slider in real_sliders if slider.section == normalized]


def get_slider(key: str) -> RealSlider | None:
    """Return one registry slider by key."""
    for slider in list_sliders():
        if slider.key == key:
            return slider
    return None


def registry_sections() -> list[str]:
    """Return sorted unique registry sections."""
    return sorted({slider.section for slider in list_sliders()})
