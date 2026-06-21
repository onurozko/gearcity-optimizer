"""Streamlit Design Optimizer tab."""

from __future__ import annotations

import csv
import io

import streamlit as st

from gearcity_optimizer.core.component_availability import ComponentAvailabilityContext
from gearcity_optimizer.core.models import VehicleType
from gearcity_optimizer.reports.slider_optimizer import (
    SliderOptimizationInput,
    SliderOptimizationResult,
    control_settings_for_section,
    optimize_real_slider_settings,
)
from gearcity_optimizer.ui.design_session import (
    availability_context_from_session,
    get_design_session_values,
    render_optimizer_controls,
)
from gearcity_optimizer.ui.slider_audit import slider_audit_rows, slider_audit_warnings

CONTROL_SECTIONS = (
    ("chassis", "Chassis controls"),
    ("engine", "Engine controls"),
    ("gearbox", "Gearbox controls"),
    ("vehicle", "Vehicle / coachwork controls"),
    ("testing", "Testing controls"),
)


def streamlit_tab_names() -> list[str]:
    """Return ordered Streamlit tab labels for the main app."""
    return [
        "Design Checklist",
        "Component Priorities",
        "Design Optimizer",
        "Tech Availability",
        "Vehicle Type Groups",
        "Package Optimizer",
        "Historical Events / Timeline",
        "Naming Guide",
        "Wiki / Formula Tools",
    ]


def _control_table(settings) -> list[dict[str, object]]:
    return [
        {
            "Control / slider": item.label,
            "Recommended value": item.value,
            "Formula variable": item.formula_variable or "",
            "Reason": item.reason,
            "Confidence": item.confidence,
        }
        for item in settings
    ]


def controls_to_csv(result: SliderOptimizationResult) -> str:
    """Serialize all control settings to CSV text."""
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=[
            "section",
            "slider_key",
            "Control / slider",
            "Recommended value",
            "Formula variable",
            "Reason",
            "Confidence",
        ],
    )
    writer.writeheader()
    for setting in result.control_settings:
        writer.writerow(
            {
                "section": setting.section,
                "slider_key": setting.slider_key,
                "Control / slider": setting.label,
                "Recommended value": setting.value,
                "Formula variable": setting.formula_variable or "",
                "Reason": setting.reason,
                "Confidence": setting.confidence,
            }
        )
    return buffer.getvalue()


def controls_to_text(result: SliderOptimizationResult) -> str:
    """Serialize control settings to plain text for copying."""
    lines = ["Actual controls to set", ""]
    for section, title in CONTROL_SECTIONS:
        section_settings = control_settings_for_section(result, section)
        if not section_settings:
            continue
        lines.append(title)
        for item in section_settings:
            lines.append(
                f"  - {item.label}: {item.value} "
                f"({item.formula_variable or 'n/a'}, {item.confidence})"
            )
            lines.append(f"    {item.reason}")
        lines.append("")
    return "\n".join(lines).strip()


def render_components_status_summary(
    context: ComponentAvailabilityContext,
) -> None:
    """Show compact Components.xml availability context."""
    if not context.catalog_loaded:
        st.info(
            "Components.xml has not been imported. Slider optimization can still run "
            "with formula/proxy defaults, but tech availability context will be missing."
        )
        for warning in context.warnings:
            st.caption(warning)
        st.caption("Go to the **Tech Availability** tab to import Components.xml.")
        return

    st.success(
        f"Components.xml loaded: **{context.available_count}** available, "
        f"**{context.locked_count}** locked for this year/skill setup."
    )


def render_available_tech_summary(context: ComponentAvailabilityContext) -> None:
    """Optional compact tech summary expander."""
    if not context.catalog_loaded:
        return

    with st.expander("Available tech summary", expanded=False):
        if not context.available_components:
            st.write("No components are available for the current year and skills.")
            return
        preview = [
            {
                "name": component.name,
                "category": component.category,
                "subcategory": component.subcategory,
                "required skill": component.required_skill,
            }
            for component in context.available_components[:25]
        ]
        st.dataframe(preview, use_container_width=True, hide_index=True)
        if context.available_count > 25:
            st.caption(
                f"Showing 25 of {context.available_count} available entries. "
                "Open Tech Availability for the full table."
            )


