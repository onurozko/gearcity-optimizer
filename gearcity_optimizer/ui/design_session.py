"""Shared Streamlit session state for Design Optimizer and Tech Availability."""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from gearcity_optimizer.core.component_availability import (
    ComponentAvailabilityContext,
    get_component_availability_context,
)
from gearcity_optimizer.reports.part_recommender import parse_cost_mode_display

from gearcity_optimizer.llm.config import (
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OPENAI_COMPAT_BASE_URL,
    LLMConfig,
    resolve_llm_config,
)
from gearcity_optimizer.llm.strategy_client import list_ollama_models, ollama_is_reachable


def _auto_configure_local_ollama() -> None:
    """Detect local Ollama and pick defaults without user URL entry."""
    st.session_state.llm_base_url = DEFAULT_OLLAMA_BASE_URL
    preview = resolve_llm_config(
        enabled=True,
        backend="ollama",
        model=str(st.session_state.get("llm_model", DEFAULT_OLLAMA_MODEL)),
        base_url=DEFAULT_OLLAMA_BASE_URL,
    )
    if ollama_is_reachable(preview):
        installed = list_ollama_models(preview)
        if installed:
            current = str(st.session_state.get("llm_model", "")).strip()
            if not current or current not in installed:
                st.session_state.llm_model = installed[0]

COST_MODE_OPTIONS = ("Cheap", "Balanced", "Luxury")
DEPTH_OPTIONS = ("Quick", "Balanced", "Deep")

DEPTH_TO_INTERNAL = {
    "Quick": "quick",
    "Balanced": "balanced",
    "Deep": "thorough",
}

SESSION_DEFAULTS = {
    "selected_year": 1900,
    "selected_quarter": 4,
    "chassis_skill": 5.0,
    "engine_skill": 5.0,
    "gearbox_skill": 5.0,
    "vehicle_skill": 5.0,
    "cost_mode": "Balanced",
    "optimization_depth": "Balanced",
    "component_choice_mode": "Auto-pick components (experimental)",
    "recommendation_mode": "Deterministic only",
    "llm_backend": "ollama",
    "llm_model": "llama3:latest",
    "llm_base_url": "http://localhost:11434",
    "design_optimizer_result": None,
    "design_optimizer_run_fingerprint": None,
    "checklist_year": 1901,
    "checklist_report": None,
}

COMPONENT_CHOICE_MODE_OPTIONS = (
    "Auto-pick components (experimental)",
    "Manual component selection",
)

RECOMMENDATION_MODE_OPTIONS = (
    "Deterministic only",
    "LLM-assisted experimental",
)

LLM_BACKEND_OPTIONS = ("ollama", "openai_compatible")

LLM_ASSISTED_EXPERIMENTAL_LABEL = (
    "LLM-assisted experimental mode. LLM suggestions are validated against Components.xml, "
    "wiki-backed slider registry, and formula/proxy scoring before display."
)

AUTO_PICK_EXPERIMENTAL_LABEL = (
    "Experimental: automatic component choice scoring is still being validated. "
    "Review alternatives before copying the setup into GearCity."
)


@dataclass(frozen=True)
class DesignSessionValues:
    """Shared optimization and tech availability inputs."""

    year: int
    quarter: int
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
        quarter=int(st.session_state.selected_quarter),
        chassis_skill=float(st.session_state.chassis_skill),
        engine_skill=float(st.session_state.engine_skill),
        gearbox_skill=float(st.session_state.gearbox_skill),
        vehicle_skill=float(st.session_state.vehicle_skill),
        cost_mode_label=cost_label,
        cost_mode=parse_cost_mode_display(cost_label),
        optimization_depth_label=depth_label,
        optimization_depth=DEPTH_TO_INTERNAL.get(depth_label, "balanced"),
    )


def render_shared_year_skill_inputs(*, compact: bool = False) -> None:
    """Render year/skill widgets. Updates shared session state."""
    init_design_session_state()

    col_year, col_quarter = st.columns([2, 1])
    with col_year:
        st.number_input(
            "Year",
            min_value=1900,
            max_value=2100,
            step=1,
            key="selected_year",
        )
    with col_quarter:
        st.selectbox(
            "Quarter",
            options=(1, 2, 3, 4),
            format_func=lambda value: f"Q{value}",
            key="selected_quarter",
            help="Used for skill requirement decay within the selected year.",
        )
    if compact:
        skill_col_a, skill_col_b = st.columns(2)
        with skill_col_a:
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
        with skill_col_b:
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
    else:
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


YEAR_SKILL_PANEL_RENDERED_KEY = "_shared_year_skill_panel_rendered"


def reset_shared_year_skill_panel_render() -> None:
    """Allow one editable year/skill panel per Streamlit rerun (tabs all execute each time)."""
    st.session_state[YEAR_SKILL_PANEL_RENDERED_KEY] = False


def _render_shared_year_skill_summary(session: DesignSessionValues) -> None:
    st.markdown("#### Year, quarter, and research skills")
    st.caption(
        "Shared between Design Optimizer and Tech Availability. "
        "Edit these on the Design Optimizer tab; values apply here too."
    )
    st.info(
        f"**Year:** {session.year} **Q{session.quarter}** | "
        f"**Chassis:** {session.chassis_skill:.1f} | "
        f"**Engine:** {session.engine_skill:.1f} | "
        f"**Gearbox:** {session.gearbox_skill:.1f} | "
        f"**Vehicle:** {session.vehicle_skill:.1f}"
    )


