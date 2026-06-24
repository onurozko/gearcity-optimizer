"""Optimize real GearCity slider settings and predict output stats via formulas."""

from __future__ import annotations

from dataclasses import dataclass, field, fields, replace
from typing import Literal

from gearcity_optimizer.core.component_priorities import get_adjusted_vehicle_weights
from gearcity_optimizer.core.cost_mode import CostMode, parse_cost_mode
from gearcity_optimizer.core.models import VehicleType
from gearcity_optimizer.core.slider_registry import (
    RealSlider,
    WIKI_MISSING_WARNING,
    get_outputs_affected_by_slider,
    get_slider,
    list_sliders,
    load_slider_registry,
    registry_status_message,
    wiki_model_available,
)
from gearcity_optimizer.importers.wiki_formula_effects import build_slider_influence_weights
from gearcity_optimizer.formulas.chassis_formula import (
    ChassisFormulaInputs,
    ChassisFormulaResult,
    calculate_chassis,
)
from gearcity_optimizer.formulas.engine_formula import (
    EngineFormulaInputs,
    EngineFormulaResult,
    calculate_engine,
)
from gearcity_optimizer.formulas.gearbox_formula import (
    GearboxFormulaInputs,
    GearboxFormulaResult,
    calculate_gearbox,
)
from gearcity_optimizer.formulas.vehicle_assembly_formula import (
    ComponentAssemblyInput,
    VehicleAssemblyRatings,
    assemble_vehicle_ratings,
)
from gearcity_optimizer.core.component_models import (
    ChassisCandidate,
    EngineCandidate,
    GearboxCandidate,
)
from gearcity_optimizer.importers.component_choices import ComponentChoice
from gearcity_optimizer.reports.design_physical_constraints import assess_physical_fit
from gearcity_optimizer.core.component_formula_bridge import subcomponent_values_from_choices
from gearcity_optimizer.core.wiki_component_compatibility import (
    filter_compatible_candidates,
    parse_gear_count,
    resolve_engine_layout_key,
    validate_component_choices,
)
from gearcity_optimizer.importers.components_xml import validate_year_input
from gearcity_optimizer.reports.part_recommender import is_work_or_utility_focused

try:
    from gearcity_optimizer.llm.strategy_models import LLMSliderGuidance
except ImportError:  # pragma: no cover
    LLMSliderGuidance = None  # type: ignore[misc, assignment]

OptimizationDepth = Literal["quick", "balanced", "thorough", "llm"]

LUXURY_SLIDER_KEYS = frozenset(
    {
        "sus_comfort",
        "tech_materials",
        "tech_material",
        "tech_technology",
        "layout_length",
    }
)

COST_SLIDER_KEYS = frozenset(
    {
        "design_pace",
        "development_pace",
        "tech_materials",
        "tech_technology",
        "tech_components",
        "tech_techniques",
        "tech_material",
    }
)

ENGINE_SUBCOMPONENT_SLIDER_FIELDS = frozenset(
    {"layout_length", "layout_width", "layout_weight"}
)


@dataclass(frozen=True)
class OptimizationGoal:
    """Target output stat for scoring."""

    output_key: str
    label: str
    target_weight: float
    desired_direction: str
    reason: str


@dataclass(frozen=True)
class ControlSetting:
    """Recommended value for one real control."""

    slider_key: str
    label: str
    section: str
    value: float
    reason: str
    confidence: str
    formula_variable: str | None = None
    source_page: str = ""
    source_section: str = ""
    affected_outputs: tuple[str, ...] = ()
    source_context: str = ""


@dataclass(frozen=True)
class PredictedOutput:
    """Formula-estimated output stat."""

    output_key: str
    label: str
    value: float
    target_weight: float
    reason: str
    is_proxy: bool = False


@dataclass(frozen=True)
class SliderOptimizationInput:
    """Inputs for real-slider optimization."""

    vehicle_type: VehicleType
    year: int
    cost_mode: str
    chassis_skill: float = 0.0
    engine_skill: float = 0.0
    gearbox_skill: float = 0.0
    vehicle_skill: float = 0.0
    depth: OptimizationDepth = "balanced"
    selected_choices: dict[str, ComponentChoice] | None = None
    slider_guidance: tuple[LLMSliderGuidance, ...] | None = None
    available_choices_by_type: dict[str, list[ComponentChoice]] | None = None


@dataclass(frozen=True)
class SliderOptimizationResult:
    """Recommended controls, predicted outputs, and advisor notes."""

    control_settings: list[ControlSetting]
    predicted_outputs: list[PredictedOutput]
    goals: list[OptimizationGoal]
    tradeoffs: list[str]
    warnings: list[str]
    limitations: list[str] = field(default_factory=list)
    chassis_result: ChassisFormulaResult | None = None
    engine_result: EngineFormulaResult | None = None
    gearbox_result: GearboxFormulaResult | None = None
    vehicle_ratings: VehicleAssemblyRatings | None = None
    wiki_model_loaded: bool = False
    optimization_disabled: bool = False
    adjusted_component_choices: dict[str, ComponentChoice] | None = None
    torque_repair_notes: tuple[str, ...] = ()


def build_optimization_goals(
    vehicle_type: VehicleType,
    cost_mode: CostMode,
) -> list[OptimizationGoal]:
    """Build output goals from vehicle type importance weights."""
    weights = get_adjusted_vehicle_weights(vehicle_type)
    goal_specs = [
        ("performance", "Performance", weights.get("performance", 0.0)),
        ("drivability", "Driveability", weights.get("drivability", 0.0)),
        ("luxury", "Luxury", weights.get("luxury", 0.0)),
        ("safety", "Safety", weights.get("safety", 0.0)),
        ("fuel", "Fuel economy", weights.get("fuel", 0.0)),
        ("power", "Power", weights.get("power", 0.0)),
        ("cargo", "Cargo", weights.get("cargo", 0.0)),
        ("dependability", "Dependability", weights.get("dependability", 0.0)),
        ("engine_torque", "Engine torque", weights.get("power", 0.0) * 0.8),
        ("engine_horsepower", "Engine horsepower", weights.get("performance", 0.0) * 0.7),
        (
            "gearbox_max_torque_support",
            "Gearbox max torque support",
            weights.get("power", 0.0) * 0.6,
        ),
    ]
    if cost_mode is CostMode.CHEAP:
        goal_specs.append(
            ("manufacturing_cost", "Manufacturing cost", 0.35, "minimize")
        )

    goals: list[OptimizationGoal] = []
    for item in goal_specs:
        if len(item) == 4:
            key, label, weight, direction = item
        else:
            key, label, weight = item
            direction = "maximize"
        if weight <= 0.05 and key not in {"manufacturing_cost"}:
            continue
        goals.append(
            OptimizationGoal(
                output_key=key,
                label=label,
                target_weight=float(weight),
                desired_direction=direction,
                reason=f"{vehicle_type.name} importance weight for {label.lower()}.",
            )
        )
    goals.sort(key=lambda goal: goal.target_weight, reverse=True)
    return goals


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _priority(weight: float) -> float:
    return _clamp(0.25 + 0.65 * weight, 0.0, 1.0)


