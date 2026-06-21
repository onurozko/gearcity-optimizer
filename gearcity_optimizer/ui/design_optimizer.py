"""Streamlit Design Optimizer tab."""

from __future__ import annotations

import csv
import io

import streamlit as st

from gearcity_optimizer.core.component_availability import ComponentAvailabilityContext
from gearcity_optimizer.core.models import VehicleType
from gearcity_optimizer.importers.component_choices import (
    ComponentChoice,
    audit_component_choice_types,
    audit_components_schema,
    choice_type_label,
    format_choice_type_audit_summary,
    get_available_component_choices,
)
from gearcity_optimizer.importers.component_sources import discover_components_source
from gearcity_optimizer.importers.components_xml import load_imported_components_catalog
from gearcity_optimizer.reports.component_choice_recommender import ChoiceRecommendation
from gearcity_optimizer.reports.design_optimizer import (
    DesignOptimizationInput,
    DesignOptimizationResult,
    choice_recommendations_for_section,
    optimize_design,
)
from gearcity_optimizer.reports.slider_optimizer import (
    SliderOptimizationResult,
    control_settings_for_section,
)
from gearcity_optimizer.ui.design_session import (
    AUTO_PICK_EXPERIMENTAL_LABEL,
    availability_context_from_session,
    get_design_session_values,
    is_auto_experimental_component_mode,
    is_manual_component_mode,
    render_optimizer_controls,
)
from gearcity_optimizer.core.slider_registry import registry_status_message, wiki_model_available
from gearcity_optimizer.ui.slider_audit import (
    formula_influence_rows,
    list_slider_variables,
    screenshot_label_audit_rows,
    slider_audit_rows,
    slider_audit_warnings,
    slider_definition_rows,
    slider_detail,
)

CHOICE_SECTIONS = (
    ("engine", "Engine component choices"),
    ("chassis", "Chassis component choices"),
    ("gearbox", "Gearbox component choices"),
    ("vehicle", "Vehicle / coachwork component choices"),
)

