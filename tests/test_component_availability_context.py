"""Tests for shared component availability context."""

from __future__ import annotations

from pathlib import Path

import pytest

from gearcity_optimizer.core.component_availability import (
    MISSING_CATALOG_WARNING,
    get_component_availability_context,
)
from gearcity_optimizer.importers.components_xml import parse_components_xml
from gearcity_optimizer.ui.design_optimizer import render_design_optimizer_tab
from gearcity_optimizer.ui.design_session import availability_context_from_session, design_session_from_mapping
from gearcity_optimizer.ui.tech_availability import render_tech_availability_tab


@pytest.fixture
def sample_catalog():
    fixture = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "components"
        / "sample_components.xml"
    )
    return parse_components_xml(fixture)


def test_both_ui_modules_use_shared_availability_context():
    """Design Optimizer and Tech Availability should call the shared helper."""
    root = Path(__file__).resolve().parents[1] / "gearcity_optimizer" / "ui"
    optimizer = (root / "design_optimizer.py").read_text(encoding="utf-8")
    tech = (root / "tech_availability.py").read_text(encoding="utf-8")
    session = (root / "design_session.py").read_text(encoding="utf-8")
    helpers = (root / "streamlit_helpers.py").read_text(encoding="utf-8")
    assert "availability_context_from_session" in optimizer
    assert "availability_context_from_session" in tech
    assert "get_component_availability_context" in session
    assert "render_shared_year_skill_inputs" in helpers
    assert "classify_components" not in optimizer
    assert "classify_components" not in tech


def test_same_year_skills_yield_same_counts(sample_catalog):
    """Given the same inputs, both tabs should see identical availability counts."""
    base_kwargs = {
        "year": 1920,
        "chassis_skill": 5.0,
        "engine_skill": 10.0,
        "gearbox_skill": 15.0,
        "vehicle_skill": 20.0,
        "catalog": sample_catalog,
    }
    optimizer_context = get_component_availability_context(**base_kwargs)
    session = design_session_from_mapping(
        {
            "selected_year": 1920,
            "chassis_skill": 5.0,
            "engine_skill": 10.0,
            "gearbox_skill": 15.0,
            "vehicle_skill": 20.0,
        }
    )
    tech_context = availability_context_from_session(session, catalog=sample_catalog)

    assert optimizer_context.available_count == tech_context.available_count
    assert optimizer_context.locked_count == tech_context.locked_count
    assert optimizer_context.available_count + optimizer_context.locked_count > 0


def test_changing_year_changes_availability_context(sample_catalog):
    """Different years should produce different availability results."""
    early = get_component_availability_context(
        year=1900,
        chassis_skill=0.0,
        engine_skill=0.0,
        gearbox_skill=0.0,
        vehicle_skill=0.0,
        catalog=sample_catalog,
    )
    later = get_component_availability_context(
        year=1950,
        chassis_skill=0.0,
        engine_skill=0.0,
        gearbox_skill=0.0,
        vehicle_skill=0.0,
        catalog=sample_catalog,
    )
    assert early.available_count != later.available_count or early.locked_count != later.locked_count


def test_changing_skills_changes_availability_context(sample_catalog):
    """Higher skills should unlock components locked at lower skill levels."""
    low_skill = get_component_availability_context(
        year=1920,
        chassis_skill=0.0,
        engine_skill=0.0,
        gearbox_skill=0.0,
        vehicle_skill=0.0,
        catalog=sample_catalog,
    )
    high_skill = get_component_availability_context(
        year=1920,
        chassis_skill=100.0,
        engine_skill=100.0,
        gearbox_skill=100.0,
        vehicle_skill=100.0,
        catalog=sample_catalog,
    )
    assert high_skill.available_count >= low_skill.available_count
    assert high_skill.locked_count <= low_skill.locked_count


def test_missing_catalog_returns_not_loaded_context(monkeypatch: pytest.MonkeyPatch):
    """Missing Components.xml should return catalog_loaded=False with warnings."""
    monkeypatch.setattr(
        "gearcity_optimizer.core.component_availability.load_imported_components_catalog",
        lambda: None,
    )
    context = get_component_availability_context(
        year=1900,
        chassis_skill=0.0,
        engine_skill=0.0,
        gearbox_skill=0.0,
        vehicle_skill=0.0,
    )
    assert context.catalog_loaded is False
    assert context.available_count == 0
    assert context.locked_count == 0
    assert context.source_path is None
    assert MISSING_CATALOG_WARNING in context.warnings


def test_category_filter_applies_to_shared_context(sample_catalog):
    """Tech Availability category filters should use the same helper path."""
    all_context = get_component_availability_context(
        year=1920,
        chassis_skill=0.0,
        engine_skill=0.0,
        gearbox_skill=0.0,
        vehicle_skill=0.0,
        catalog=sample_catalog,
    )
    engine_context = get_component_availability_context(
        year=1920,
        chassis_skill=0.0,
        engine_skill=0.0,
        gearbox_skill=0.0,
        vehicle_skill=0.0,
        category_filter="engine",
        catalog=sample_catalog,
    )
    assert engine_context.available_count <= all_context.available_count
    assert all(
        row.skill_category == "engine" or row.component.category.lower() == "engine"
        for row in engine_context.available_rows
    )


def test_render_entrypoints_importable():
    """Streamlit tab renderers should remain importable."""
    assert callable(render_design_optimizer_tab)
    assert callable(render_tech_availability_tab)
