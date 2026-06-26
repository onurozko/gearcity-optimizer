"""Tests for bundled engine layout reference data."""

from __future__ import annotations

from gearcity_optimizer.core.layout_reference import (
    layout_reference_for_choice,
    layout_reference_for_key,
    load_engine_layout_reference,
)


def test_layout_reference_includes_w_layout():
    ref = layout_reference_for_key("W")
    assert ref is not None
    assert ref.engine_length == 0.85
    assert ref.engine_width == 1.3
    assert ref.cylinder_length_arrangement == 3


def test_layout_reference_covers_all_wiki_layout_keys():
    refs = load_engine_layout_reference()
    assert "I" in refs
    assert "W" in refs
    assert refs["I"].engine_length > refs["W"].engine_length


def test_layout_reference_for_choice_resolves_aliases():
    from gearcity_optimizer.importers.component_choices import ComponentChoice

    layout = ComponentChoice(
        id="w-layout",
        name="WLayout",
        display_name="W Layout",
        section="engine",
        choice_type="engine_layout",
        start_year=1903,
        end_year=5050,
        required_skill=0.0,
        stats={},
        raw_attributes={"picture": "W.dds"},
        source_path="test",
        confidence="high",
    )
    ref = layout_reference_for_choice(layout)
    assert ref is not None
    assert ref.key == "W"
    assert ref.engine_width == 1.3