def _cost_mode_scale(
    key: str,
    base: float,
    cost_mode: CostMode,
    *,
    vehicle_type: VehicleType,
) -> float:
    weights = get_adjusted_vehicle_weights(vehicle_type)
    if cost_mode is CostMode.CHEAP:
        if key in LUXURY_SLIDER_KEYS:
            luxury_weight = weights.get("luxury", 0.0)
            if luxury_weight < 0.55:
                base *= 0.55
        if key in COST_SLIDER_KEYS:
            base *= 0.75
    elif cost_mode is CostMode.LUXURY:
        if key in LUXURY_SLIDER_KEYS:
            base = min(0.95, base + 0.12)
    return _clamp(base, 0.0, 1.0)


def _recommend_normalized_value(
    slider: RealSlider,
    vehicle_type: VehicleType,
    cost_mode: CostMode,
    *,
    influence_weights: dict[str, float],
) -> tuple[float, str]:
    wiki_var = slider.wiki_formula_variable
    key = slider.field_name

    if wiki_var and influence_weights.get(wiki_var, 0.0) > 0.0:
        max_influence = max(influence_weights.values())
        normalized_influence = influence_weights[wiki_var] / max_influence if max_influence else 0.0
        value = _cost_mode_scale(
            key,
            _priority(normalized_influence),
            cost_mode,
            vehicle_type=vehicle_type,
        )
        outputs = slider.affected_outputs or tuple(
            effect.output_label for effect in get_outputs_affected_by_slider(wiki_var)
        )
        output_text = ", ".join(outputs[:3]) if outputs else "parsed wiki outputs"
        return round(value, 3), (
            f"Formula-model optimized: wiki formulas link {slider.label} to {output_text}."
        )

    value = _cost_mode_scale(key, 0.45, cost_mode, vehicle_type=vehicle_type)
    return round(value, 3), (
        f"No parsed wiki formula influence found for {slider.label}; using neutral default."
    )


def _recommend_dimensional_value(
    slider: RealSlider,
    vehicle_type: VehicleType,
    cost_mode: CostMode,
    *,
    influence_weights: dict[str, float],
) -> tuple[float, str]:
    wiki_var = slider.wiki_formula_variable
    if wiki_var and influence_weights.get(wiki_var, 0.0) > 0.0:
        max_influence = max(influence_weights.values())
        normalized_influence = influence_weights[wiki_var] / max_influence if max_influence else 0.0
        span = slider.max_value - slider.min_value
        value = slider.min_value + span * _priority(normalized_influence)
        outputs = slider.affected_outputs or tuple(
            effect.output_label for effect in get_outputs_affected_by_slider(wiki_var)
        )
        output_text = ", ".join(outputs[:3]) if outputs else "parsed wiki outputs"
        return round(_clamp(value, slider.min_value, slider.max_value), 1), (
            f"Formula-model optimized from wiki influence on {output_text}."
        )

    return slider.default_value, (
        f"No parsed wiki formula influence found for {slider.label}; using neutral default."
    )


def _display_value(slider: RealSlider, raw: float) -> float:
    if slider.scale == "percent":
        return round(raw * 100.0, 1) if raw <= 1.0 else round(raw, 1)
    return round(raw, 1)


def _apply_selected_choices_to_settings(
    settings: list[ControlSetting],
    selected_choices: dict[str, ComponentChoice] | None,
) -> list[ControlSetting]:
    """Annotate slider recommendations when manual/auto component choices were made."""
    if not selected_choices:
        return settings

    updated = list(settings)
    by_key = {setting.slider_key: index for index, setting in enumerate(updated)}
    layout = selected_choices.get("engine_layout")
    if layout is not None and "engine.layout_length" in by_key:
        idx = by_key["engine.layout_length"]
        old = updated[idx]
        updated[idx] = ControlSetting(
            slider_key=old.slider_key,
            label=old.label,
            section=old.section,
            value=old.value,
            reason=(
                f"{old.reason} Selected engine layout: {layout.display_name}."
            ),
            confidence=old.confidence,
            formula_variable=old.formula_variable,
            source_page=old.source_page,
            source_section=old.source_section,
            affected_outputs=old.affected_outputs,
            source_context=old.source_context,
        )
    return updated


def _design_skill_extras(input_data: SliderOptimizationInput) -> dict[str, dict[str, float]]:
    """Pass sidebar design skills into wiki formula globals."""
    return {
        "engine": {"marque_design_engine_skill": float(input_data.engine_skill)},
        "chassis": {"marque_design_chassis_skill": float(input_data.chassis_skill)},
        "gearbox": {"marque_design_gearbox_skill": float(input_data.gearbox_skill)},
    }


def _guidance_for_slider(
    slider: RealSlider,
    guidance_items: tuple[LLMSliderGuidance, ...] | None,
) -> LLMSliderGuidance | None:
    if not guidance_items:
        return None
    label = slider.label.strip().lower()
    for item in guidance_items:
        if item.slider_label.strip().lower() == label:
            return item
    return None


