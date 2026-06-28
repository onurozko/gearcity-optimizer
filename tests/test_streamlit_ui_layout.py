"""Tests for Streamlit tab layout and design optimizer separation."""

from __future__ import annotations

from pathlib import Path

import pytest

from gearcity_optimizer.ui.design_optimizer import (
    controls_to_csv,
    streamlit_tab_names,
)
from gearcity_optimizer.ui.design_session import (
    SESSION_DEFAULTS,
    design_session_from_mapping,
)
from gearcity_optimizer.ui.streamlit_helpers import render_app
from gearcity_optimizer.ui.tech_availability import (
    render_tech_availability_tab,
)


def test_streamlit_tab_list_includes_design_optimizer():
    """Main app tab order should include Design Optimizer before Tech Availability."""
    names = streamlit_tab_names()
    assert "Design Optimizer" in names
    assert "Tech Availability" in names
    assert "Save Data / Calibration" in names
    assert names.index("Design Optimizer") < names.index("Tech Availability")
    assert names.index("Save Data / Calibration") > names.index("Wiki / Formula Tools")
    assert names[0] == "Design Checklist"
    assert names[1] == "Component Priorities"
    assert names[2] == "Design Optimizer"
    assert names[3] == "Tech Availability"


def test_streamlit_helpers_tab_order_matches_design_optimizer_module():
    """streamlit_helpers should wire tabs from the shared tab name list."""
    source = Path(__file__).resolve().parents[1] / "gearcity_optimizer" / "ui" / "streamlit_helpers.py"
    text = source.read_text(encoding="utf-8")
    assert "streamlit_tab_names()" in text
    assert "render_design_optimizer_tab" in text
    assert "render_tech_availability_tab()" in text
    assert "render_save_calibration_tab()" in text


def test_tech_availability_no_recommendation_preview():
    """Tech Availability module should not host recommendation preview or slider UI."""
    source = Path(__file__).resolve().parents[1] / "gearcity_optimizer" / "ui" / "tech_availability.py"
    text = source.read_text(encoding="utf-8")
    assert "render_recommendation_preview" not in text
    assert "render_model_optimized_sliders" not in text
    assert "Recommendation Preview" not in text
    assert "Model-optimized real slider settings" not in text
    assert "DESIGN_OPTIMIZER_NOTE" in text
    assert "Design Optimizer" in text


def test_design_optimizer_separates_controls_from_predicted_outputs():
    """Design Optimizer helpers should keep choices, controls, and predicted stats distinct."""
    source = Path(__file__).resolve().parents[1] / "gearcity_optimizer" / "ui" / "design_optimizer.py"
    text = source.read_text(encoding="utf-8")
    assert "## Component choices" in text
    assert "Validated component choices" in text
    assert "Recommended slider values" in text
    assert "Predicted output stats" in text
    assert "control_settings_for_section" in text
    assert "result.slider_result.predicted_outputs" in text
    assert "Model-optimized real slider settings" not in text


def test_shared_session_state_used_by_both_tabs():
    """Design Optimizer and Tech Availability should share design_session helpers."""
    root = Path(__file__).resolve().parents[1] / "gearcity_optimizer" / "ui"
    optimizer = (root / "design_optimizer.py").read_text(encoding="utf-8")
    tech = (root / "tech_availability.py").read_text(encoding="utf-8")
    helpers = (root / "streamlit_helpers.py").read_text(encoding="utf-8")
    session = (root / "design_session.py").read_text(encoding="utf-8")
    assert "get_design_session_values" in optimizer
    assert "get_design_session_values" in tech
    assert "render_shared_year_skill_panel" in optimizer
    assert "render_shared_year_skill_panel" in tech
    assert "render_checklist_controls" in helpers
    assert "render_shared_year_skill_panel" in session
    assert "reset_shared_year_skill_panel_render" in helpers
    assert "availability_context_from_session" in optimizer
    assert "availability_context_from_session" in tech
    assert "selected_year" in session
    assert "checklist_year" in session


def test_shared_session_defaults_map_consistently():
    """Shared year/skill/cost mode keys should map consistently."""
    values = design_session_from_mapping(
        {
            "selected_year": 1925,
            "chassis_skill": 10.0,
            "engine_skill": 20.0,
            "gearbox_skill": 30.0,
            "vehicle_skill": 40.0,
            "cost_mode": "Luxury",
            "optimization_depth": "Deep",
        }
    )
    assert values.year == 1925
    assert values.quarter == 4
    assert values.chassis_skill == 10.0
    assert values.cost_mode == "luxury"
    assert values.optimization_depth == "thorough"
    assert set(SESSION_DEFAULTS) >= {
        "selected_year",
        "selected_quarter",
        "chassis_skill",
        "engine_skill",
        "gearbox_skill",
        "vehicle_skill",
        "cost_mode",
        "checklist_year",
    }


def test_controls_csv_includes_section_and_slider_key(wiki_model_paths):
    """CSV export should include all control settings with section metadata."""
    from gearcity_optimizer.core.models import VehicleType
    from gearcity_optimizer.reports.slider_optimizer import optimize_real_slider_settings, SliderOptimizationInput

    vehicle_type = VehicleType(
        name="Sedan",
        performance=0.4,
        drivability=0.4,
        luxury=0.45,
        safety=0.65,
        fuel=0.65,
        power=0.45,
        cargo=0.5,
        dependability=0.45,
        wealth_demo=4,
        military_fleet=False,
        civilian_fleet=True,
    )
    result = optimize_real_slider_settings(
        SliderOptimizationInput(vehicle_type=vehicle_type, year=1900, cost_mode="balanced")
    )
    csv_text = controls_to_csv(result)
    assert "section" in csv_text.splitlines()[0]
    assert "slider_key" in csv_text.splitlines()[0]
    assert len(result.control_settings) > 0
    assert result.predicted_outputs
    assert all(
        setting.section
        for setting in result.control_settings
    )


def test_streamlit_app_imports_without_crashing():
    """Streamlit UI helpers should import when streamlit is available."""
    pytest.importorskip("streamlit")
    assert callable(render_app)
    assert callable(render_tech_availability_tab)
