"""Tests for quarterly design skill requirement decay."""

from __future__ import annotations

from gearcity_optimizer.core.design_skill_decay import (
    SKILL_DECAY_PER_QUARTER,
    decay_quarters_elapsed,
    effective_required_skill,
)
from gearcity_optimizer.importers.components_xml import (
    ComponentTech,
    is_component_available,
)


def test_decay_is_zero_during_unlock_year():
    assert decay_quarters_elapsed(1900, 1900) == 0
    assert effective_required_skill(20.0, 1900, 1900) == 20.0


def test_first_decay_happens_in_q1_after_unlock_year():
    assert decay_quarters_elapsed(1900, 1901, quarter=1) == 1
    assert effective_required_skill(20.0, 1900, 1901, quarter=1) == 19.82
    assert effective_required_skill(20.0, 1900, 1901, quarter=2) == 19.64


def test_i_layout_unlock_1891_skill_10_available_at_1900_with_skill_5():
    """Developer example: I layout lists skill 10 but is open at 1900 with skill 5."""
    required = effective_required_skill(10.0, 1891, 1900)
    assert required is not None
    assert required < 5.0
    assert round(required, 2) == 3.52

    layout = ComponentTech(
        id="91005",
        name="StraightLayout",
        category="engine",
        subcategory="layout",
        start_year=1891,
        end_year=None,
        required_skill=10.0,
        raw_attributes={"picture": "StraightLayout.dds", "type": "layout"},
        source_path="test",
    )
    assert is_component_available(
        layout,
        1900,
        {"chassis": 5.0, "engine": 5.0, "gearbox": 5.0, "vehicle": 5.0},
    )


def test_unlock_year_1900_not_available_same_year_with_low_skill():
    layout = ComponentTech(
        id="test",
        name="TestLayout",
        category="engine",
        subcategory="layout",
        start_year=1900,
        end_year=None,
        required_skill=10.0,
        raw_attributes={"type": "layout"},
        source_path="test",
    )
    skills = {"chassis": 5.0, "engine": 5.0, "gearbox": 5.0, "vehicle": 5.0}
    assert not is_component_available(layout, 1900, skills)
    assert not is_component_available(layout, 1901, skills)
    assert effective_required_skill(10.0, 1900, 1901, quarter=1) == 9.82


def test_changing_quarter_changes_skill_decay_availability():
    """Later quarters in the same year should unlock more decayed skill gates."""
    layout = ComponentTech(
        id="test",
        name="TestLayout",
        category="engine",
        subcategory="layout",
        start_year=1900,
        end_year=None,
        required_skill=10.0,
        raw_attributes={"type": "layout"},
        source_path="test",
    )
    skills = {"chassis": 5.0, "engine": 9.5, "gearbox": 5.0, "vehicle": 5.0}
    assert not is_component_available(layout, 1901, skills, quarter=1)
    assert is_component_available(layout, 1901, skills, quarter=4)


def test_decay_step_matches_reported_value():
    assert SKILL_DECAY_PER_QUARTER == 0.18