def _apply_slider_guidance(
    slider: RealSlider,
    raw: float,
    guidance: LLMSliderGuidance | None,
) -> tuple[float, str]:
    if guidance is None:
        return raw, ""
    note_parts: list[str] = []
    adjusted = raw
    if guidance.direction == "higher":
        adjusted += 0.12 if slider.scale == "percent" else (slider.max_value - slider.min_value) * 0.12
        note_parts.append("LLM guidance: bias higher")
    elif guidance.direction == "lower":
        adjusted -= 0.12 if slider.scale == "percent" else (slider.max_value - slider.min_value) * 0.12
        note_parts.append("LLM guidance: bias lower")
    if guidance.suggested_range is not None:
        low, high = guidance.suggested_range
        if slider.scale == "percent":
            low = low / 100.0 if high > 1.0 else low
            high = high / 100.0 if high > 1.0 else high
        adjusted = _clamp(adjusted, low, high)
        note_parts.append(f"LLM suggested range {guidance.suggested_range}")
    if slider.scale == "percent":
        adjusted = _clamp(adjusted, 0.0, 1.0)
    else:
        adjusted = _clamp(adjusted, slider.min_value, slider.max_value)
    if guidance.reason:
        note_parts.append(guidance.reason)
    return adjusted, "; ".join(note_parts)


def _build_control_settings(
    vehicle_type: VehicleType,
    cost_mode: CostMode,
    goals: list[OptimizationGoal],
    *,
    slider_guidance: tuple[LLMSliderGuidance, ...] | None = None,
) -> list[ControlSetting]:
    registry = load_slider_registry()
    goal_weights = {goal.output_key: goal.target_weight for goal in goals}
    influence_weights = build_slider_influence_weights(goal_weights, registry.effects)
    settings: list[ControlSetting] = []
    for slider in list_sliders():
        guidance = _guidance_for_slider(slider, slider_guidance)
        if slider.scale == "percent":
            raw, reason = _recommend_normalized_value(
                slider,
                vehicle_type,
                cost_mode,
                influence_weights=influence_weights,
            )
            raw = _clamp(raw, 0.0, 1.0)
            raw, guidance_note = _apply_slider_guidance(slider, raw, guidance)
            display = _display_value(slider, raw)
        else:
            raw, reason = _recommend_dimensional_value(
                slider,
                vehicle_type,
                cost_mode,
                influence_weights=influence_weights,
            )
            raw = _clamp(raw, slider.min_value, slider.max_value)
            raw, guidance_note = _apply_slider_guidance(slider, raw, guidance)
            display = _display_value(slider, raw)
        if guidance_note:
            reason = f"{reason} {guidance_note}"
        settings.append(
            ControlSetting(
                slider_key=slider.key,
                label=slider.label,
                section=slider.section,
                value=display,
                reason=reason,
                confidence=slider.confidence,
                formula_variable=slider.wiki_formula_variable,
                source_page=slider.source_page,
                source_section=slider.source_section,
                affected_outputs=slider.affected_outputs,
                source_context=slider.source_context,
            )
        )
    return settings


def _settings_by_section(
    settings: list[ControlSetting],
) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    grouped: dict[str, dict[str, float]] = {
        "chassis": {},
        "engine": {},
        "gearbox": {},
    }
    engine_subcomponents: dict[str, float] = {}
    for setting in settings:
        slider = get_slider(setting.slider_key)
        if slider is None or slider.formula_field is None:
            continue
        raw = setting.value / 100.0 if slider.scale == "percent" else setting.value
        if slider.field_name in ENGINE_SUBCOMPONENT_SLIDER_FIELDS:
            engine_subcomponents[slider.formula_field] = raw
            continue
        grouped.setdefault(setting.section, {})[slider.formula_field] = raw
    return grouped, engine_subcomponents


def _chassis_inputs_from_settings(
    values: dict[str, float],
    *,
    year: int,
    extra: dict[str, float] | None = None,
) -> ChassisFormulaInputs:
    kwargs: dict[str, object] = {"year": year, "name": "Optimized Chassis"}
    for field in fields(ChassisFormulaInputs):
        if field.name in {"name", "year"}:
            continue
        if field.name in values:
            kwargs[field.name] = values[field.name]
    if extra:
        for key, value in extra.items():
            if key in {field.name for field in fields(ChassisFormulaInputs)}:
                kwargs[key] = value
    return ChassisFormulaInputs(**kwargs)


def _engine_inputs_from_settings(
    values: dict[str, float],
    *,
    year: int,
    extra: dict[str, float] | None = None,
) -> EngineFormulaInputs:
    kwargs: dict[str, object] = {"year": year, "name": "Optimized Engine"}
    bool_fields = {
        "is_supercharged",
        "is_turbocharged",
        "has_fuel_injection",
        "has_overhead_cam",
    }
    int_fields = {"cylinders", "cylinder_bank_arrangement"}
    for field in fields(EngineFormulaInputs):
        if field.name in {"name", "year"}:
            continue
        if field.name not in values:
            continue
        raw = values[field.name]
        if field.name in bool_fields:
            kwargs[field.name] = bool(int(raw))
        elif field.name in int_fields:
            kwargs[field.name] = int(raw)
        else:
            kwargs[field.name] = float(raw)
    if extra:
        for key, value in extra.items():
            if key in {field.name for field in fields(EngineFormulaInputs)}:
                kwargs[key] = value
    if "bore" in values and "stroke" in values:
        kwargs["bore"] = float(values["bore"])
        kwargs["stroke"] = float(values["stroke"])
    return EngineFormulaInputs(**kwargs)


def _gearbox_inputs_from_settings(
    values: dict[str, float],
    *,
    year: int,
    extra: dict[str, float] | None = None,
) -> GearboxFormulaInputs:
    kwargs: dict[str, object] = {"year": year, "name": "Optimized Gearbox"}
    bool_fields = {"has_limited_slip", "has_overdrive", "has_transaxle", "has_reverse"}
    for field in fields(GearboxFormulaInputs):
        if field.name in {"name", "year"}:
            continue
        if field.name not in values:
            continue
        raw = values[field.name]
        if field.name in bool_fields:
            kwargs[field.name] = bool(int(raw))
        elif field.name == "number_of_gears":
            kwargs[field.name] = int(raw)
        else:
            kwargs[field.name] = float(raw)
    if extra:
        for key, value in extra.items():
            if key in {field.name for field in fields(GearboxFormulaInputs)}:
                kwargs[key] = value
    return GearboxFormulaInputs(**kwargs)