SLIDER_SECTIONS = (
    ("chassis", "Chassis slider values"),
    ("engine", "Engine slider values"),
    ("gearbox", "Gearbox slider values"),
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


def _candidate_table_rows(recommendation: ChoiceRecommendation) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for rank, candidate in enumerate(recommendation.candidates, start=1):
        rows.append(
            {
                "Rank": rank,
                "Choice": candidate.component_name,
                "Suitability": candidate.total_score,
                "Availability": "yes",
                "Era fit": round(candidate.era_score, 1),
                "Cost fit": round(candidate.cost_mode_score, 1),
                "Vehicle fit": round(candidate.vehicle_fit_score, 1),
                "Reason": "; ".join(candidate.reasons[:2]),
                "Penalties": "; ".join(candidate.penalties),
                "Confidence": candidate.confidence,
            }
        )
    return rows


def _choice_summary_rows(recommendations: list[ChoiceRecommendation]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for item in recommendations:
        if not item.candidates:
            continue
        top = item.candidates[0]
        recommended_name = (
            item.recommended_choice.display_name if item.recommended_choice else ""
        )
        rows.append(
            {
                "Choice type": choice_type_label(item.choice_type),
                "Recommended choice": recommended_name,
                "Suitability": top.total_score,
                "Confidence": item.confidence,
                "Alternatives": ", ".join(
                    choice.display_name for choice in item.alternatives[:3]
                ),
                "Penalties (recommended)": "; ".join(top.penalties),
                "Reason": item.reason,
            }
        )
    return rows


def _slider_table_rows(settings) -> list[dict[str, object]]:
    return [
        {
            "Slider name": item.label,
            "Formula variable": item.formula_variable or "",
            "Recommended value": item.value,
            "Source page": item.source_page,
            "Source section": item.source_section,
            "Outputs affected": ", ".join(item.affected_outputs),
            "Reason": item.reason,
            "Confidence": item.confidence,
        }
        for item in settings
    ]


def design_result_to_csv(result: DesignOptimizationResult) -> str:
    """Export component choices, slider controls, and predicted outputs to CSV."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["record_type", "section", "field", "value", "extra", "reason", "confidence"])

    if result.component_choices is not None:
        for recommendation in result.component_choices.choices:
            writer.writerow(
                [
                    "component_choice",
                    recommendation.section,
                    recommendation.choice_type,
                    recommendation.recommended_choice.display_name
                    if recommendation.recommended_choice
                    else "",
                    ", ".join(
                        choice.display_name for choice in recommendation.alternatives[:3]
                    ),
                    recommendation.reason,
                    recommendation.confidence,
                ]
            )

    for setting in result.slider_result.control_settings:
        writer.writerow(
            [
                "slider_control",
                setting.section,
                setting.label,
                setting.value,
                setting.formula_variable or "",
                setting.reason,
                setting.confidence,
            ]
        )

    for output in result.slider_result.predicted_outputs:
        writer.writerow(
            [
                "predicted_output",
                "output",
                output.label,
                round(output.value, 2),
                round(output.target_weight, 3),
                output.reason,
                "proxy" if output.is_proxy else "formula",
            ]
        )
    return buffer.getvalue()


def controls_to_csv(result: SliderOptimizationResult) -> str:
    """Backward-compatible CSV export for slider controls only."""
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


def _render_manual_choice_inputs(
    available_choices: list[ComponentChoice],
) -> dict[str, ComponentChoice]:
    """Render manual component choice dropdowns."""
    grouped: dict[str, list[ComponentChoice]] = {}
    for choice in available_choices:
        if choice.choice_type == "unknown":
            continue
        grouped.setdefault(choice.choice_type, []).append(choice)

    manual: dict[str, ComponentChoice] = {}
    for choice_type in sorted(grouped):
        options = grouped[choice_type]
        labels = [choice.display_name for choice in options]
        selected_label = st.selectbox(
            choice_type_label(choice_type),
            options=labels,
            key=f"manual_component_choice_{choice_type}",
        )
        manual[choice_type] = options[labels.index(selected_label)]
    return manual


def render_components_status_summary(
    context: ComponentAvailabilityContext,
    *,
    available_choice_count: int,
) -> None:
    """Show compact Components.xml availability context."""
    if not context.catalog_loaded:
        st.warning(
            "Components.xml is required for component/dropdown recommendations. "
            "Slider-only proxy optimization can still run, but component choices "
            "cannot be recommended."
        )
        for warning in context.warnings:
            st.caption(warning)
        st.caption("Go to the **Tech Availability** tab to import Components.xml.")
        return

    st.success(
        f"Components.xml loaded: **{context.available_count}** available entries, "
        f"**{available_choice_count}** selectable choices for this year/skill setup."
    )


def render_component_choices(result: DesignOptimizationResult) -> None:
    """Render recommended component choices section."""
    st.markdown("## Recommended component choices")
    if result.component_choice_mode == "manual":
        st.caption(
            "Manual component selection: choose components using the dropdowns above. "
            "Rankings below are for inspection only."
        )
    else:
        st.warning(AUTO_PICK_EXPERIMENTAL_LABEL)

    if result.component_choices is None:
        st.info("No component choices are available without an imported Components.xml catalog.")
        return

    summary_rows = _choice_summary_rows(result.component_choices.choices)
    if summary_rows:
        st.dataframe(summary_rows, use_container_width=True, hide_index=True)

    has_rows = False
    for section, title in CHOICE_SECTIONS:
        recommendations = choice_recommendations_for_section(result, section)
        if not recommendations:
            continue
        has_rows = True
        with st.expander(title, expanded=section == "engine"):
            for recommendation in recommendations:
                st.markdown(f"**{choice_type_label(recommendation.choice_type)}**")
                if recommendation.recommended_choice:
                    st.markdown(
                        f"Recommended: **{recommendation.recommended_choice.display_name}** | "
                        f"Confidence: **{recommendation.confidence}** | "
                        f"Suitability: **{recommendation.candidates[0].total_score:.0f}**"
                    )
                    if recommendation.alternatives:
                        alt_names = ", ".join(
                            choice.display_name for choice in recommendation.alternatives[:3]
                        )
                        st.markdown(f"Alternatives: {alt_names}")
                    if recommendation.candidates[0].penalties:
                        st.markdown(
                            "Penalties (recommended): "
                            + "; ".join(recommendation.candidates[0].penalties)
                        )
                    st.caption(recommendation.reason)
                candidate_rows = _candidate_table_rows(recommendation)
                if candidate_rows:
                    st.dataframe(candidate_rows, use_container_width=True, hide_index=True)
                for warning in recommendation.warnings:
                    if warning != AUTO_PICK_EXPERIMENTAL_LABEL:
                        st.caption(warning)

    if not has_rows:
        st.write("No component choices matched the current year, skills, and filters.")


def render_slider_controls(result: DesignOptimizationResult) -> None:
    """Render recommended slider values section."""
    st.markdown("## Recommended slider values")
    st.caption(
        "Wiki-defined GearCity controls with source-backed formula influence. Output stats "
        "like Power, Torque, and Fuel belong in predicted outputs, not here."
    )
    slider_result = result.slider_result
    if slider_result.optimization_disabled:
        st.warning(
            "Wiki mechanics sources are missing. Run `gearcity-optimizer setup-sources` "
            "to build the source-backed optimizer model."
        )
        return
    for section, title in SLIDER_SECTIONS:
        section_settings = control_settings_for_section(slider_result, section)
        if not section_settings:
            continue
        with st.expander(title, expanded=section in {"chassis", "engine", "gearbox"}):
            st.dataframe(
                _slider_table_rows(section_settings),
                use_container_width=True,
                hide_index=True,
            )


def render_predicted_outputs(result: DesignOptimizationResult) -> None:
    """Render predicted output stats section."""
    st.markdown("## Predicted output stats")
    if result.slider_result.optimization_disabled:
        st.info("Predicted outputs require the source-backed wiki mechanics model.")
        return
    predicted_rows = [
        {
            "Output stat": item.label,
            "Predicted/proxy value": round(item.value, 2),
            "Importance": round(item.target_weight, 3),
            "Reason": item.reason,
            "Proxy": "yes" if item.is_proxy else "no",
            "Flag": (
                "low for priority"
                if result.objective
                and item.label in result.objective.poor_priority_stats
                else ""
            ),
        }
        for item in result.slider_result.predicted_outputs
    ]
    st.dataframe(predicted_rows, use_container_width=True, hide_index=True)
    if result.objective is not None:
        st.metric("Objective score", result.objective.objective_score)


def render_component_parsing_audit() -> None:
    """Show parsed component choice categories and parsing confidence."""
    st.markdown("##### Component parsing audit")
    source = discover_components_source()
    catalog = load_imported_components_catalog()
    if catalog is None:
        st.warning(
            "Component categories are not parsed confidently yet. Auto-pick may be "
            "low-confidence until Components.xml is imported."
        )
        return

    choice_audit = audit_component_choice_types(catalog)
    rows = format_choice_type_audit_summary(choice_audit)
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.write("No component choice types were parsed from the imported catalog.")

    st.caption(
        f"Source: {source.name if source else 'Imported catalog'} | "
        f"Total entries: {choice_audit.total_entries} | "
        f"Unknown mappings: {choice_audit.unknown_count}"
    )

    key_types = (
        "engine_layout",
        "fuel_type",
        "valvetrain",
        "forced_induction",
        "frame",
        "suspension",
        "drivetrain",
        "gearbox_type",
    )
    found = {row.choice_type for row in choice_audit.choice_types}
    missing = [choice_type_label(item) for item in key_types if item not in found]
    if missing:
        st.warning(
            "Some expected choice categories were not found: "
            + ", ".join(missing)
            + ". Auto-pick may be low-confidence for those sections."
        )
    if choice_audit.unknown_count or any(row.low_confidence_count for row in choice_audit.choice_types):
        st.warning(
            "Component categories are not parsed confidently yet. Auto-pick may be low-confidence."
        )


def render_design_optimizer_results(
    *,
    result: DesignOptimizationResult,
    vehicle_type_name: str,
    year: int,
    cost_mode_label: str,
    availability: ComponentAvailabilityContext,
) -> None:
    """Render full design optimizer output."""
    slider_result = result.slider_result
    metric_cols = st.columns(8)
    metric_cols[0].metric("Vehicle type", vehicle_type_name)
    metric_cols[1].metric("Cost mode", cost_mode_label)
    metric_cols[2].metric("Year", year)
    metric_cols[3].metric("Component choices", len(result.component_choices.choices) if result.component_choices else 0)
    metric_cols[4].metric("Slider values", len(slider_result.control_settings))
    metric_cols[5].metric("Available tech", availability.available_count)
    metric_cols[6].metric("Locked tech", availability.locked_count)
    metric_cols[7].metric(
        "Objective score",
        result.objective.objective_score if result.objective else "n/a",
    )

    st.download_button(
        "Download design recommendations as CSV",
        data=design_result_to_csv(result),
        file_name=f"{vehicle_type_name.lower().replace(' ', '_')}_{year}_design.csv",
        mime="text/csv",
    )

    st.divider()
    render_component_choices(result)
    st.divider()
    render_slider_controls(result)
    st.divider()
    render_predicted_outputs(result)

    st.divider()
    st.markdown("## Tradeoffs")
    for item in slider_result.tradeoffs:
        st.markdown(f"- {item}")

    combined_warnings = result.warnings + slider_result.warnings
    if combined_warnings:
        st.markdown("### Warnings")
        for item in combined_warnings:
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
        "Recommend discrete component/dropdown choices and exact numeric slider controls "
        "using vehicle type priorities, cost mode, year, research skills, and imported "
        "Components.xml availability."
    )
    if is_auto_experimental_component_mode():
        st.warning(AUTO_PICK_EXPERIMENTAL_LABEL)
    status_message = registry_status_message()
    if status_message:
        if wiki_model_available():
            st.info(status_message)
        else:
            st.warning(status_message)

    st.markdown("#### Optimizer controls")
    st.caption(
        "Year and research skills are set in the sidebar under "
        "Design Optimizer / Tech Availability."
    )
    render_optimizer_controls()
    session = get_design_session_values()
    availability = availability_context_from_session(session)

    available_choices = get_available_component_choices(
        session.year,
        session.chassis_skill,
        session.engine_skill,
        session.gearbox_skill,
        session.vehicle_skill,
    )
    manual_choices: dict[str, ComponentChoice] | None = None
    if is_manual_component_mode() and available_choices:
        st.markdown("#### Manual component selections")
        manual_choices = _render_manual_choice_inputs(available_choices)

    st.divider()
    render_components_status_summary(
        availability,
        available_choice_count=len(available_choices),
    )

    design_result = optimize_design(
        DesignOptimizationInput(
            vehicle_type=vehicle_type,
            year=session.year,
            cost_mode=session.cost_mode,
            chassis_skill=session.chassis_skill,
            engine_skill=session.engine_skill,
            gearbox_skill=session.gearbox_skill,
            vehicle_skill=session.vehicle_skill,
            depth=session.optimization_depth,  # type: ignore[arg-type]
            component_choice_mode="manual" if is_manual_component_mode() else "auto",
            manual_choices=manual_choices,
        )
    )

    st.divider()
    render_design_optimizer_results(
        result=design_result,
        vehicle_type_name=vehicle_type_name,
        year=session.year,
        cost_mode_label=session.cost_mode_label,
        availability=availability,
    )

    with st.expander("Component parsing audit", expanded=False):
        render_component_parsing_audit()

    with st.expander("Slider & Formula Audit", expanded=False):
        st.caption(
            "Source-backed slider definitions and formula influence map from GearCity Wiki "
            "mechanics pages. Formula-model optimized from parsed wiki pseudo-code."
        )
        for warning in slider_audit_warnings():
            st.warning(warning)

        st.markdown("##### Slider definitions")
        definition_rows = slider_definition_rows()
        if definition_rows:
            st.dataframe(definition_rows, use_container_width=True, hide_index=True)
        else:
            st.write("No slider definitions loaded.")

        st.markdown("##### Formula influence map")
        influence_rows = formula_influence_rows()
        if influence_rows:
            st.dataframe(influence_rows, use_container_width=True, hide_index=True)
        else:
            st.write("No formula influence data loaded. Run `gearcity-optimizer setup-sources`.")

        variables = list_slider_variables()
        if variables:
            selected = st.selectbox("Inspect one slider", variables, key="slider_formula_audit_select")
            detail = slider_detail(selected)
            if "error" not in detail:
                st.markdown(f"**UI label:** {detail['UI label']}")
                st.markdown(f"**Formula variable:** {detail['formula variable']}")
                st.markdown(f"**Wiki description:** {detail['wiki description']}")
                st.markdown(f"**Source page:** {detail['source page']}")
                st.markdown(f"**Affected outputs:** {', '.join(detail['affected outputs']) or 'None parsed'}")
                if detail["formula snippets"]:
                    st.markdown("**Source snippets**")
                    for snippet in detail["formula snippets"]:
                        st.code(snippet)

        st.markdown("##### Screenshot label fixture (audit only)")
        st.caption("Visual UI validation only. Labels only, no formula effects.")
        screenshot_rows = screenshot_label_audit_rows()
        if screenshot_rows:
            st.dataframe(screenshot_rows, use_container_width=True, hide_index=True)

        st.markdown("##### Optimizer slider controls")
        rows = slider_audit_rows()
        if rows:
            st.dataframe(rows, use_container_width=True, hide_index=True)
