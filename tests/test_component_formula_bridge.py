"""Tests for Components.xml to formula bridge mapping."""

from __future__ import annotations

from gearcity_optimizer.importers.components_xml import parse_components_xml  # noqa: F401

from gearcity_optimizer.core.component_formula_bridge import (
    DEFAULT_COMPONENT_RATING,
    FORMULA_SUBCOMPONENT_DEFAULT,
    component_rating,
    formula_subcomponent_value,
    subcomponent_values_from_choices,
)
from gearcity_optimizer.importers.component_choices import ComponentChoice


def _choice(name: str, choice_type: str, **stats: float) -> ComponentChoice:
    return ComponentChoice(
        id=name,
        name=name,
        display_name=name,
        section="engine",
        choice_type=choice_type,
        start_year=1890,
        end_year=5050,
        required_skill=0.0,
        stats=dict(stats),
        raw_attributes={"picture": f"{name}.dds"},
        source_path="test",
        confidence="high",
    )


def test_component_rating_defaults_when_stats_missing():
    assert component_rating({}) == DEFAULT_COMPONENT_RATING


def test_formula_subcomponent_value_scales_game_ratings_to_zero_one():
    assert formula_subcomponent_value({"performance": 42.0}) == 0.42
    assert formula_subcomponent_value({}) == FORMULA_SUBCOMPONENT_DEFAULT


def test_subcomponent_mapping_uses_formula_scale_without_xml_stats():
    layout = _choice("StraightLayout", "engine_layout")
    fuel = _choice("GasFuel", "fuel_type")
    mapped = subcomponent_values_from_choices(
        {
            "engine_layout": layout,
            "fuel_type": fuel,
        }
    )
    engine = mapped["engine"]
    assert engine["layout_reliability"] == FORMULA_SUBCOMPONENT_DEFAULT
    assert engine["fuel_system_fuel_economy"] == FORMULA_SUBCOMPONENT_DEFAULT
    assert engine["cylinders"] == 4



def test_frame_maps_to_chassis_frame_fields():
    frame = _choice("TestFrame", "frame", reliability=60, performance=35, weight=55)
    mapped = subcomponent_values_from_choices({"frame": frame})
    chassis = mapped["chassis"]
    assert chassis["frame_durability"] == 0.60
    assert chassis["frame_performance"] == 0.35
    assert chassis["frame_weight"] == 0.55


def test_mapped_choices_produce_sane_engine_torque():
    from gearcity_optimizer.formulas.engine_formula import EngineFormulaInputs, calculate_engine

    layout = _choice("StraightLayout", "engine_layout")
    fuel = _choice("GasFuel", "fuel_type")
    mapped = subcomponent_values_from_choices(
        {"engine_layout": layout, "fuel_type": fuel, "cylinder_count": _choice("Four", "cylinder_count")}
    )
    extras = mapped["engine"]
    fields = EngineFormulaInputs.__dataclass_fields__
    kwargs = {k: v for k, v in extras.items() if k in fields}
    result = calculate_engine(EngineFormulaInputs(year=1920, marque_design_engine_skill=25.0, **kwargs))
    assert result.torque < 500.0, f"torque {result.torque} looks like unscaled subcomponent stats"