def _build_predicted_outputs(
    goals: list[OptimizationGoal],
    *,
    chassis: ChassisFormulaResult,
    engine: EngineFormulaResult,
    gearbox: GearboxFormulaResult,
    vehicle: VehicleAssemblyRatings,
) -> list[PredictedOutput]:
    weight_by_key = {goal.output_key: goal.target_weight for goal in goals}
    outputs = [
        PredictedOutput("power", "Horsepower (formula raw)", engine.horsepower, weight_by_key.get("engine_horsepower", 0.0), "Raw wiki formula horsepower, not the 0-100 Power rating.", False),
        PredictedOutput("torque", "Torque (lb-ft)", engine.torque, weight_by_key.get("engine_torque", 0.0), "Predicted engine torque from wiki formula.", False),
        PredictedOutput("engine_bore_mm", "Engine bore (mm)", engine.bore_mm, 0.0, "Bore used in wiki length/width/torque formulas.", False),
        PredictedOutput("engine_stroke_mm", "Engine stroke (mm)", engine.stroke_mm, 0.0, "Stroke used in wiki length/width/torque formulas.", False),
        PredictedOutput("engine_displacement_cc", "Engine displacement (cc)", engine.displacement_cc, 0.0, "Displacement from bore x stroke x cylinders.", False),
        PredictedOutput("engine_cylinders", "Engine cylinders", float(engine.cylinder_count), 0.0, "Cylinder count wired from component choices.", False),
        PredictedOutput("engine_length_in", "Engine length (in)", engine.length, 0.0, "Predicted engine length from wiki formula.", False),
        PredictedOutput("engine_width_in", "Engine width (in)", engine.width, 0.0, "Predicted engine width from wiki formula.", False),
        PredictedOutput("chassis_max_engine_length_in", "Chassis max engine length (in)", chassis.max_engine_length, 0.0, "From chassis formula bay limit.", False),
        PredictedOutput("chassis_max_engine_width_in", "Chassis max engine width (in)", chassis.max_engine_width, 0.0, "From chassis formula bay limit.", False),
        PredictedOutput("fuel", "Fuel", engine.fuel_economy, weight_by_key.get("fuel", 0.0), "Predicted from engine formula.", False),
        PredictedOutput("smoothness", "Smoothness", engine.smoothness_rating, weight_by_key.get("luxury", 0.0), "Predicted from engine formula.", False),
        PredictedOutput("reliability", "Reliability", engine.reliability_rating, weight_by_key.get("dependability", 0.0), "Predicted from engine formula.", False),
        PredictedOutput(
            "engine_overall",
            "Engine overall",
            engine.overall_rating,
            weight_by_key.get("performance", 0.0) * 0.5,
            "Predicted from engine formula.",
            False,
        ),
        PredictedOutput(
            "vehicle_overall",
            "Vehicle overall (proxy)",
            vehicle.overall,
            weight_by_key.get("performance", 0.0),
            "Proxy assembly from component ratings.",
            True,
        ),
        PredictedOutput(
            "vehicle_quality",
            "Vehicle quality (proxy)",
            vehicle.quality,
            weight_by_key.get("dependability", 0.0),
            "Proxy assembly from component ratings.",
            True,
        ),
        PredictedOutput(
            "overall",
            "Overall",
            vehicle.overall,
            weight_by_key.get("performance", 0.0),
            "Uses assembled vehicle overall proxy for design scoring.",
            True,
        ),
        PredictedOutput(
            "design_requirements",
            "Design requirements",
            chassis.overall_rating * 0.35 + engine.overall_rating * 0.35 + gearbox.overall_rating * 0.30,
            0.2,
            "Proxy from component overall ratings and development pace sliders.",
            True,
        ),
        PredictedOutput(
            "manufacturing_requirements",
            "Manufacturing requirements",
            (100.0 - chassis.performance_rating) * 0.4 + (100.0 - engine.reliability_rating) * 0.3,
            0.2,
            "Proxy from reliability/performance tradeoffs and cost mode.",
            True,
        ),
        PredictedOutput("chassis_comfort", "Chassis comfort (proxy)", chassis.comfort_rating, weight_by_key.get("luxury", 0.0), "From chassis formula.", False),
        PredictedOutput("chassis_strength", "Chassis strength (proxy)", chassis.strength_rating, weight_by_key.get("safety", 0.0), "From chassis formula.", False),
        PredictedOutput("gearbox_torque_support", "Gearbox torque support (proxy)", gearbox.max_torque_support, weight_by_key.get("gearbox_max_torque_support", 0.0), "From gearbox formula.", False),
        PredictedOutput("vehicle_performance", "Vehicle performance (proxy)", vehicle.performance, weight_by_key.get("performance", 0.0), "Proxy assembly from component ratings.", True),
        PredictedOutput("vehicle_dependability", "Vehicle dependability (proxy)", vehicle.dependability, weight_by_key.get("dependability", 0.0), "Proxy assembly from component ratings.", True),
    ]
    return outputs


def _build_tradeoffs(
    vehicle_type: VehicleType,
    cost_mode: CostMode,
    goals: list[OptimizationGoal],
) -> list[str]:
    weights = get_adjusted_vehicle_weights(vehicle_type)
    tradeoffs: list[str] = []
    if cost_mode is CostMode.CHEAP:
        if weights.get("luxury", 0.0) < 0.55:
            tradeoffs.append(
                f"Cheap mode keeps luxury/style controls lower because {vehicle_type.name} "
                "priorities and cost mode do not justify overspending."
            )
        if weights.get("fuel", 0.0) >= 0.45:
            tradeoffs.append(
                "Fuel economy and reliability design focuses are prioritized because "
                "they strongly affect this vehicle type."
            )
    elif cost_mode is CostMode.LUXURY:
        tradeoffs.append(
            "Luxury mode allows higher comfort, smoothness, and material-quality "
            "controls where the vehicle type benefits."
        )
    else:
        tradeoffs.append(
            "Balanced mode spends most on the highest vehicle-type weights without "
            "extreme cost cutting or luxury overspend."
        )
    if is_work_or_utility_focused(vehicle_type):
        tradeoffs.append(
            "Maximum Torque Input and Low End Gearing are kept high enough for work-focused "
            "load requirements."
        )
    if goals:
        top = goals[0].label
        tradeoffs.append(f"Top optimization target: {top}.")
    return tradeoffs