def render_shared_year_skill_panel() -> None:
    """Render shared year/quarter/skills block for Optimizer and Tech Availability tabs."""
    init_design_session_state()
    if st.session_state.get(YEAR_SKILL_PANEL_RENDERED_KEY):
        _render_shared_year_skill_summary(get_design_session_values())
        return

    st.session_state[YEAR_SKILL_PANEL_RENDERED_KEY] = True
    st.markdown("#### Year, quarter, and research skills")
    st.caption(
        "Shared between Design Optimizer and Tech Availability. "
        "Values are kept when you switch tabs."
    )
    render_shared_year_skill_inputs(compact=True)


def render_checklist_controls() -> bool:
    """Render checklist year and generate button. Returns True when generate was clicked."""
    init_design_session_state()
    col_year, col_button = st.columns([2, 1])
    with col_year:
        st.number_input(
            "Checklist year",
            min_value=1899,
            max_value=2100,
            step=1,
            key="checklist_year",
            help="Historical context for the design checklist only.",
        )
    with col_button:
        st.markdown("")
        generate = st.button("Generate Checklist", type="primary", key="generate_checklist")
    return generate


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
    st.selectbox(
        "Component choice mode",
        options=list(COMPONENT_CHOICE_MODE_OPTIONS),
        key="component_choice_mode",
        help=(
            "Auto-pick ranks available Components.xml choices using deterministic suitability "
            "scoring. Manual mode lets you pick layout/fuel/frame/gearbox and optimize sliders "
            "around those choices."
        ),
    )
    st.selectbox(
        "Recommendation mode",
        options=list(RECOMMENDATION_MODE_OPTIONS),
        key="recommendation_mode",
        help=(
            "Deterministic only uses source-backed scoring. LLM-assisted experimental adds "
            "contextual strategy suggestions that are validated before display."
        ),
    )
    if is_llm_recommendation_mode():
        st.selectbox("LLM backend", options=list(LLM_BACKEND_OPTIONS), key="llm_backend")
    if is_llm_recommendation_mode():
        backend = str(st.session_state.llm_backend).strip().lower()
        if backend == "ollama":
            _auto_configure_local_ollama()
            installed = list_ollama_models(build_llm_config_from_session())
            if installed:
                st.selectbox("LLM model", options=installed, key="llm_model")
            else:
                st.caption(
                    "Local Ollama not detected. Start Ollama, or switch to Deterministic only."
                )
                st.text_input(
                    "LLM model",
                    key="llm_model",
                    value=str(st.session_state.get("llm_model", DEFAULT_OLLAMA_MODEL)),
                )
            st.caption(f"Using local Ollama at {DEFAULT_OLLAMA_BASE_URL} (automatic).")
        else:
            st.text_input("LLM model", key="llm_model")
            if not str(st.session_state.get("llm_base_url", "")).strip():
                st.session_state.llm_base_url = DEFAULT_OPENAI_COMPAT_BASE_URL
            st.text_input(
                "LLM base URL",
                key="llm_base_url",
                help="OpenAI-compatible API base URL, usually ending in /v1",
                placeholder=DEFAULT_OPENAI_COMPAT_BASE_URL,
            )


def is_manual_component_mode() -> bool:
    """Return True when the user chose manual component selection."""
    init_design_session_state()
    return str(st.session_state.component_choice_mode).startswith("Manual")


def is_auto_experimental_component_mode() -> bool:
    """Return True when experimental auto-pick is enabled."""
    init_design_session_state()
    return str(st.session_state.component_choice_mode).startswith("Auto-pick")


def is_llm_recommendation_mode() -> bool:
    """Return True when LLM-assisted recommendation mode is selected."""
    init_design_session_state()
    return str(st.session_state.recommendation_mode).startswith("LLM")


def build_llm_config_from_session() -> LLMConfig:
    """Build LLM config from Streamlit session state."""
    init_design_session_state()
    enabled = is_llm_recommendation_mode()
    backend_raw = str(st.session_state.llm_backend).strip().lower()
    backend = backend_raw if backend_raw in {"ollama", "openai_compatible"} else "ollama"
    base_url = (
        DEFAULT_OLLAMA_BASE_URL
        if backend == "ollama"
        else str(st.session_state.get("llm_base_url", ""))
    )
    return resolve_llm_config(
        enabled=enabled,
        backend=backend,  # type: ignore[arg-type]
        model=str(st.session_state.get("llm_model", "")),
        base_url=base_url,
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
        quarter=session.quarter,
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
        quarter=int(values.get("selected_quarter", 4)),
        chassis_skill=float(values.get("chassis_skill", 0.0)),
        engine_skill=float(values.get("engine_skill", 0.0)),
        gearbox_skill=float(values.get("gearbox_skill", 0.0)),
        vehicle_skill=float(values.get("vehicle_skill", 0.0)),
        cost_mode_label=cost_label,
        cost_mode=parse_cost_mode_display(cost_label),
        optimization_depth_label=depth_label,
        optimization_depth=DEPTH_TO_INTERNAL.get(depth_label, "balanced"),
    )
