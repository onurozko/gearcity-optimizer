"""Shared Streamlit session state for Design Optimizer and Tech Availability."""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from gearcity_optimizer.core.component_availability import (
    ComponentAvailabilityContext,
    get_component_availability_context,
)
from gearcity_optimizer.reports.part_recommender import parse_cost_mode_display

COST_MODE_OPTIONS = ("Cheap", "Balanced", "Luxury")
DEPTH_OPTIONS = ("Quick", "Balanced", "Deep")

DEPTH_TO_INTERNAL = {
    "Quick": "quick",
    "Balanced": "balanced",
    "Deep": "thorough",
}

SESSION_DEFAULTS = {
    "selected_year": 1900,
    "chassis_skill": 0.0,
    "engine_skill": 0.0,
    "gearbox_skill": 0.0,
    "vehicle_skill": 0.0,
    "cost_mode": "Balanced",
    "optimization_depth": "Balanced",
}


@dataclass(frozen=True)
class DesignSessionValues:
    """Shared optimization and tech availability inputs."""

    year: int
    chassis_skill: float
    engine_skill: float
    gearbox_skill: float
    vehicle_skill: float
    cost_mode_label: str
    cost_mode: str
    optimization_depth_label: str
    optimization_depth: str

    @property
    def skill_levels(self) -> dict[str, float]:
        return {
            "chassis": self.chassis_skill,
            "engine": self.engine_skill,
            "gearbox": self.gearbox_skill,
            "vehicle": self.vehicle_skill,
        }


def init_design_session_state() -> None:
    """Initialize shared design/tech session keys if missing."""
    for key, value in SESSION_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = value


def get_design_session_values() -> DesignSessionValues:
    """Read shared session values without rendering widgets."""
    init_design_session_state()
    depth_label = str(st.session_state.optimization_depth)
    cost_label = str(st.session_state.cost_mode)
    return DesignSessionValues(
        year=int(st.session_state.selected_year),
        chassis_skill=float(st.session_state.chassis_skill),
        engine_skill=float(st.session_state.engine_skill),
        gearbox_skill=float(st.session_state.gearbox_skill),
        vehicle_skill=float(st.session_state.vehicle_skill),
        cost_mode_label=cost_label,
        cost_mode=parse_cost_mode_display(cost_label),
        optimization_depth_label=depth_label,
        optimization_depth=DEPTH_TO_INTERNAL.get(depth_label, "balanced"),
    )


def render_shared_year_skill_inputs() -> None:
    """Render year/skill widgets once (sidebar). Updates shared session state."""
    init_design_session_state()

    st.number_input(
        "Year",
        min_value=1900,
        max_value=2100,
        step=1,
        key="selected_year",
    )
    st.number_input(
        "Chassis skill",
        min_value=0.0,
        max_value=100.0,
        step=1.0,
        key="chassis_skill",
    )
    st.number_input(
        "Engine skill",
        min_value=0.0,
        max_value=100.0,
        step=1.0,
        key="engine_skill",
    )
    st.number_input(
        "Gearbox skill",
        min_value=0.0,
        max_value=100.0,
        step=1.0,
        key="gearbox_skill",
    )
    st.number_input(
        "Vehicle / Coachwork skill",
        min_value=0.0,
        max_value=100.0,
        step=1.0,
        key="vehicle_skill",
    )


def render_optimizer_controls() -> None:
    """Render optimizer-only controls (Design Optimizer tab only)."""
    init_design_session_state()
    col_cost, col_depth = st.columns(2)
    with col_cost:
        st.selectbox("Cost mode", options=list(COST_MODE_OPTIONS), key="cost_mode")
    with col_depth:
        st.selectbox(
            "Optimization depth",
            options=list(DEPTH_OPTIONS),
            key="optimization_depth",
            help="Quick uses the same heuristic with fewer refinements in future versions.",
        )


def availability_context_from_session(
    session: DesignSessionValues,
    *,
    category_filter: str | None = None,
    name_search: str | None = None,
    catalog=None,
) -> ComponentAvailabilityContext:
    """Build shared component availability context from session state values."""
    return get_component_availability_context(
        year=session.year,
        chassis_skill=session.chassis_skill,
        engine_skill=session.engine_skill,
        gearbox_skill=session.gearbox_skill,
        vehicle_skill=session.vehicle_skill,
        category_filter=category_filter,
        name_search=name_search,
        catalog=catalog,
    )


def design_session_from_mapping(values: dict[str, object]) -> DesignSessionValues:
    """Build session values from a plain mapping (for tests)."""
    depth_label = str(values.get("optimization_depth", "Balanced"))
    cost_label = str(values.get("cost_mode", "Balanced"))
    return DesignSessionValues(
        year=int(values.get("selected_year", 1900)),
        chassis_skill=float(values.get("chassis_skill", 0.0)),
        engine_skill=float(values.get("engine_skill", 0.0)),
        gearbox_skill=float(values.get("gearbox_skill", 0.0)),
        vehicle_skill=float(values.get("vehicle_skill", 0.0)),
        cost_mode_label=cost_label,
        cost_mode=parse_cost_mode_display(cost_label),
        optimization_depth_label=depth_label,
        optimization_depth=DEPTH_TO_INTERNAL.get(depth_label, "balanced"),
    )