def optimize_real_slider_settings(
    input_data: SliderOptimizationInput,
) -> SliderOptimizationResult:
    """Recommend exact real control values and predict output stats."""
    validate_year_input(input_data.year)
    cost_mode = parse_cost_mode(input_data.cost_mode)
    vehicle_type = input_data.vehicle_type
    goals = build_optimization_goals(vehicle_type, cost_mode)

    if not wiki_model_available():
        return SliderOptimizationResult(
            control_settings=[],
            predicted_outputs=[],
            goals=goals,
            tradeoffs=[],
            warnings=[WIKI_MISSING_WARNING],
            limitations=[
                "Exact slider optimization requires parsed GearCity Wiki mechanics.",
                "Run `gearcity-optimizer setup-sources` to build the source-backed optimizer model.",
            ],
            wiki_model_loaded=False,
            optimization_disabled=True,
        )

    controls = _build_control_settings(
        vehicle_type,
        cost_mode,
        goals,
        slider_guidance=input_data.slider_guidance,
    )
    controls = _apply_selected_choices_to_settings(
        controls,
        input_data.selected_choices,
    )
    grouped, engine_slider_subcomponents = _settings_by_section(controls)
    choice_subcomponents = subcomponent_values_from_choices(input_data.selected_choices)
    skill_extras = _design_skill_extras(input_data)
    engine_extra = {
        **choice_subcomponents.get("engine", {}),
        **skill_extras.get("engine", {}),
        **engine_slider_subcomponents,
    }

    chassis_inputs = _chassis_inputs_from_settings(
        grouped.get("chassis", {}),
        year=input_data.year,
        extra={
            **choice_subcomponents.get("chassis", {}),
            **skill_extras.get("chassis", {}),
        },
    )
    engine_inputs = _engine_inputs_from_settings(
        grouped.get("engine", {}),
        year=input_data.year,
        extra=engine_extra,
    )
    gearbox_inputs = _gearbox_inputs_from_settings(
        grouped.get("gearbox", {}),
        year=input_data.year,
        extra={
            **choice_subcomponents.get("gearbox", {}),
            **skill_extras.get("gearbox", {}),
        },
    )

    chassis_result = calculate_chassis(chassis_inputs)
    engine_result = calculate_engine(engine_inputs)
    gearbox_result = calculate_gearbox(gearbox_inputs)

    assembly = ComponentAssemblyInput(
        chassis=ChassisCandidate(
            name="optimized",
            comfort=chassis_result.comfort_rating,
            performance=chassis_result.performance_rating,
            strength=chassis_result.strength_rating,
            durability=chassis_result.durability_rating,
            overall=chassis_result.overall_rating,
            unit_cost=1.0,
        ),
        engine=EngineCandidate(
            name="optimized",
            horsepower=engine_result.horsepower,
            torque=engine_result.torque,
            fuel_economy=engine_result.fuel_economy,
            reliability=engine_result.reliability_rating,
            smoothness=engine_result.smoothness_rating,
            overall=engine_result.overall_rating,
            unit_cost=1.0,
        ),
        gearbox=GearboxCandidate(
            name="optimized",
            power=gearbox_result.power_rating,
            max_torque=gearbox_result.max_torque_support,
            fuel_economy=gearbox_result.fuel_economy_rating,
            performance=gearbox_result.performance_rating,
            reliability=gearbox_result.reliability_rating,
            comfort=gearbox_result.comfort_rating,
            overall=gearbox_result.overall_rating,
            unit_cost=1.0,
        ),
    )
    vehicle_ratings = assemble_vehicle_ratings(assembly)
    predicted = _build_predicted_outputs(
        goals,
        chassis=chassis_result,
        engine=engine_result,
        gearbox=gearbox_result,
        vehicle=vehicle_ratings,
    )
    warnings = list(chassis_result.warnings) + list(engine_result.warnings) + list(
        gearbox_result.warnings
    )
    registry = load_slider_registry()
    warnings.extend(registry.warnings)
    status_message = registry_status_message()
    limitations = [
        "Formula-model optimized from GearCity Wiki mechanics. "
        "Deterministic recommendations based on parsed wiki pseudo-code, not hidden game code.",
        "Slider Summary controls use exact in-game labels; predicted outputs are separate.",
    ]
    if registry.source_mode == "wiki" and status_message:
        limitations.insert(0, status_message)
    if input_data.selected_choices:
        limitations.append(
            "Slider values were optimized around the selected Components.xml component "
            "choices where parsed stats were available."
        )
    else:
        limitations.append(
            "No Components.xml component choices were applied; slider values use "
            "formula/proxy defaults."
        )
    repaired_result = repair_torque_fit_design(input_data, controls)
    merged_limitations = list(limitations)
    for note in repaired_result.torque_repair_notes:
        if note not in merged_limitations:
            merged_limitations.append(note)
    return replace(
        repaired_result,
        tradeoffs=_build_tradeoffs(vehicle_type, cost_mode, goals),
        warnings=[*warnings, *repaired_result.warnings],
        limitations=merged_limitations,
    )


def control_settings_for_section(
    result: SliderOptimizationResult,
    section: str,
) -> list[ControlSetting]:
    """Return control settings for one section."""
    normalized = section.strip().lower()
    return [item for item in result.control_settings if item.section == normalized]


SLIDER_SEED_PROFILES: tuple[str, ...] = (
    "neutral",
    "fuel_dependability",
    "performance_power",
    "luxury_comfort",
    "low_cost",
    "balanced",
)

PROFILE_GOAL_BOOSTS: dict[str, dict[str, float]] = {
    "neutral": {},
    "fuel_dependability": {
        "fuel": 1.45,
        "dependability": 1.35,
        "quality": 1.15,
    },
    "performance_power": {
        "performance": 1.45,
        "power": 1.40,
        "drivability": 1.10,
    },
    "luxury_comfort": {
        "luxury": 1.50,
        "drivability": 1.20,
        "safety": 1.10,
    },
    "low_cost": {
        "fuel": 1.15,
        "dependability": 1.20,
        "manufacturing_cost": 1.60,
    },
    "balanced": {
        "performance": 1.10,
        "fuel": 1.10,
        "dependability": 1.10,
        "safety": 1.10,
    },
}


def _boosted_goal_weights(
    goals: list[OptimizationGoal],
    profile: str,
) -> dict[str, float]:
    boosts = PROFILE_GOAL_BOOSTS.get(profile, {})
    weights = {goal.output_key: goal.target_weight for goal in goals}
    for key, multiplier in boosts.items():
        if key in weights:
            weights[key] *= multiplier
        elif key == "manufacturing_cost":
            weights[key] = 0.45 * multiplier
    return weights


