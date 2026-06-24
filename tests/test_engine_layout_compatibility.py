"""Tests for engine layout and cylinder count compatibility."""

from __future__ import annotations

from gearcity_optimizer.core.engine_layout_compatibility import (
    allowed_cylinder_counts,
    is_valid_layout_cylinder_combo,
    parse_cylinder_count,
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


def test_single_layout_only_allows_one_cylinder():
    layout = _choice("SingleLayout", "engine_layout")
    one = _choice("OneCylinder", "cylinder_count", cylinders=1)
    two = _choice("TwoCylinder", "cylinder_count", cylinders=2)
    assert allowed_cylinder_counts(layout) == {1}
    assert is_valid_layout_cylinder_combo(layout, one)
    assert not is_valid_layout_cylinder_combo(layout, two)


def test_straight_layout_allows_inline_multi_cylinder():
    layout = _choice("StraightLayout", "engine_layout")
    two = _choice("TwoCylinder", "cylinder_count", cylinders=2)
    six = _choice("SixCylinder", "cylinder_count", cylinders=6)
    one = _choice("OneCylinder", "cylinder_count", cylinders=1)
    assert is_valid_layout_cylinder_combo(layout, two)
    assert is_valid_layout_cylinder_combo(layout, six)
    assert not is_valid_layout_cylinder_combo(layout, one)


def test_parse_cylinder_count_from_name():
    assert parse_cylinder_count(_choice("TwoCylinder", "cylinder_count")) == 2
    assert parse_cylinder_count(_choice("SixCylinder", "cylinder_count")) == 6
