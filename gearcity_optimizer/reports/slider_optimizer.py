"""Optimize real GearCity slider settings and predict output stats via formulas."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
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
from gearcity_optimizer.importers.components_xml import validate_year_input
from gearcity_optimizer.reports.part_recommender import is_work_or_utility_focused

OptimizationDepth = Literal["quick", "balanced", "thorough"]

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


def _subcomponent_values_from_choices(
    selected_choices: dict[str, ComponentChoice] | None,
) -> dict[str, dict[str, float]]:
    """Map selected choices to subcomponent stat proxies for formulas."""
    if not selected_choices:
        return {"engine": {}, "chassis": {}, "gearbox": {}}

    engine: dict[str, float] = {}
    chassis: dict[str, float] = {}
    gearbox: dict[str, float] = {}

    layout = selected_choices.get("engine_layout")
    if layout is not None:
        for src, dest in (
            ("weight", "layout_weight"),
            ("width", "layout_width"),
            ("length", "layout_length"),
            ("smoothness", "layout_smoothness"),
            ("reliability", "layout_reliability"),
            ("performance", "layout_performance"),
            ("manufacturing", "layout_manufacturing"),
            ("design", "layout_design"),
        ):
            if src in layout.stats:
                engine[dest] = layout.stats[src]

    fuel = selected_choices.get("fuel_type")
    if fuel is not None:
        for src, dest in (
            ("performance", "fuel_system_performance"),
            ("fueleconomy", "fuel_system_fuel_economy"),
            ("reliability", "fuel_system_reliability"),
        ):
            if src in fuel.stats:
                engine[dest] = fuel.stats[src]

    induction = selected_choices.get("forced_induction")
    if induction is not None:
        for src, dest in (
            ("performance", "aspiration_performance"),
            ("fueleconomy", "aspiration_fuel_economy"),
            ("reliability", "aspiration_reliability"),
        ):
            if src in induction.stats:
                engine[dest] = induction.stats[src]

    frame = selected_choices.get("frame")
    if frame is not None:
        for src, dest in (
            ("weight", "subcomponent_weight"),
            ("complexity", "subcomponent_complexity"),
            ("performance", "subcomponent_performance_rating"),
            ("reliability", "subcomponent_durability"),
        ):
            if src in frame.stats:
                chassis[dest] = frame.stats[src]

    gearbox_type = selected_choices.get("gearbox_type")
    if gearbox_type is not None:
        for src, dest in (
            ("performance", "subcomponent_performance_rating"),
            ("fueleconomy", "subcomponent_fuel_rating"),
            ("reliability", "subcomponent_durability"),
            ("smoothness", "subcomponent_smoothness"),
        ):
            if src in gearbox_type.stats:
                gearbox[dest] = gearbox_type.stats[src]

    return {"engine": engine, "chassis": chassis, "gearbox": gearbox}


def _build_control_settings(
    vehicle_type: VehicleType,
    cost_mode: CostMode,
    goals: list[OptimizationGoal],
) -> list[ControlSetting]:
    registry = load_slider_registry()
    goal_weights = {goal.output_key: goal.target_weight for goal in goals}
    influence_weights = build_slider_influence_weights(goal_weights, registry.effects)
    settings: list[ControlSetting] = []
    for slider in list_sliders():
        if slider.scale == "percent":
            raw, reason = _recommend_normalized_value(
                slider,
                vehicle_type,
                cost_mode,
                influence_weights=influence_weights,
            )
            raw = _clamp(raw, 0.0, 1.0)
            display = _display_value(slider, raw)
        else:
            raw, reason = _recommend_dimensional_value(
                slider,
                vehicle_type,
                cost_mode,
                influence_weights=influence_weights,
            )
            raw = _clamp(raw, slider.min_value, slider.max_value)
            display = _display_value(slider, raw)
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
        PredictedOutput("power", "Power", engine.horsepower, weight_by_key.get("engine_horsepower", 0.0), "Predicted from engine formula.", False),
        PredictedOutput("torque", "Torque", engine.torque, weight_by_key.get("engine_torque", 0.0), "Predicted from engine formula.", False),
        PredictedOutput("fuel", "Fuel", engine.fuel_economy, weight_by_key.get("fuel", 0.0), "Predicted from engine formula.", False),
        PredictedOutput("smoothness", "Smoothness", engine.smoothness_rating, weight_by_key.get("luxury", 0.0), "Predicted from engine formula.", False),
        PredictedOutput("reliability", "Reliability", engine.reliability_rating, weight_by_key.get("dependability", 0.0), "Predicted from engine formula.", False),
        PredictedOutput("overall", "Overall", engine.overall_rating, weight_by_key.get("performance", 0.0), "Predicted from engine formula.", False),
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

    controls = _build_control_settings(vehicle_type, cost_mode, goals)
    controls = _apply_selected_choices_to_settings(
        controls,
        input_data.selected_choices,
    )
    grouped, engine_slider_subcomponents = _settings_by_section(controls)
    choice_subcomponents = _subcomponent_values_from_choices(input_data.selected_choices)
    engine_extra = {
        **choice_subcomponents.get("engine", {}),
        **engine_slider_subcomponents,
    }

    chassis_inputs = _chassis_inputs_from_settings(
        grouped.get("chassis", {}),
        year=input_data.year,
        extra=choice_subcomponents.get("chassis", {}),
    )
    engine_inputs = _engine_inputs_from_settings(
        grouped.get("engine", {}),
        year=input_data.year,
        extra=engine_extra,
    )
    gearbox_inputs = _gearbox_inputs_from_settings(
        grouped.get("gearbox", {}),
        year=input_data.year,
        extra=choice_subcomponents.get("gearbox", {}),
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
    return SliderOptimizationResult(
        control_settings=controls,
        predicted_outputs=predicted,
        goals=goals,
        tradeoffs=_build_tradeoffs(vehicle_type, cost_mode, goals),
        warnings=warnings,
        limitations=limitations,
        chassis_result=chassis_result,
        engine_result=engine_result,
        gearbox_result=gearbox_result,
        vehicle_ratings=vehicle_ratings,
        wiki_model_loaded=True,
        optimization_disabled=False,
    )


def control_settings_for_section(
    result: SliderOptimizationResult,
    section: str,
) -> list[ControlSetting]:
    """Return control settings for one section."""
    normalized = section.strip().lower()
    return [item for item in result.control_settings if item.section == normalized]