def build_seed_control_settings(
    vehicle_type: VehicleType,
    cost_mode: CostMode,
    goals: list[OptimizationGoal],
    *,
    profile: str = "neutral",
    slider_guidance: tuple[LLMSliderGuidance, ...] | None = None,
) -> list[ControlSetting]:
    """Build slider settings from a named optimization seed profile."""
    registry = load_slider_registry()
    goal_weights = _boosted_goal_weights(goals, profile)
    influence_weights = build_slider_influence_weights(goal_weights, registry.effects)
    settings: list[ControlSetting] = []
    for slider in list_sliders():
        guidance = _guidance_for_slider(slider, slider_guidance)
        if slider.scale == "percent":
            raw, reason = _recommend_normalized_value(
                slider,
                vehicle_type,
                cost_mode,
                influence_weights=influence_weights,
            )
            if profile == "low_cost" and slider.field_name in COST_SLIDER_KEYS:
                raw *= 0.72
            if profile == "luxury_comfort" and slider.field_name in LUXURY_SLIDER_KEYS:
                raw = min(0.95, raw + 0.10)
            raw = _clamp(raw, 0.0, 1.0)
            raw, guidance_note = _apply_slider_guidance(slider, raw, guidance)
            display = _display_value(slider, raw)
        else:
            raw, reason = _recommend_dimensional_value(
                slider,
                vehicle_type,
                cost_mode,
                influence_weights=influence_weights,
            )
            raw = _clamp(raw, slider.min_value, slider.max_value)
            raw, guidance_note = _apply_slider_guidance(slider, raw, guidance)
            display = _display_value(slider, raw)
        if guidance_note:
            reason = f"{reason} {guidance_note}"
        reason = f"[{profile}] {reason}"
        settings.append(
            ControlSetting(
                slider_key=slider.key,
                label=slider.label,
                section=slider.section,
                value=display,
                reason=reason,
                confidence=slider.confidence,
                formula_variable=slider.wiki_formula_variable,
                source_page=slider.source_page,
                source_section=slider.source_section,
                affected_outputs=slider.affected_outputs,
                source_context=slider.source_context,
            )
        )
    return settings


def run_formula_pipeline(
    input_data: SliderOptimizationInput,
    controls: list[ControlSetting],
) -> SliderOptimizationResult:
    """Run formulas and build predicted outputs for explicit control settings."""
    validate_year_input(input_data.year)
    cost_mode = parse_cost_mode(input_data.cost_mode)
    goals = build_optimization_goals(input_data.vehicle_type, cost_mode)
    controls = _apply_selected_choices_to_settings(controls, input_data.selected_choices)
    grouped, engine_slider_subcomponents = _settings_by_section(controls)
    choice_subcomponents = subcomponent_values_from_choices(input_data.selected_choices)
    skill_extras = _design_skill_extras(input_data)
    engine_extra = {
        **choice_subcomponents.get("engine", {}),
        **skill_extras.get("engine", {}),
        **engine_slider_subcomponents,
    }
    chassis_inputs = _chassis_inputs_from_settings(
        grouped.get("chassis", {}),
        year=input_data.year,
        extra={
            **choice_subcomponents.get("chassis", {}),
            **skill_extras.get("chassis", {}),
        },
    )
    engine_inputs = _engine_inputs_from_settings(
        grouped.get("engine", {}),
        year=input_data.year,
        extra=engine_extra,
    )
    gearbox_inputs = _gearbox_inputs_from_settings(
        grouped.get("gearbox", {}),
        year=input_data.year,
        extra={
            **choice_subcomponents.get("gearbox", {}),
            **skill_extras.get("gearbox", {}),
        },
    )
    chassis_result = calculate_chassis(chassis_inputs)
    engine_result = calculate_engine(engine_inputs)
    gearbox_result = calculate_gearbox(gearbox_inputs)
    assembly = ComponentAssemblyInput(
        chassis=ChassisCandidate(
            name="optimized",
            comfort=chassis_result.comfort_rating,
            performance=chassis_result.performance_rating,
            strength=chassis_result.strength_rating,
            durability=chassis_result.durability_rating,
            overall=chassis_result.overall_rating,
            unit_cost=1.0,
        ),
        engine=EngineCandidate(
            name="optimized",
            horsepower=engine_result.horsepower,
            torque=engine_result.torque,
            fuel_economy=engine_result.fuel_economy,
            reliability=engine_result.reliability_rating,
            smoothness=engine_result.smoothness_rating,
            overall=engine_result.overall_rating,
            unit_cost=1.0,
        ),
        gearbox=GearboxCandidate(
            name="optimized",
            power=gearbox_result.power_rating,
            max_torque=gearbox_result.max_torque_support,
            fuel_economy=gearbox_result.fuel_economy_rating,
            performance=gearbox_result.performance_rating,
            reliability=gearbox_result.reliability_rating,
            comfort=gearbox_result.comfort_rating,
            overall=gearbox_result.overall_rating,
            unit_cost=1.0,
        ),
    )
    vehicle_ratings = assemble_vehicle_ratings(assembly)
    predicted = _build_predicted_outputs(
        goals,
        chassis=chassis_result,
        engine=engine_result,
        gearbox=gearbox_result,
        vehicle=vehicle_ratings,
    )
    warnings = list(chassis_result.warnings) + list(engine_result.warnings) + list(
        gearbox_result.warnings
    )
    return SliderOptimizationResult(
        control_settings=controls,
        predicted_outputs=predicted,
        goals=goals,
        tradeoffs=_build_tradeoffs(input_data.vehicle_type, cost_mode, goals),
        warnings=warnings,
        limitations=[],
        chassis_result=chassis_result,
        engine_result=engine_result,
        gearbox_result=gearbox_result,
        vehicle_ratings=vehicle_ratings,
        wiki_model_loaded=True,
        optimization_disabled=False,
    )


def _mutate_control_setting(setting: ControlSetting, delta: float) -> ControlSetting:
    slider = get_slider(setting.slider_key)
    if slider is None:
        return setting
    if slider.scale == "percent":
        raw = setting.value / 100.0 if setting.value > 1.0 else setting.value
        raw = _clamp(raw + delta, 0.0, 1.0)
        value = _display_value(slider, raw)
    else:
        value = _clamp(setting.value + delta, slider.min_value, slider.max_value)
    return ControlSetting(
        slider_key=setting.slider_key,
        label=setting.label,
        section=setting.section,
        value=value,
        reason=f"{setting.reason} Hill-climb adjustment.",
        confidence=setting.confidence,
        formula_variable=setting.formula_variable,
        source_page=setting.source_page,
        source_section=setting.source_section,
        affected_outputs=setting.affected_outputs,
        source_context=setting.source_context,
    )


