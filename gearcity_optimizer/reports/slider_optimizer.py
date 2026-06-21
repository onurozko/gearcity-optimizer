"""Optimize real GearCity slider settings and predict output stats via formulas."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Literal

from gearcity_optimizer.core.component_priorities import get_adjusted_vehicle_weights
from gearcity_optimizer.core.cost_mode import CostMode, parse_cost_mode
from gearcity_optimizer.core.models import VehicleType
from gearcity_optimizer.core.slider_registry import RealSlider, get_slider, list_sliders
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
from gearcity_optimizer.importers.components_xml import validate_year_input
from gearcity_optimizer.reports.part_recommender import is_work_or_utility_focused

OptimizationDepth = Literal["quick", "balanced", "thorough"]

LUXURY_SLIDER_KEYS = frozenset(
    {
        "design_smoothness",
        "luxury_focus",
        "style_focus",
        "material_quality",
        "tech_materials",
        "tech_technology",
        "tech_material",
        "sus_comfort",
    }
)

COST_SLIDER_KEYS = frozenset(
    {
        "design_pace",
        "tech_materials",
        "tech_technology",
        "tech_components",
        "tech_techniques",
        "tech_material",
        "material_quality",
        "style_focus",
    }
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
) -> tuple[float, str]:
    weights = get_adjusted_vehicle_weights(vehicle_type)
    key = slider.field_name

    mapping: dict[str, tuple[str, str]] = {
        "design_fuel_economy": ("fuel", "Fuel economy priority"),
        "design_dependability": ("dependability", "Dependability priority"),
        "design_performance": ("performance", "Performance priority"),
        "design_smoothness": ("luxury", "Luxury/smoothness priority"),
        "design_strength": ("safety", "Safety/strength priority"),
        "design_control": ("drivability", "Drivability/control priority"),
        "design_ease": ("dependability", "Ease/manufacturing priority"),
        "sus_comfort": ("luxury", "Comfort/luxury priority"),
        "sus_performance": ("performance", "Performance priority"),
        "sus_durability": ("dependability", "Durability priority"),
        "sus_braking": ("safety", "Safety/braking priority"),
        "sus_stability": ("drivability", "Stability/drivability priority"),
        "fd_weight": ("fuel", "Weight vs cargo/fuel tradeoff"),
        "fd_length": ("cargo", "Cargo/length priority"),
        "torque_max_input": ("power", "Power/torque support priority"),
        "low_gear_ratio": ("power", "Low-end torque priority"),
        "high_gear_ratio": ("fuel", "High-speed fuel economy priority"),
        "safety_focus": ("safety", "Vehicle safety focus"),
        "dependability_focus": ("dependability", "Vehicle dependability focus"),
        "cargo_focus": ("cargo", "Vehicle cargo focus"),
        "luxury_focus": ("luxury", "Vehicle luxury focus"),
        "style_focus": ("luxury", "Vehicle style focus"),
        "material_quality": ("quality", "Material quality priority"),
        "testing_reliability": ("dependability", "Reliability testing priority"),
        "testing_fuel": ("fuel", "Fuel testing priority"),
        "testing_performance": ("performance", "Performance testing priority"),
        "testing_utility": ("cargo", "Utility testing priority"),
        "tech_materials": ("dependability", "Materials tech level"),
        "tech_components": ("performance", "Components tech level"),
        "tech_techniques": ("fuel", "Techniques tech level"),
        "tech_technology": ("performance", "Technology level"),
        "tech_material": ("dependability", "Gearbox material tech"),
        "fuel_system_quality": ("fuel", "Fuel system quality"),
        "aspiration_quality": ("performance", "Aspiration quality"),
        "design_pace": ("dependability", "Design pace vs cost"),
    }

    if key in mapping:
        weight_key, reason_prefix = mapping[key]
        weight = weights.get(weight_key, 0.35)
        if weight_key == "quality":
            weight = 0.45
        value = _cost_mode_scale(key, _priority(weight), cost_mode, vehicle_type=vehicle_type)
        return round(value, 3), f"{reason_prefix} for {vehicle_type.name}."

    value = _cost_mode_scale(key, 0.45, cost_mode, vehicle_type=vehicle_type)
    return round(value, 3), f"Balanced default for {vehicle_type.name}."


def _recommend_dimensional_value(
    slider: RealSlider,
    vehicle_type: VehicleType,
    cost_mode: CostMode,
    year: int,
) -> tuple[float, str]:
    weights = get_adjusted_vehicle_weights(vehicle_type)
    perf = weights.get("performance", 0.0)
    power = weights.get("power", 0.0)
    fuel = weights.get("fuel", 0.0)

    if slider.field_name == "bore":
        value = 58.0 + 22.0 * _priority(max(perf, power))
        if cost_mode is CostMode.CHEAP:
            value -= 6.0
        return round(_clamp(value, slider.min_value, slider.max_value), 1), (
            "Sized from performance/power priority; affects displacement and torque."
        )
    if slider.field_name == "stroke":
        value = 60.0 + 20.0 * _priority(power) - 8.0 * _priority(fuel)
        return round(_clamp(value, slider.min_value, slider.max_value), 1), (
            "Longer stroke favors torque; shorter stroke favors RPM/fuel economy."
        )
    if slider.field_name == "displacement":
        cylinders = 4
        value = 800.0 + 350.0 * _priority(power) + 200.0 * _priority(perf)
        if cost_mode is CostMode.CHEAP:
            value *= 0.85
        return round(_clamp(value, slider.min_value, slider.max_value), 0), (
            "Displacement scales with power needs when bore/stroke are not fixed."
        )
    if slider.field_name == "cylinders":
        if power >= 0.65 or perf >= 0.75:
            value = 6.0
        elif power >= 0.45:
            value = 4.0
        elif year < 1905 or cost_mode is CostMode.CHEAP:
            value = 2.0
        else:
            value = 4.0
        return value, "Cylinder count based on era, cost mode, and power needs."
    if slider.field_name == "number_of_gears":
        if year < 1912:
            value = 2.0 if cost_mode is CostMode.CHEAP else 3.0
        elif cost_mode is CostMode.LUXURY:
            value = 4.0
        else:
            value = 3.0
        return value, "Gear count based on year and cost mode."
    if slider.field_name.startswith("has_") or slider.field_name.startswith("is_"):
        enabled = False
        if slider.field_name == "has_reverse":
            enabled = True
        elif slider.field_name in {"has_overdrive"} and cost_mode is not CostMode.CHEAP and year >= 1930:
            enabled = True
        elif slider.field_name == "has_limited_slip" and perf >= 0.65:
            enabled = True
        elif slider.field_name in {"is_supercharged", "is_turbocharged"} and year >= 1920 and perf >= 0.75:
            enabled = False if cost_mode is CostMode.CHEAP else False
        elif slider.field_name == "has_fuel_injection" and year >= 1950:
            enabled = cost_mode is not CostMode.CHEAP
        elif slider.field_name == "has_overhead_cam" and year >= 1910 and cost_mode is not CostMode.CHEAP:
            enabled = perf >= 0.45 or weights.get("luxury", 0.0) >= 0.45
        value = 1.0 if enabled else 0.0
        return value, "Feature enabled only when era and priorities justify the complexity."

    return slider.default_value, "Default registry value."


def _display_value(slider: RealSlider, raw: float) -> float:
    if slider.max_value <= 1.0 and slider.min_value >= 0.0 and slider.field_name not in {
        "cylinders",
        "number_of_gears",
    } and not slider.field_name.startswith(("has_", "is_")):
        return round(raw * 100.0, 1)
    if slider.field_name in {"cylinders", "number_of_gears"}:
        return float(int(round(raw)))
    if slider.field_name.startswith(("has_", "is_")):
        return float(int(round(raw)))
    return round(raw, 1)


def _build_control_settings(
    vehicle_type: VehicleType,
    cost_mode: CostMode,
    year: int,
) -> list[ControlSetting]:
    settings: list[ControlSetting] = []
    for slider in list_sliders():
        if slider.max_value <= 1.0 and slider.min_value >= 0.0 and slider.field_name not in {
            "cylinders",
            "number_of_gears",
        } and not slider.field_name.startswith(("has_", "is_")):
            raw, reason = _recommend_normalized_value(slider, vehicle_type, cost_mode)
        else:
            raw, reason = _recommend_dimensional_value(
                slider, vehicle_type, cost_mode, year
            )
        raw = _clamp(raw, slider.min_value, slider.max_value)
        settings.append(
            ControlSetting(
                slider_key=slider.key,
                label=slider.label,
                section=slider.section,
                value=_display_value(slider, raw),
                reason=reason,
                confidence=slider.confidence,
                formula_variable=slider.formula_variable,
            )
        )
    return settings


def _settings_by_section(settings: list[ControlSetting]) -> dict[str, dict[str, float]]:
    grouped: dict[str, dict[str, float]] = {
        "chassis": {},
        "engine": {},
        "gearbox": {},
        "vehicle": {},
        "testing": {},
    }
    for setting in settings:
        slider = get_slider(setting.slider_key)
        if slider is None:
            continue
        raw = setting.value
        if slider.max_value <= 1.0 and slider.min_value >= 0.0 and slider.field_name not in {
            "cylinders",
            "number_of_gears",
        } and not slider.field_name.startswith(("has_", "is_")):
            raw = raw / 100.0
        grouped.setdefault(setting.section, {})[slider.field_name] = raw
    return grouped


def _chassis_inputs_from_settings(
    values: dict[str, float],
    *,
    year: int,
) -> ChassisFormulaInputs:
    kwargs: dict[str, object] = {"year": year, "name": "Optimized Chassis"}
    for field in fields(ChassisFormulaInputs):
        if field.name in {"name", "year"}:
            continue
        if field.name in values:
            kwargs[field.name] = values[field.name]
    return ChassisFormulaInputs(**kwargs)


def _engine_inputs_from_settings(
    values: dict[str, float],
    *,
    year: int,
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
    if "bore" in values and "stroke" in values:
        kwargs["bore"] = float(values["bore"])
        kwargs["stroke"] = float(values["stroke"])
    return EngineFormulaInputs(**kwargs)


def _gearbox_inputs_from_settings(
    values: dict[str, float],
    *,
    year: int,
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
        PredictedOutput("engine_torque", "Engine torque", engine.torque, weight_by_key.get("engine_torque", 0.0), "From engine formula.", False),
        PredictedOutput("engine_horsepower", "Engine horsepower", engine.horsepower, weight_by_key.get("engine_horsepower", 0.0), "From engine formula.", False),
        PredictedOutput("engine_fuel_economy_rating", "Engine fuel economy rating", engine.fuel_economy, weight_by_key.get("fuel", 0.0), "From engine formula.", False),
        PredictedOutput("engine_reliability_rating", "Engine reliability rating", engine.reliability_rating, weight_by_key.get("dependability", 0.0), "From engine formula.", False),
        PredictedOutput("engine_smoothness_rating", "Engine smoothness rating", engine.smoothness_rating, weight_by_key.get("luxury", 0.0), "From engine formula.", False),
        PredictedOutput("chassis_comfort_rating", "Chassis comfort rating", chassis.comfort_rating, weight_by_key.get("luxury", 0.0), "From chassis formula.", False),
        PredictedOutput("chassis_strength_rating", "Chassis strength rating", chassis.strength_rating, weight_by_key.get("safety", 0.0), "From chassis formula.", False),
        PredictedOutput("chassis_durability_rating", "Chassis durability rating", chassis.durability_rating, weight_by_key.get("dependability", 0.0), "From chassis formula.", False),
        PredictedOutput("gearbox_max_torque_support", "Gearbox max torque support", gearbox.max_torque_support, weight_by_key.get("gearbox_max_torque_support", 0.0), "From gearbox formula.", False),
        PredictedOutput("gearbox_fuel_economy_rating", "Gearbox fuel economy rating", gearbox.fuel_economy_rating, weight_by_key.get("fuel", 0.0), "From gearbox formula.", False),
        PredictedOutput("vehicle_performance", "Vehicle performance (proxy)", vehicle.performance, weight_by_key.get("performance", 0.0), "Proxy assembly from component ratings.", True),
        PredictedOutput("vehicle_drivability", "Vehicle drivability (proxy)", vehicle.drivability, weight_by_key.get("drivability", 0.0), "Proxy assembly from component ratings.", True),
        PredictedOutput("vehicle_luxury", "Vehicle luxury (proxy)", vehicle.luxury, weight_by_key.get("luxury", 0.0), "Proxy assembly from component ratings.", True),
        PredictedOutput("vehicle_safety", "Vehicle safety (proxy)", vehicle.safety, weight_by_key.get("safety", 0.0), "Proxy assembly from component ratings.", True),
        PredictedOutput("vehicle_fuel", "Vehicle fuel economy (proxy)", vehicle.fuel, weight_by_key.get("fuel", 0.0), "Proxy assembly from component ratings.", True),
        PredictedOutput("vehicle_power", "Vehicle power (proxy)", vehicle.power, weight_by_key.get("power", 0.0), "Proxy assembly from component ratings.", True),
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
            "Torque max input and low gear ratio are kept high enough for work-focused "
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
    controls = _build_control_settings(vehicle_type, cost_mode, input_data.year)
    grouped = _settings_by_section(controls)

    chassis_inputs = _chassis_inputs_from_settings(grouped.get("chassis", {}), year=input_data.year)
    engine_inputs = _engine_inputs_from_settings(grouped.get("engine", {}), year=input_data.year)
    gearbox_inputs = _gearbox_inputs_from_settings(grouped.get("gearbox", {}), year=input_data.year)

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
    limitations = [
        "These are model-optimized settings from the current formula/proxy model. "
        "They are not guaranteed hidden game-code perfection.",
        "Vehicle/coachwork and testing sliders use proxy influence until full vehicle "
        "body formulas are wired in.",
        "Components.xml tech choices are not auto-selected yet; inspect available tech "
        "separately in the Tech Availability tables.",
    ]
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
    )


def control_settings_for_section(
    result: SliderOptimizationResult,
    section: str,
) -> list[ControlSetting]:
    """Return control settings for one section."""
    normalized = section.strip().lower()
    return [item for item in result.control_settings if item.section == normalized]
