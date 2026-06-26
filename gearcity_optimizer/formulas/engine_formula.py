"""Deterministic GearCity engine formulas from wiki pseudo-code.

Assumptions documented in code:
- User slider names map to wiki ``Slider_DesignFocus_*``, ``Slider_Technology_*``,
  and performance sliders derived from design focus.
- Layout sliders are derived from bore/stroke when not supplied separately.
- Cylinder bank arrangement defaults to inline (``SubComponent_Layout_CylinderLengthArrangment = 1``).
- Valve/cylinder/fuel subcomponents are approximated from layout/fuel/aspiration inputs.
- ``ex_1d0105p_year99`` is approximated as ``1.0105 ** (year - 1899)`` (not listed in wiki globals).
- ``design_smoothness`` is not in wiki smoothness formula; a small bonus is added as approximation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, fields, replace
from typing import Any

import pandas as pd

from gearcity_optimizer.core.models import _parse_bool, _parse_optional_float

YEAR_BASE = 1899
ADJUSTED_YEAR_CAP = 121
RPM_TMPAY_CAP = 80


def year_factor(base: float, year: int) -> float:
    """Return ``base ** (year - 1899)`` used by engine wiki formulas."""
    return base ** (year - YEAR_BASE)


def adjusted_year(year: int) -> int:
    """Return wiki AdjustedYear (year - 1899, capped at 121)."""
    return min(year - YEAR_BASE, ADJUSTED_YEAR_CAP)


def ex_0d996p_year50r(year: int) -> float:
    """Torque era multiplier from wiki globals."""
    if year > 2020:
        return 0.901037361
    return 0.996 ** (2050 - year)


def clamp(value: float, min_value: float = 0.0, max_value: float = 100.0) -> float:
    """Clamp a numeric value to an inclusive range."""
    return max(min_value, min(max_value, value))


def bool01(value: bool) -> int:
    """Convert a boolean to 0 or 1."""
    return 1 if value else 0


def validate_slider(name: str, value: float) -> None:
    """Raise ValueError if a slider is outside 0..1."""
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1, got {value}")


def _clamp01(value: float) -> float:
    """Clamp a normalized slider helper to 0..1."""
    return max(0.0, min(1.0, value))


SLIDER_FIELDS = (
    "design_performance",
    "design_fuel_economy",
    "design_dependability",
    "design_smoothness",
    "design_pace",
    "tech_materials",
    "tech_components",
    "tech_techniques",
    "tech_technology",
    "fuel_system_quality",
    "aspiration_quality",
)

SUBCOMPONENT_FIELDS = (
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
)


@dataclass
class EngineFormulaInputs:
    """Inputs for GearCity engine wiki formulas."""

    name: str = "Unnamed Engine"
    year: int = 1901
    cylinders: int = 2
    displacement: float = 800.0
    bore: float | None = None
    stroke: float | None = None
    is_supercharged: bool = False
    is_turbocharged: bool = False
    has_fuel_injection: bool = False
    has_overhead_cam: bool = False
    design_performance: float = 0.5
    design_fuel_economy: float = 0.5
    design_dependability: float = 0.5
    design_smoothness: float = 0.5
    design_pace: float = 0.5
    tech_materials: float = 0.5
    tech_components: float = 0.5
    tech_techniques: float = 0.5
    tech_technology: float = 0.5
    fuel_system_quality: float = 0.5
    aspiration_quality: float = 0.5
    layout_weight: float = 0.3
    layout_width: float = 0.3
    layout_length: float = 0.3
    layout_smoothness: float = 0.3
    layout_reliability: float = 0.3
    layout_performance: float = 0.3
    layout_manufacturing: float = 0.3
    layout_design: float = 0.3
    fuel_system_performance: float = 0.3
    fuel_system_fuel_economy: float = 0.3
    fuel_system_reliability: float = 0.3
    aspiration_performance: float = 0.3
    aspiration_fuel_economy: float = 0.3
    aspiration_reliability: float = 0.3
    marque_design_engine_skill: float = 0.0
    pre_research_engine_amount_effect: float = 0.0
    cylinder_bank_arrangement: int = 1
    wiki_subcomponent_layout_length: float | None = None
    wiki_subcomponent_layout_width: float | None = None
    wiki_slider_layout_length: float | None = None
    wiki_slider_layout_width: float | None = None
    wiki_slider_performance_torque: float | None = None
    wiki_slider_performance_revolutions: float | None = None
    wiki_slider_performance_fuel: float | None = None

    def __post_init__(self) -> None:
        if self.year < YEAR_BASE:
            raise ValueError(f"year must be >= {YEAR_BASE}, got {self.year}")
        if self.cylinders < 1:
            raise ValueError("cylinders must be >= 1")
        if self.displacement <= 0:
            raise ValueError("displacement must be > 0")

        for field_name in SLIDER_FIELDS:
            validate_slider(field_name, getattr(self, field_name))

        for field_name in SUBCOMPONENT_FIELDS:
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} must be non-negative")


@dataclass
class EngineFormulaResult:
    """Computed engine specs and ratings."""

    horsepower: float
    torque: float
    fuel_economy: float
    reliability_rating: float
    smoothness_rating: float
    performance_rating: float
    overall_rating: float
    weight: float
    width: float
    length: float
    design_requirements: float
    manufacturing_requirements: float
    warnings: list[str]
    bore_mm: float = 0.0
    stroke_mm: float = 0.0
    displacement_cc: float = 0.0
    cylinder_count: int = 0
    cylinder_bank_arrangement: int = 1


@dataclass
class _EngineDimensions:
    bore_mm: float
    stroke_mm: float
    displacement_cc: float


@dataclass
class _WikiContext:
    """Resolved wiki variables from simplified user inputs."""

    inputs: EngineFormulaInputs
    dims: _EngineDimensions
    slider_layout_bore: float
    slider_layout_stroke: float
    slider_layout_length: float
    slider_layout_width: float
    slider_layout_displacement: float
    slider_layout_weight: float
    slider_performance_torque: float
    slider_performance_revolutions: float
    slider_performance_fuel_economy: float
    layout_power: float
    layout_fuel: float
    layout_rel: float
    layout_smooth: float
    layout_design: float
    layout_manu: float
    layout_weight_sub: float
    layout_width_sub: float
    layout_length_sub: float
    cylinders_power: float
    cylinders_fuel: float
    cylinders_rel: float
    cylinders_weight: float
    cylinders_smooth: float
    cylinders_design: float
    cylinders_manu: float
    fuel_power: float
    fuel_fuel: float
    fuel_rel: float
    fuel_weight: float
    fuel_rpm: float
    fuel_smooth: float
    fuel_design: float
    fuel_manu: float
    induction_power: float
    induction_fuel: float
    induction_rel: float
    induction_weight: float
    induction_design: float
    induction_manu: float
    valve_power: float
    valve_rpm: float
    valve_fuel: float
    valve_rel: float
    valve_weight: float
    valve_size: float
    valve_smooth: float
    valve_design: float
    valve_manu: float
    forced_induction: bool


def _resolve_dimensions(inputs: EngineFormulaInputs) -> _EngineDimensions:
    """Resolve bore, stroke, and displacement in cc."""
    if inputs.bore is not None and inputs.stroke is not None:
        bore_mm = inputs.bore
        stroke_mm = inputs.stroke
        displacement_cc = (
            0.7854
            * ((bore_mm / 10.0) ** 2)
            * (stroke_mm / 10.0)
            * inputs.cylinders
        )
    else:
        displacement_cc = inputs.displacement
        per_cylinder = displacement_cc / inputs.cylinders
        bore_mm = (per_cylinder * 1000.0 / 0.7854) ** (1.0 / 3.0)
        stroke_mm = bore_mm
    return _EngineDimensions(bore_mm, stroke_mm, displacement_cc)


def _build_wiki_context(inputs: EngineFormulaInputs) -> _WikiContext:
    """Map simplified inputs onto wiki variable names."""
    dims = _resolve_dimensions(inputs)
    forced = inputs.is_supercharged or inputs.is_turbocharged

    norm_bore = _clamp01((dims.bore_mm - 50.0) / 100.0)
    norm_stroke = _clamp01((dims.stroke_mm - 50.0) / 100.0)
    layout_disp = (norm_bore + norm_stroke) / 2.0

    slider_layout_bore = norm_bore
    slider_layout_stroke = norm_stroke
    layout_length_sub = (
        inputs.wiki_subcomponent_layout_length
        if inputs.wiki_subcomponent_layout_length is not None
        else inputs.layout_length
    )
    layout_width_sub = (
        inputs.wiki_subcomponent_layout_width
        if inputs.wiki_subcomponent_layout_width is not None
        else inputs.layout_width
    )
    slider_layout_length = (
        inputs.wiki_slider_layout_length
        if inputs.wiki_slider_layout_length is not None
        else _clamp01(inputs.layout_length * 0.5 + layout_disp * 0.5)
    )
    slider_layout_width = (
        inputs.wiki_slider_layout_width
        if inputs.wiki_slider_layout_width is not None
        else _clamp01(inputs.layout_width * 0.5 + layout_disp * 0.5)
    )
    slider_layout_displacement = layout_disp
    slider_layout_weight = _clamp01(inputs.layout_weight)

    perf_torque = (
        inputs.wiki_slider_performance_torque
        if inputs.wiki_slider_performance_torque is not None
        else _clamp01(inputs.design_performance + 0.15 * bool01(forced))
    )
    perf_rev = (
        inputs.wiki_slider_performance_revolutions
        if inputs.wiki_slider_performance_revolutions is not None
        else _clamp01(inputs.design_performance + 0.1 * bool01(forced))
    )
    perf_fuel = (
        inputs.wiki_slider_performance_fuel
        if inputs.wiki_slider_performance_fuel is not None
        else inputs.design_fuel_economy
    )

    fuel_q = inputs.fuel_system_quality
    asp_q = inputs.aspiration_quality

    valve_power = 0.82 + 0.12 * bool01(inputs.has_overhead_cam) + 0.06 * bool01(
        inputs.has_fuel_injection
    )
    valve_rpm = 0.80 + 0.15 * bool01(inputs.has_overhead_cam)
    valve_size = 0.20 + 0.20 * bool01(inputs.has_overhead_cam)

    induction_power = inputs.aspiration_performance * asp_q
    if forced:
        induction_power = _clamp01(induction_power * 1.8 + 0.25)

    return _WikiContext(
        inputs=inputs,
        dims=dims,
        slider_layout_bore=slider_layout_bore,
        slider_layout_stroke=slider_layout_stroke,
        slider_layout_length=slider_layout_length,
        slider_layout_width=slider_layout_width,
        slider_layout_displacement=slider_layout_displacement,
        slider_layout_weight=slider_layout_weight,
        slider_performance_torque=perf_torque,
        slider_performance_revolutions=perf_rev,
        slider_performance_fuel_economy=perf_fuel,
        layout_power=inputs.layout_performance,
        layout_fuel=inputs.fuel_system_fuel_economy * fuel_q,
        layout_rel=inputs.layout_reliability,
        layout_smooth=inputs.layout_smoothness,
        layout_design=inputs.layout_design,
        layout_manu=inputs.layout_manufacturing,
        layout_weight_sub=inputs.layout_weight,
        layout_width_sub=layout_width_sub,
        layout_length_sub=layout_length_sub,
        cylinders_power=inputs.layout_performance,
        cylinders_fuel=inputs.fuel_system_fuel_economy * fuel_q,
        cylinders_rel=inputs.layout_reliability,
        cylinders_weight=inputs.layout_weight,
        cylinders_smooth=inputs.layout_smoothness,
        cylinders_design=inputs.layout_design,
        cylinders_manu=inputs.layout_manufacturing,
        fuel_power=inputs.fuel_system_performance * fuel_q,
        fuel_fuel=_clamp01(
            inputs.fuel_system_fuel_economy * fuel_q + 0.08 * bool01(inputs.has_fuel_injection)
        ),
        fuel_rel=inputs.fuel_system_reliability * fuel_q,
        fuel_weight=inputs.layout_weight * 0.15,
        fuel_rpm=0.75 + 0.25 * inputs.design_performance,
        fuel_smooth=inputs.layout_smoothness * 0.8,
        fuel_design=inputs.layout_design * 0.6,
        fuel_manu=inputs.layout_manufacturing * 0.5,
        induction_power=induction_power,
        induction_fuel=inputs.aspiration_fuel_economy * asp_q,
        induction_rel=inputs.aspiration_reliability * asp_q,
        induction_weight=0.20 + 0.30 * asp_q if forced else 0.08,
        induction_design=inputs.layout_design * 0.4,
        induction_manu=inputs.layout_manufacturing * 0.4,
        valve_power=valve_power,
        valve_rpm=valve_rpm,
        valve_fuel=inputs.fuel_system_fuel_economy * fuel_q * 0.8,
        valve_rel=inputs.fuel_system_reliability * fuel_q * 0.7,
        valve_weight=0.22 + 0.10 * bool01(inputs.has_overhead_cam),
        valve_size=valve_size,
        valve_smooth=inputs.layout_smoothness * 0.5 + inputs.design_smoothness * 0.3,
        valve_design=inputs.layout_design * 0.5,
        valve_manu=inputs.layout_manufacturing * 0.5,
        forced_induction=forced,
    )


def calculate_displacement_cc(ctx: _WikiContext) -> float:
    """Return engine displacement in cc."""
    return ctx.dims.displacement_cc


def _length_banks_factor(arrangement: int) -> float:
    """Bank factor for the multi-bank engine length formula.

    Wiki text uses ``1 / arrangement`` when arrangement > 0, but save-game
    calibration shows the game floors this at 0.5 (W-15 length matches ~56 in
    with arrangement=3 only when banks=0.5, not 1/3).
    """
    if arrangement <= 0:
        return 0.5
    return max(0.5, 1.0 / float(arrangement))


def _width_arrangement_scale(arrangement: int) -> float:
    """Scale width for wide multi-bank layouts (save-calibrated)."""
    if arrangement <= 2:
        return 1.0
    return math.sqrt(2.0 / float(arrangement))


def calculate_engine_length(ctx: _WikiContext) -> float:
    """Calculate engine length in inches (wiki Length formula)."""
    inputs = ctx.inputs
    arrangement = inputs.cylinder_bank_arrangement
    bore_mm = ctx.dims.bore_mm
    disp = ctx.dims.displacement_cc
    cylinders = inputs.cylinders
    layout_len_sub = ctx.layout_length_sub
    slider_len = ctx.slider_layout_length
    valve_size = ctx.valve_size

    if arrangement == 1:
        length = (3.0 + (disp / (47.3 + 277.0))) * layout_len_sub
        length += cylinders * (bore_mm / 130.0)
        length += cylinders + (5.0 * (bore_mm / 130.0)) + 2.0 * valve_size
        length += 0.16 * length * slider_len
        return length

    if arrangement <= -1:
        bank = arrangement * -1
        length = 3.0 + (0.039 * (bore_mm * 2.0)) + 5.0 * slider_len
        return length * bank

    banks = _length_banks_factor(arrangement)
    length = (4.0 + ((disp * (banks * 2.0)) / (47.3 + 277.0))) * layout_len_sub
    length += (cylinders * banks) * (bore_mm / 130.0)
    length += (cylinders * (banks * 2.0)) + (5.0 * (bore_mm / 130.0)) + 2.0 * valve_size
    length += 0.16 * length * slider_len
    return length


def calculate_engine_width(ctx: _WikiContext) -> float:
    """Calculate engine width in inches (wiki Width formula)."""
    inputs = ctx.inputs
    disp = ctx.dims.displacement_cc
    bore_mm = ctx.dims.bore_mm
    arrangement = inputs.cylinder_bank_arrangement

    width = (6.0 + (disp / (57.3 + 302.0))) * ctx.layout_width_sub
    width += (6.0 * (bore_mm / 115.0)) + 5.0 * ctx.valve_size
    width += 0.16 * width * ctx.slider_layout_width
    width *= _width_arrangement_scale(arrangement)

    if arrangement < -1:
        bank = 1.0 / (arrangement * -1.0)
        width *= bank
    return width


def calculate_torque(ctx: _WikiContext) -> float:
    """Calculate engine torque in lb-ft (wiki Torque formula)."""
    inputs = ctx.inputs
    year = inputs.year
    y01 = year_factor(1.01, year)
    y005 = year_factor(1.005, year)
    y004 = year_factor(1.004, year)
    y0024 = year_factor(1.0024, year)

    torque = 10.0 + inputs.marque_design_engine_skill / 20.0
    inner = (
        25.0 * ((ctx.slider_performance_torque - 0.4) * 1.5) * y01
        + (4.0 * (ctx.layout_length_sub + ctx.layout_width_sub)) * y005
        - 14.0
        * (ctx.slider_performance_fuel_economy + inputs.design_fuel_economy)
        * y004
        + ctx.layout_power * 5.0
        + ctx.cylinders_power * 13.0
        + ctx.fuel_power * 24.0
        + 100.0 * ctx.induction_power
        + 5.0 * y004 * inputs.design_performance
        + 8.0
        * (
            inputs.tech_components
            + inputs.tech_materials
            + inputs.tech_technology
            + inputs.tech_techniques
        )
    ) * y0024
    torque += inner

    scale = (
        inputs.cylinders * ctx.dims.stroke_mm * 0.93 * ctx.dims.bore_mm * 0.9
    ) * 0.000027 + 5.0
    torque *= scale

    if year < 2050:
        torque *= ex_0d996p_year50r(year)

    torque *= ctx.valve_power
    return max(torque, 0.0)


def calculate_rpm(ctx: _WikiContext) -> float:
    """Calculate engine RPM (wiki RPM formula)."""
    inputs = ctx.inputs
    year = inputs.year
    ay = adjusted_year(year)
    tmp_ay = ay
    if tmp_ay > RPM_TMPAY_CAP:
        tmp_ay = RPM_TMPAY_CAP + ((ay - RPM_TMPAY_CAP) / 5.0)

    y01 = year_factor(1.01, year)
    y0105 = year_factor(1.0105, year)  # TODO: verify ex_1d0105p_year99 constant
    y005 = year_factor(1.005, year)

    rpm = (
        (tmp_ay**4) * 0.00000420875
        - (19.0 * (tmp_ay**3)) * 0.00016835
        + (427.0 * (tmp_ay**2)) * 0.00126
        + (1315.0 * tmp_ay) * 0.01515
        + 620.0
        + 265.0 * y01 * inputs.design_performance
        + 465.0 * y0105 * (ctx.slider_performance_revolutions * 5.5)
        - 10.0 * y01 * ctx.induction_power
        + 55.0 * y005 * (1.0 - ctx.slider_layout_weight)
        - 30.0
        * y005
        * (inputs.design_fuel_economy + ctx.slider_performance_fuel_economy)
        + 25.0 * y01 * inputs.tech_components
        + 25.0 * y01 * inputs.tech_materials
        + 25.0 * y01 * inputs.tech_technology
    ) * ctx.fuel_rpm

    rpm *= ctx.valve_rpm
    rpm -= (rpm / 1.5) * (ctx.dims.stroke_mm / 221.136364)
    return max(rpm, 25.0)


def calculate_horsepower(torque: float, rpm: float) -> float:
    """Calculate horsepower from torque and rpm."""
    return (torque * rpm) / 5252.0


def calculate_engine_weight(ctx: _WikiContext, length: float, width: float) -> float:
    """Calculate engine weight in lbs (wiki Weight formula)."""
    inputs = ctx.inputs
    sub_avg = (
        ctx.valve_weight
        + ctx.layout_weight_sub
        + ctx.fuel_weight
        + ctx.induction_weight
        + ctx.cylinders_weight
    ) / 5.0

    weight = 30.0 + 55.0 * sub_avg + 100.0 * (ctx.dims.stroke_mm / 80.0)
    inner = (
        40.0
        + 42.0 * (((ctx.slider_layout_width + ctx.slider_layout_length) / 2.0) + 0.05)
        + (15.0 + 15.0 * sub_avg) * (ctx.slider_layout_weight + 0.1)
        - 15.0 * inputs.tech_materials
        + 5.0 * ctx.induction_weight
        + 8.0 * (ctx.slider_layout_width + ctx.slider_layout_length)
    )
    weight += (length * 1.95 * width) / 80.0 + inner * ((length * 1.78 * width) / 800.0)
    weight += (5.0 + 5.0 * ctx.cylinders_weight) * inputs.cylinders

    if inputs.cylinder_bank_arrangement > 2:
        weight *= inputs.cylinder_bank_arrangement / 2.9
    return weight


def calculate_fuel_consumption_mpg(ctx: _WikiContext) -> float:
    """Calculate fuel consumption MPG (wiki Fuel Consumption formula)."""
    inputs = ctx.inputs
    year = inputs.year
    y0023 = year_factor(1.0023, year)
    y0051 = year_factor(1.0051, year)
    disp = ctx.dims.displacement_cc

    mpg = 95.0 + (
        55.0 * y0023 * (ctx.slider_performance_fuel_economy + 0.1)
        + 40.0 * y0023 * inputs.design_fuel_economy
    )
    mpg += 12.0 * y0023 * ctx.fuel_fuel + 7.0 * y0023 * inputs.tech_technology
    mpg -= (
        15.0
        * y0051
        * (
            ctx.slider_performance_torque
            + ctx.slider_performance_revolutions
            + inputs.design_performance
        )
        + 20.0 * ctx.slider_layout_displacement
        + 10.0 * ctx.valve_fuel
    )
    mpg = (
        mpg
        + 6.0 * ctx.cylinders_fuel
        + 6.0 * ctx.layout_fuel
    ) * ctx.induction_fuel + inputs.marque_design_engine_skill / 50.0

    divisor = 1.5 + disp / 350.0
    if divisor > 0:
        mpg /= divisor
    mpg += 5.0

    if mpg < 1.0:
        mpg = 1.0

    # Wiki uses game-scale fuel ratings; approximate cap branch when fuel rating is low.
    fuel_rating_scaled = ctx.fuel_fuel * 5.0
    if fuel_rating_scaled < 5.0 and mpg > 30.0:
        if fuel_rating_scaled > 1.5 and mpg > (30.0 + fuel_rating_scaled * 2.0):
            mpg = mpg - (mpg**0.85) + 18.0 + fuel_rating_scaled * 2.0
        else:
            mpg = mpg - (mpg**0.85) + 18.0

    return mpg


def calculate_fuel_economy_rating(mpg: float) -> float:
    """Calculate fuel economy rating 0..100 from MPG."""
    return clamp((mpg / 120.0) * 100.0)


def calculate_power_rating(torque: float, ctx: _WikiContext) -> float:
    """Calculate power/performance rating (wiki Power Ratings formula)."""
    if ctx.inputs.cylinders <= 0:
        return 0.0
    year = ctx.inputs.year
    y007 = year_factor(1.007, year)
    power = torque / (
        (100.0 * y007) * ctx.inputs.cylinders / 2.2
    )
    power *= 50.0
    if power > 50.0:
        power = 50.0
    power += 50.0 * (torque / 2000.0)
    return clamp(power)


def calculate_reliability_rating(ctx: _WikiContext, rpm: float) -> float:
    """Calculate reliability rating (wiki Reliability formula)."""
    inputs = ctx.inputs
    rating = (
        6.0 * inputs.design_dependability
        + 3.0 * (1.0 - inputs.design_performance)
        + 5.0 * (1.0 - (rpm / 10000.0))
        + 2.0 * (1.0 - ctx.slider_performance_torque)
        + 3.0 * (1.0 - ctx.slider_performance_revolutions)
        + 3.0 * inputs.tech_components
        + 2.0 * inputs.tech_materials
        + (1.0 - inputs.tech_technology)
        + inputs.tech_techniques
    )
    rating += (
        ctx.cylinders_rel
        + ctx.fuel_rel
        + (1.0 - ctx.induction_rel)
        + ctx.layout_rel
        + 2.0 * ctx.valve_rel
    )
    rating += 8.0 * (1.0 - (ctx.dims.stroke_mm / 150.0))
    rating = rating / 4.5 * 10.0 + inputs.marque_design_engine_skill / 10.0
    return clamp(rating)


def calculate_smoothness_rating(ctx: _WikiContext) -> float:
    """Calculate smoothness rating (wiki Smoothness formula + design_smoothness bonus)."""
    inputs = ctx.inputs
    cylinders = inputs.cylinders
    rating = -(1.0 / 10.0) * ((cylinders - 8) ** 2) + 5.0
    rating += ctx.cylinders_smooth * 2.0
    rating += ctx.fuel_smooth * 2.0
    rating += ctx.layout_smooth * 2.0
    rating += inputs.tech_components * 3.0
    rating += inputs.tech_technology * 2.0
    rating += inputs.tech_techniques * 3.0
    rating += ctx.valve_smooth * 2.0
    rating += inputs.marque_design_engine_skill / 25.0
    # Approximation: design_smoothness is not in wiki pseudo-code.
    rating += inputs.design_smoothness * 5.0
    rating *= 4.0
    return clamp(max(rating, 1.0))


def calculate_overall_rating(
    reliability: float,
    fuel_economy: float,
    power_rating: float,
    smoothness: float,
    inputs: EngineFormulaInputs,
) -> float:
    """Calculate overall engine rating (wiki Overall formula)."""
    overall = (
        reliability
        + fuel_economy
        + power_rating
        + smoothness
        + inputs.marque_design_engine_skill
    ) / 5.0
    overall += 5.0 * inputs.pre_research_engine_amount_effect
    return clamp(overall)


def calculate_design_requirements(ctx: _WikiContext) -> float:
    """Calculate design requirements (wiki Design Requirements formula)."""
    inputs = ctx.inputs
    design_req = (
        5.0 * inputs.design_dependability
        + 5.0 * inputs.design_fuel_economy
        + 5.0 * inputs.design_performance
        + 3.0 * ctx.slider_performance_revolutions
        + 2.0 * ctx.slider_performance_fuel_economy
        + 2.0 * ctx.slider_performance_torque
        + 2.0 * inputs.tech_technology
        + (1.0 - ctx.slider_layout_weight)
        + (
            ctx.slider_layout_displacement
            + (1.0 - ctx.slider_layout_length)
            + (1.0 - ctx.slider_layout_width)
        )
        - 2.0 * inputs.tech_techniques
    )
    design_req += (
        ctx.cylinders_design
        + ctx.fuel_design
        + ctx.valve_design
        + 5.0 * ctx.induction_design
        + 3.0 * ctx.layout_design
    )
    return 2.7027 * design_req


def calculate_manufacturing_requirements(ctx: _WikiContext) -> float:
    """Calculate manufacturing requirements (wiki Manufacturing Requirements formula)."""
    inputs = ctx.inputs
    manufacturing = (
        ctx.slider_layout_displacement
        + 2.0 * (1.0 - ctx.slider_layout_length)
        + 2.0 * (1.0 - ctx.slider_layout_width)
        + ctx.slider_performance_fuel_economy
        + ctx.slider_performance_revolutions * 2.0
        + 2.0 * ctx.slider_performance_torque
        + inputs.tech_components
        + inputs.tech_materials
        + inputs.tech_technology
        + 3.0 * inputs.tech_techniques
    )
    manufacturing += (
        3.0 * ctx.cylinders_manu
        + 3.0 * ctx.layout_manu
        + 2.0 * ctx.induction_manu
        + ctx.fuel_manu
        + 2.0 * ctx.valve_manu
    )
    return manufacturing * 3.7037


def _collect_warnings(
    inputs: EngineFormulaInputs,
    result: EngineFormulaResult,
) -> list[str]:
    """Build practical warnings for an engine design."""
    warnings: list[str] = []
    if result.horsepower < 10.0:
        warnings.append("Horsepower is very low; engine may be underpowered.")
    if result.torque < 25.0:
        warnings.append("Torque is very low; engine may struggle to move vehicles.")
    if result.reliability_rating < 20.0:
        warnings.append("Reliability rating is very low.")
    if inputs.design_smoothness > 0.5 and result.smoothness_rating < 20.0:
        warnings.append(
            "Smoothness rating is very low for a smoothness-oriented design."
        )
    if inputs.year <= 1920 and result.weight > 200.0:
        warnings.append(
            "Engine is very heavy for early years; may limit vehicle options."
        )
    if inputs.year < 1920 and (inputs.is_supercharged or inputs.is_turbocharged):
        warnings.append(
            "Forced induction is uncommon this early; verify it is intentional."
        )
    return warnings


def calculate_engine(inputs: EngineFormulaInputs) -> EngineFormulaResult:
    """Calculate all implemented engine specs and ratings."""
    ctx = _build_wiki_context(inputs)
    length = calculate_engine_length(ctx)
    width = calculate_engine_width(ctx)
    weight = calculate_engine_weight(ctx, length, width)
    torque = calculate_torque(ctx)
    rpm = calculate_rpm(ctx)
    horsepower = calculate_horsepower(torque, rpm)
    mpg = calculate_fuel_consumption_mpg(ctx)
    fuel_economy = calculate_fuel_economy_rating(mpg)
    performance = calculate_power_rating(torque, ctx)
    reliability = calculate_reliability_rating(ctx, rpm)
    smoothness = calculate_smoothness_rating(ctx)
    overall = calculate_overall_rating(
        reliability, fuel_economy, performance, smoothness, inputs
    )
    design = calculate_design_requirements(ctx)
    manufacturing = calculate_manufacturing_requirements(ctx)

    result = EngineFormulaResult(
        horsepower=horsepower,
        torque=torque,
        fuel_economy=fuel_economy,
        reliability_rating=reliability,
        smoothness_rating=smoothness,
        performance_rating=performance,
        overall_rating=overall,
        weight=weight,
        width=width,
        length=length,
        design_requirements=design,
        manufacturing_requirements=manufacturing,
        bore_mm=ctx.dims.bore_mm,
        stroke_mm=ctx.dims.stroke_mm,
        displacement_cc=ctx.dims.displacement_cc,
        cylinder_count=inputs.cylinders,
        cylinder_bank_arrangement=inputs.cylinder_bank_arrangement,
        warnings=[],
    )
    result.warnings = _collect_warnings(inputs, result)
    return result


def _row_to_inputs(row: pd.Series) -> EngineFormulaInputs:
    """Convert one CSV row to engine formula inputs."""
    kwargs: dict[str, Any] = {"name": str(row["name"])}
    for field in fields(EngineFormulaInputs):
        if field.name == "name":
            continue
        raw = row.get(field.name)
        if field.name.startswith("wiki_"):
            continue
        if raw is None or (isinstance(raw, float) and pd.isna(raw)):
            continue
        if field.type is bool or field.type == "bool":
            kwargs[field.name] = _parse_bool(raw)
        elif field.type is int:
            kwargs[field.name] = int(raw)
        elif field.name in ("bore", "stroke"):
            kwargs[field.name] = _parse_optional_float(raw)
        else:
            kwargs[field.name] = float(raw)
    return EngineFormulaInputs(**kwargs)


def load_engine_formula_inputs(path: str) -> list[EngineFormulaInputs]:
    """Load engine formula input rows from CSV."""
    df = pd.read_csv(path)
    return [_row_to_inputs(row) for _, row in df.iterrows()]


def export_engine_candidates_csv(
    inputs_list: list[EngineFormulaInputs],
    output_path: str,
    year_override: int | None = None,
) -> None:
    """Export formula results to package-optimizer-compatible engine CSV."""
    records = []
    for inputs in inputs_list:
        if year_override is not None:
            inputs = replace(inputs, year=year_override)
        result = calculate_engine(inputs)
        records.append(
            {
                "name": inputs.name,
                "horsepower": round(result.horsepower, 2),
                "torque": round(result.torque, 2),
                "fuel_economy": round(result.fuel_economy, 2),
                "reliability": round(result.reliability_rating, 2),
                "smoothness": round(result.smoothness_rating, 2),
                "overall": round(result.overall_rating, 2),
                "unit_cost": 0,
                "design_cost": 0,
                "weight": round(result.weight, 2),
                "width": round(result.width, 2),
                "length": round(result.length, 2),
                "notes": "generated from engine formula",
            }
        )
    pd.DataFrame(records).to_csv(output_path, index=False)