def _depth_search_params(depth: OptimizationDepth) -> tuple[int, int, int, int]:
    """Return top_per_type, seed_count, hill_steps, max_full_evaluations."""
    if depth == "llm":
        return 2, 1, 3, 1
    if depth == "quick":
        return 2, 3, 4, 3
    if depth == "thorough":
        return 5, 6, 10, 8
    return 3, 5, 8, 5


def _hill_climb_slider_limit(depth: OptimizationDepth) -> int | None:
    """Cap hill-climb sliders for fast depths; None means all formula-linked sliders."""
    if depth == "llm":
        return 12
    if depth == "quick":
        return 18
    return None


def _hill_climb_indices(
    current_controls: list[ControlSetting],
    *,
    goals: list[OptimizationGoal],
    depth: OptimizationDepth,
    slider_guidance: tuple[LLMSliderGuidance, ...] | None,
) -> list[int]:
    """Order slider indices for hill climb, prioritizing influential and LLM-guided sliders."""
    limit = _hill_climb_slider_limit(depth)
    if limit is None:
        return list(range(len(current_controls)))

    registry = load_slider_registry()
    goal_weights = {goal.output_key: goal.target_weight for goal in goals}
    influence_weights = build_slider_influence_weights(goal_weights, registry.effects)

    ranked: list[tuple[float, int]] = []
    for index, setting in enumerate(current_controls):
        slider = get_slider(setting.slider_key)
        if slider is None or slider.formula_field is None:
            continue
        wiki_var = slider.wiki_formula_variable or ""
        weight = influence_weights.get(wiki_var, 0.0)
        if _guidance_for_slider(slider, slider_guidance) is not None:
            weight += 10.0
        ranked.append((weight, index))

    if not ranked:
        return list(range(len(current_controls)))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [index for _, index in ranked[:limit]]


TORQUE_RAISE_FIELDS = frozenset({"torque_max_input"})
TORQUE_REDUCE_FIELDS = frozenset(
    {
        "design_performance",
        "layout_performance",
        "aspiration_performance",
        "revolutions",
        "bore",
        "stroke",
    }
)


def _torque_fit_mutation_indices(
    controls: list[ControlSetting],
) -> tuple[list[int], list[int]]:
    raise_indices: list[int] = []
    lower_indices: list[int] = []
    for index, setting in enumerate(controls):
        slider = get_slider(setting.slider_key)
        if slider is None or slider.formula_field is None:
            continue
        if slider.formula_field in TORQUE_RAISE_FIELDS:
            raise_indices.append(index)
        elif slider.formula_field in TORQUE_REDUCE_FIELDS:
            lower_indices.append(index)
    return raise_indices, lower_indices


def _assess_torque_fit(
    input_data: SliderOptimizationInput,
    controls: list[ControlSetting],
):
    result = run_formula_pipeline(input_data, controls)
    assessment = assess_physical_fit(
        engine=result.engine_result,
        chassis=result.chassis_result,
        gearbox=result.gearbox_result,
    )
    return assessment, result


def enforce_torque_fit_controls(
    input_data: SliderOptimizationInput,
    controls: list[ControlSetting],
    *,
    max_iterations: int = 48,
) -> list[ControlSetting]:
    """Greedy slider repair when engine torque exceeds gearbox capacity."""
    assessment, _ = _assess_torque_fit(input_data, controls)
    if assessment.torque_ok is not False:
        return controls

    current = list(controls)
    raise_indices, lower_indices = _torque_fit_mutation_indices(current)
    candidate_indices = raise_indices + lower_indices
    if not candidate_indices:
        return current

    for _ in range(max_iterations):
        if assessment.torque_ok:
            break
        best_margin = assessment.torque_margin_ratio or 0.0
        best_controls: list[ControlSetting] | None = None
        best_assessment = assessment

        for index in candidate_indices:
            setting = current[index]
            slider = get_slider(setting.slider_key)
            if slider is None or slider.formula_field is None:
                continue
            base_step = (
                0.05
                if slider.scale == "percent"
                else (slider.max_value - slider.min_value) * 0.05
            )
            margin = assessment.torque_margin_ratio or 0.0
            if margin >= 0.85:
                base_step *= 0.4
            if slider.formula_field in TORQUE_RAISE_FIELDS:
                deltas = (base_step, base_step * 2.0, base_step * 3.0)
            else:
                deltas = (-base_step, -base_step * 2.0, -base_step * 3.0)
            for delta in deltas:
                trial_setting = _mutate_control_setting(setting, delta)
                if trial_setting.value == setting.value:
                    continue
                trial_controls = list(current)
                trial_controls[index] = trial_setting
                trial_assessment, _ = _assess_torque_fit(input_data, trial_controls)
                trial_margin = trial_assessment.torque_margin_ratio or 0.0
                if trial_assessment.torque_ok or trial_margin > best_margin + 1e-6:
                    best_margin = 1.0 if trial_assessment.torque_ok else trial_margin
                    best_controls = trial_controls
                    best_assessment = trial_assessment
                    if trial_assessment.torque_ok:
                        break
            if best_assessment.torque_ok:
                break

        if best_controls is None:
            break
        current = best_controls
        assessment = best_assessment

    return current