def render_model_optimized_sliders(
    *,
    result: SliderOptimizationResult,
    vehicle_type_name: str,
    year: int,
    cost_mode_label: str,
    availability: ComponentAvailabilityContext,
) -> None:
    """Render model-optimized controls, predicted outputs, and tradeoffs."""
    st.markdown("## Model-optimized real slider settings")
    st.caption(
        "Exact values for actual controllable GearCity sliders/inputs. Output stats "
        "like torque, horsepower, cargo, and fuel economy are predicted results, "
        "not sliders."
    )

    metric_cols = st.columns(6)
    metric_cols[0].metric("Vehicle type", vehicle_type_name)
    metric_cols[1].metric("Cost mode", cost_mode_label)
    metric_cols[2].metric("Year", year)
    metric_cols[3].metric("Controls", len(result.control_settings))
    metric_cols[4].metric("Available tech", availability.available_count)
    metric_cols[5].metric("Locked tech", availability.locked_count)

    st.divider()
    st.markdown("## Actual controls to set")

    st.download_button(
        "Download all controls as CSV",
        data=controls_to_csv(result),
        file_name=(
            f"{vehicle_type_name.lower().replace(' ', '_')}_{year}_controls.csv"
        ),
        mime="text/csv",
    )

    for section, title in CONTROL_SECTIONS:
        section_settings = control_settings_for_section(result, section)
        if not section_settings:
            continue
        with st.expander(title, expanded=section in {"chassis", "engine", "gearbox"}):
            st.dataframe(
                _control_table(section_settings),
                use_container_width=True,
                hide_index=True,
            )

    with st.expander("Copy-friendly control export"):
        st.text(controls_to_text(result))

    st.divider()
    st.markdown("## Predicted output stats")
    predicted_rows = [
        {
            "Output stat": item.label,
            "Predicted/proxy value": round(item.value, 2),
            "Importance": round(item.target_weight, 3),
            "Reason": item.reason,
            "Proxy": "yes" if item.is_proxy else "no",
        }
        for item in result.predicted_outputs
    ]
    st.dataframe(predicted_rows, use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("## Tradeoffs")
    for item in result.tradeoffs:
        st.markdown(f"- {item}")

    if result.warnings:
        st.markdown("### Warnings")
        for item in result.warnings:
            st.markdown(f"- {item}")

    with st.expander("Model limitations"):
        for item in result.limitations:
            st.markdown(f"- {item}")


def render_design_optimizer_tab(
    *,
    vehicle_type_name: str,
    vehicle_type: VehicleType,
) -> None:
    """Render the Design Optimizer tab."""
    st.subheader("Design Optimizer")
    st.caption(
        "Generate exact model-optimized values for actual GearCity controls/sliders "
        "using vehicle type priorities, cost mode, year, research skills, and "
        "imported Components.xml availability."
    )

    st.markdown("#### Optimizer controls")
    st.caption(
        "Year and research skills are set in the sidebar under "
        "Design Optimizer / Tech Availability."
    )
    render_optimizer_controls()
    session = get_design_session_values()
    availability = availability_context_from_session(session)
    st.divider()

    render_components_status_summary(availability)
    render_available_tech_summary(availability)

    opt_result = optimize_real_slider_settings(
        SliderOptimizationInput(
            vehicle_type=vehicle_type,
            year=session.year,
            cost_mode=session.cost_mode,
            chassis_skill=session.chassis_skill,
            engine_skill=session.engine_skill,
            gearbox_skill=session.gearbox_skill,
            vehicle_skill=session.vehicle_skill,
            depth=session.optimization_depth,  # type: ignore[arg-type]
        )
    )

    st.divider()
    render_model_optimized_sliders(
        result=opt_result,
        vehicle_type_name=vehicle_type_name,
        year=session.year,
        cost_mode_label=session.cost_mode_label,
        availability=availability,
    )

    with st.expander("Real slider/input audit", expanded=False):
        st.caption(
            "Verified controllable GearCity inputs from formula modules. Output stats "
            "are not listed here."
        )
        for warning in slider_audit_warnings():
            st.warning(warning)
        rows = slider_audit_rows()
        if rows:
            st.dataframe(rows, use_container_width=True, hide_index=True)