def _upgrade_gear_count_for_torque(
    input_data: SliderOptimizationInput,
    controls: list[ControlSetting],
) -> tuple[SliderOptimizationInput, tuple[str, ...]]:
    """Try higher gear-count components when sliders alone cannot close torque gap."""
    available_by_type = input_data.available_choices_by_type
    if not available_by_type:
        return input_data, ()

    choices = dict(input_data.selected_choices or {})
    gear_options = available_by_type.get("gear_count", [])
    parsed: list[tuple[int, ComponentChoice]] = []
    for choice in gear_options:
        gears = parse_gear_count(choice)
        if gears is not None:
            parsed.append((gears, choice))
    if not parsed:
        return input_data, ()

    parsed.sort(key=lambda item: item[0])
    current_gears = (
        parse_gear_count(choices["gear_count"]) if "gear_count" in choices else None
    )
    assessment, _ = _assess_torque_fit(input_data, controls)
    if assessment.torque_ok:
        return input_data, ()

    best_input = input_data
    best_margin = assessment.torque_margin_ratio or 0.0
    notes: list[str] = []

    for gears, choice in reversed(parsed):
        if current_gears is not None and gears <= current_gears:
            continue
        if choices and not filter_compatible_candidates("gear_count", choice, choices):
            continue
        trial_choices = {**choices, "gear_count": choice}
        trial_input = replace(input_data, selected_choices=trial_choices)
        trial_assessment, _ = _assess_torque_fit(trial_input, controls)
        trial_margin = trial_assessment.torque_margin_ratio or 0.0
        if trial_assessment.torque_ok:
            notes.append(
                f"Upgraded to {choice.display_name} ({gears} gears): gearbox torque "
                f"{trial_assessment.gearbox_max_torque_lbft:.0f} lb-ft covers "
                f"engine {trial_assessment.engine_torque_lbft:.0f} lb-ft."
            )
            return trial_input, tuple(notes)
        if trial_margin > best_margin + 1e-6:
            best_margin = trial_margin
            best_input = trial_input
            notes = [
                f"Upgraded to {choice.display_name} ({gears} gears) to improve torque margin "
                f"to {trial_margin:.0%}."
            ]

    return best_input, tuple(notes)


def repair_torque_fit_design(
    input_data: SliderOptimizationInput,
    controls: list[ControlSetting],
) -> SliderOptimizationResult:
    """Upgrade gear count if needed, then tune sliders until engine torque fits gearbox."""
    upgraded_input, gear_notes = _upgrade_gear_count_for_torque(input_data, controls)
    repaired_controls = enforce_torque_fit_controls(upgraded_input, controls)
    repair_notes = list(gear_notes)
    if repaired_controls is not controls:
        repair_notes.append("Adjusted gearbox/engine sliders for torque fit.")
    result = run_formula_pipeline(upgraded_input, repaired_controls)
    adjusted = (
        dict(upgraded_input.selected_choices)
        if upgraded_input.selected_choices
        else None
    )
    extra_limitations = [note for note in repair_notes if note not in result.limitations]
    return replace(
        result,
        control_settings=repaired_controls,
        adjusted_component_choices=adjusted,
        torque_repair_notes=tuple(repair_notes),
        limitations=[*result.limitations, *extra_limitations],
    )


def optimize_sliders_for_objective(
    input_data: SliderOptimizationInput,
    *,
    score_fn,
    seed_profiles: tuple[str, ...] | None = None,
) -> SliderOptimizationResult:
    """Search slider settings that maximize a global objective score function."""
    if not wiki_model_available():
        cost_mode = parse_cost_mode(input_data.cost_mode)
        goals = build_optimization_goals(input_data.vehicle_type, cost_mode)
        return SliderOptimizationResult(
            control_settings=[],
            predicted_outputs=[],
            goals=goals,
            tradeoffs=[],
            warnings=[WIKI_MISSING_WARNING],
            limitations=[
                "Exact slider optimization requires parsed GearCity Wiki mechanics.",
            ],
            wiki_model_loaded=False,
            optimization_disabled=True,
        )

    cost_mode = parse_cost_mode(input_data.cost_mode)
    goals = build_optimization_goals(input_data.vehicle_type, cost_mode)
    _, _, hill_steps, _ = _depth_search_params(input_data.depth)
    profiles = seed_profiles or SLIDER_SEED_PROFILES[: _depth_search_params(input_data.depth)[1]]

    best_result: SliderOptimizationResult | None = None
    best_score = float("-inf")

    for profile in profiles:
        seed_controls = build_seed_control_settings(
            input_data.vehicle_type,
            cost_mode,
            goals,
            profile=profile,
            slider_guidance=input_data.slider_guidance,
        )
        candidate_result = run_formula_pipeline(input_data, seed_controls)
        candidate_score = score_fn(candidate_result)
        if candidate_score > best_score:
            best_score = candidate_score
            best_result = candidate_result

        current_controls = list(candidate_result.control_settings)
        climb_indices = _hill_climb_indices(
            current_controls,
            goals=goals,
            depth=input_data.depth,
            slider_guidance=input_data.slider_guidance,
        )
        for _ in range(hill_steps):
            improved = False
            for index in climb_indices:
                setting = current_controls[index]
                slider = get_slider(setting.slider_key)
                if slider is None or slider.formula_field is None:
                    continue
                step = 0.05 if slider.scale == "percent" else (slider.max_value - slider.min_value) * 0.05
                for delta in (step, -step):
                    trial_controls = list(current_controls)
                    trial_controls[index] = _mutate_control_setting(setting, delta)
                    trial_result = run_formula_pipeline(input_data, trial_controls)
                    trial_score = score_fn(trial_result)
                    if trial_score > best_score:
                        best_score = trial_score
                        best_result = trial_result
                        current_controls = trial_controls
                        improved = True
                        break
                if improved:
                    break
            if not improved:
                break

    assert best_result is not None
    best_result = repair_torque_fit_design(input_data, best_result.control_settings)
    limitations = [
        "Global slider search optimized complete predicted vehicle outputs, not isolated slider labels.",
        "Formula-model optimized from GearCity Wiki mechanics.",
    ]
    if input_data.depth == "llm":
        limitations.append(
            "LLM fast path: one seed profile and limited hill-climb on high-influence sliders only."
        )
    if input_data.selected_choices:
        limitations.append(
            "Slider values were optimized around the selected Components.xml component choices."
        )
    return SliderOptimizationResult(
        control_settings=best_result.control_settings,
        predicted_outputs=best_result.predicted_outputs,
        goals=best_result.goals,
        tradeoffs=best_result.tradeoffs,
        warnings=best_result.warnings,
        limitations=limitations,
        chassis_result=best_result.chassis_result,
        engine_result=best_result.engine_result,
        gearbox_result=best_result.gearbox_result,
        vehicle_ratings=best_result.vehicle_ratings,
        wiki_model_loaded=True,
        optimization_disabled=False,
        adjusted_component_choices=best_result.adjusted_component_choices,
        torque_repair_notes=best_result.torque_repair_notes,
    )

