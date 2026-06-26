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
from gearcity_optimizer.reports.component_choice_recommender import (
    ChoiceRecommendation,
    LOW_CONFIDENCE_PAGE_WARNING,
    auto_pick_status_label,
    has_low_confidence_auto_picks,
    suggested_choice_column_label,
)
from gearcity_optimizer.reports.design_optimizer import (
    DesignOptimizationInput,
    DesignOptimizationResult,
    choice_recommendations_for_section,
    optimize_design,
)
from gearcity_optimizer.reports.design_physical_constraints import physical_fit_summary_lines
from gearcity_optimizer.reports.slider_optimizer import (
    SliderOptimizationResult,
    control_settings_for_section,
)
from gearcity_optimizer.ui.design_session import (
    AUTO_PICK_EXPERIMENTAL_LABEL,
    LLM_ASSISTED_EXPERIMENTAL_LABEL,
    availability_context_from_session,
    build_llm_config_from_session,
    get_design_session_values,
    init_design_session_state,
    is_auto_experimental_component_mode,
    is_llm_recommendation_mode,
    is_manual_component_mode,
    render_optimizer_controls,
    render_shared_year_skill_panel,
)
from gearcity_optimizer.llm.config import LLM_NOT_CONFIGURED_MESSAGE, is_llm_configured
from gearcity_optimizer.llm.strategy_client import list_ollama_models, ollama_is_reachable
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


def _design_optimizer_run_fingerprint(
    *,
    vehicle_type_name: str,
    session,
    manual_choices: dict[str, ComponentChoice] | None,
) -> str:
    """Stable key for whether sidebar/control inputs changed since the last run."""
    init_design_session_state()
    manual_part = tuple(sorted((key, choice.name) for key, choice in (manual_choices or {}).items()))
    llm_config = build_llm_config_from_session()
    parts = (
        vehicle_type_name,
        str(session.year),
        str(session.quarter),
        f"{session.chassis_skill:.2f}",
        f"{session.engine_skill:.2f}",
        f"{session.gearbox_skill:.2f}",
        f"{session.vehicle_skill:.2f}",
        session.cost_mode,
        session.optimization_depth,
        str(st.session_state.component_choice_mode),
        str(st.session_state.recommendation_mode),
        llm_config.backend,
        llm_config.model,
        repr(manual_part),
    )
    return "|".join(parts)


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
        "Save Calibration",
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
        top_choice = item.top_candidate or top.choice
        suggested_name = top_choice.display_name if top_choice else ""
        rows.append(
            {
                "Choice type": choice_type_label(item.choice_type),
                "Auto-pick status": auto_pick_status_label(item.auto_pick_status),
                "Suggested choice / top candidate": suggested_name,
                "Suitability": top.total_score,
                "Confidence": item.confidence,
                "Alternatives": ", ".join(
                    choice.display_name for choice in item.alternatives[:3]
                ),
                "Penalties": "; ".join(top.penalties),
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
    writer.writerow(
        [
            "record_type",
            "section",
            "choice_type",
            "auto_pick_status",
            "suggested_choice_or_top_candidate",
            "suitability",
            "confidence",
            "alternatives",
            "penalties",
            "reason",
        ]
    )

    if result.selected_design_choices:
        writer.writerow([])
        writer.writerow(["record_type", "section", "choice_type", "accepted_choice"])
        for choice_type, choice in sorted(result.selected_design_choices.items()):
            writer.writerow(
                ["accepted_design_choice", choice.section, choice_type, choice.display_name]
            )
        writer.writerow([])

    if result.component_choices is not None:
        for recommendation in result.component_choices.choices:
            if not recommendation.candidates:
                continue
            top = recommendation.candidates[0]
            top_choice = recommendation.top_candidate or top.choice
            writer.writerow(
                [
                    "component_choice",
                    recommendation.section,
                    recommendation.choice_type,
                    recommendation.auto_pick_status,
                    top_choice.display_name if top_choice else "",
                    top.total_score,
                    recommendation.confidence,
                    ", ".join(
                        choice.display_name for choice in recommendation.alternatives[:3]
                    ),
                    "; ".join(top.penalties),
                    recommendation.reason,
                ]
            )

    writer.writerow([])
    writer.writerow(
        [
            "record_type",
            "section",
            "field",
            "value",
            "extra",
            "reason",
            "confidence",
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
        f"**{available_choice_count}** selectable choices for "
        f"{context.year} Q{context.quarter} at the current skill levels."
    )


def render_llm_strategy_summary(result: DesignOptimizationResult) -> None:
    """Render validated LLM strategy summary."""
    st.markdown("## LLM strategy summary")
    validation = result.llm_validation
    if validation is None:
        st.info("No LLM strategy was requested for this run.")
        return

    if not validation.llm_available:
        st.warning(validation.llm_error or LLM_NOT_CONFIGURED_MESSAGE)
        return

    st.caption(
        f"Using local/backend model: {validation.backend_label or validation.model_name}"
    )
    st.info(validation.validation_summary)

    if result.llm_repair_attempts:
        st.markdown(f"**Auto-repair attempts:** {result.llm_repair_attempts}")
        for note in result.llm_repair_notes:
            if "improved" in note.lower() or "satisfied" in note.lower():
                st.success(note)
            elif "stopped" in note.lower() or "did not" in note.lower():
                st.warning(note)
            else:
                st.caption(note)

    strategy = validation.strategy
    if strategy is None:
        return

    if strategy.explanation:
        st.markdown(f"**Reasoning:** {strategy.explanation}")
    if strategy.expected_tradeoffs:
        st.markdown("**Expected tradeoffs**")
        for item in strategy.expected_tradeoffs:
            st.markdown(f"- {item}")
    if strategy.risks:
        st.markdown("**Risks**")
        for item in strategy.risks:
            st.markdown(f"- {item}")

    if validation.component_validations:
        st.markdown("**Validated component choices**")
        rows = [
            {
                "Choice type": item.choice_type,
                "LLM choice": item.llm_choice,
                "Validation": item.validation_status,
                "Accepted choice": (
                    item.accepted_choice.display_name if item.accepted_choice else ""
                ),
                "Reason": item.reason,
            }
            for item in validation.component_validations
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)

    if validation.slider_validations:
        st.markdown("**Validated slider guidance**")
        rows = [
            {
                "Section": item.section,
                "Slider": item.slider_label,
                "Validation": item.validation_status,
                "Direction": item.direction,
                "Reason": item.reason,
            }
            for item in validation.slider_validations
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)


def render_component_choices(result: DesignOptimizationResult) -> None:
    """Render recommended component choices section."""
    st.markdown("## Component choices")
    if result.selected_design_choices:
        st.markdown("### Accepted design choices (global search winner)")
        accepted_rows = [
            {
                "Choice type": choice_type_label(choice_type),
                "Accepted choice": choice.display_name,
            }
            for choice_type, choice in sorted(result.selected_design_choices.items())
        ]
        st.dataframe(accepted_rows, use_container_width=True, hide_index=True)

    st.markdown("### Candidate rankings and alternatives")
    if result.component_choice_mode == "manual":
        st.caption(
            "Manual component selection: choose components using the dropdowns above. "
            "Rankings below are for inspection only."
        )
    else:
        st.warning(AUTO_PICK_EXPERIMENTAL_LABEL)
        if result.component_choices and has_low_confidence_auto_picks(result.component_choices):
            st.warning(LOW_CONFIDENCE_PAGE_WARNING)

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
                top_choice = recommendation.top_candidate
                if top_choice and recommendation.candidates:
                    top_score = recommendation.candidates[0]
                    st.markdown(
                        f"Auto-pick status: **{auto_pick_status_label(recommendation.auto_pick_status)}**"
                    )
                    st.markdown(
                        f"{suggested_choice_column_label(recommendation.auto_pick_status)}: "
                        f"**{top_choice.display_name}** | "
                        f"Confidence: **{recommendation.confidence}** | "
                        f"Suitability: **{top_score.total_score:.1f}**"
                    )
                    if recommendation.alternatives:
                        alt_names = ", ".join(
                            choice.display_name for choice in recommendation.alternatives[:3]
                        )
                        st.markdown(f"Alternatives: {alt_names}")
                    if top_score.penalties:
                        st.markdown("Penalties: " + "; ".join(top_score.penalties))
                    st.caption(recommendation.reason)
                    if recommendation.auto_pick_status in {
                        "low_confidence_candidate",
                        "not_recommended",
                    }:
                        st.warning(
                            "No reliable auto-pick found for this choice type. "
                            "Select manually or inspect alternatives."
                        )
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


def render_priority_explanation(result: DesignOptimizationResult) -> None:
    """Explain why vehicle-type priorities drive the global optimizer."""
    st.markdown("## Why these priorities matter")
    for note in result.priority_explanation:
        st.markdown(f"- {note}")


def render_best_design_summary(result: DesignOptimizationResult) -> None:
    """Render the globally best complete design summary."""
    st.markdown("## Best complete design found")
    score = result.design_score
    if score is None:
        st.info("Global design scoring is unavailable without predicted outputs.")
        return

    status = score.quality_status
    if status == "Good":
        st.success(f"Design status: **{status}** | Global objective score: **{score.total_score:.1f}**")
    elif status == "Usable":
        st.info(f"Design status: **{status}** | Global objective score: **{score.total_score:.1f}**")
    else:
        st.error(f"Design status: **{status}** | Global objective score: **{score.total_score:.1f}**")

    if result.best_design_summary:
        st.markdown(result.best_design_summary)
    if result.searched_component_sets:
        st.caption(
            f"Searched **{result.searched_component_sets}** complete component combinations "
            "with global slider optimization."
        )
    if score.failed_thresholds:
        st.warning(
            "Failed or weak thresholds: " + ", ".join(score.failed_thresholds)
        )


def render_alternatives_considered(result: DesignOptimizationResult) -> None:
    """Show alternative complete designs that scored lower."""
    if not result.alternative_designs:
        return
    st.markdown("## Alternatives considered")
    rows = []
    for index, alt in enumerate(result.alternative_designs, start=1):
        fuel = alt.design_score.stat_values.get("fuel")
        overall = alt.design_score.stat_values.get("overall")
        dependability = alt.design_score.stat_values.get("dependability")
        rows.append(
            {
                "Rank": index + 1,
                "Score": round(alt.design_score.total_score, 1),
                "Quality": alt.design_score.quality_status,
                "Fuel": round(fuel, 1) if fuel is not None else "",
                "Overall": round(overall, 1) if overall is not None else "",
                "Dependability": round(dependability, 1) if dependability is not None else "",
                "Why rejected": alt.rejection_reason or "",
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)


def render_predicted_outputs(result: DesignOptimizationResult) -> None:
    """Render predicted output stats section."""
    st.markdown("## Predicted output stats")
    if result.slider_result.optimization_disabled:
        st.info("Predicted outputs require the source-backed wiki mechanics model.")
        return

    score = result.design_score
    predicted_rows = []
    for item in result.slider_result.predicted_outputs:
        target = ""
        status = ""
        if score is not None:
            for stat_label, stat_status in score.stat_statuses.items():
                if stat_label.lower() in item.label.lower() or item.label.lower() in stat_label.lower():
                    status = stat_status
                    break
            for stat_key, stat_target in score.stat_targets.items():
                if stat_key in item.output_key or stat_key.replace("_", " ") in item.label.lower():
                    target = f"{stat_target:.0f}+"
                    break
        predicted_rows.append(
            {
                "Output stat": item.label,
                "Predicted value": round(item.value, 2),
                "Importance": round(item.target_weight, 3),
                "Target": target,
                "Status": status,
                "Proxy": "yes" if item.is_proxy else "no",
            }
        )
    st.dataframe(predicted_rows, use_container_width=True, hide_index=True)
    if result.objective is not None:
        st.markdown(f"**Global objective score:** {result.objective.objective_score:.2f}")
    if score is not None and score.quality_status in {"Poor", "Failed"}:
        st.error(
            "Best design found is still "
            f"{score.quality_status}. Predicted outputs remain below vehicle-type targets."
        )


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


def render_physical_fit(result: DesignOptimizationResult) -> None:
    """Show torque margin and engine bay fit from formula-backed checks."""
    fit = result.design_score.physical_fit if result.design_score else None
    if fit is None:
        return
    lines = physical_fit_summary_lines(fit)
    if not lines:
        return
    st.markdown("## Physical fit checks")
    st.caption(
        "Hard constraints from wiki formulas: engine torque must fit gearbox capacity; "
        "engine size must fit the chassis bay."
    )
    for line in lines:
        if line.startswith("ISSUE:"):
            st.error(line.removeprefix("ISSUE: ").strip())
        elif line.startswith("NOTE:"):
            st.warning(line.removeprefix("NOTE: ").strip())
        else:
            st.markdown(f"- {line}")


def render_run_diagnostics(result: DesignOptimizationResult) -> None:
    """Show what the optimizer did behind the scenes."""
    diagnostics = result.diagnostics
    if diagnostics is None:
        return
    with st.expander("Run diagnostics (what happened behind the scenes)", expanded=False):
        for line in diagnostics.lines:
            if line.startswith("ISSUE:"):
                st.error(line)
            elif line.startswith("NOTE:"):
                st.info(line)
            else:
                st.text(line)


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
    summary_items = (
        ("Vehicle type", vehicle_type_name),
        ("Cost mode", cost_mode_label),
        ("Year", str(year)),
        (
            "Component choices",
            str(len(result.component_choices.choices) if result.component_choices else 0),
        ),
        ("Slider values", str(len(slider_result.control_settings))),
        ("Available tech", str(availability.available_count)),
        ("Locked tech", str(availability.locked_count)),
        (
            "Objective score",
            str(result.objective.objective_score) if result.objective else "n/a",
        ),
        (
            "Design quality",
            result.design_score.quality_status if result.design_score else "n/a",
        ),
    )
    summary_cols = st.columns(len(summary_items))
    for column, (label, value) in zip(summary_cols, summary_items):
        column.markdown(f"**{label}**  \n{value}")

    st.download_button(
        "Download design recommendations as CSV",
        data=design_result_to_csv(result),
        file_name=f"{vehicle_type_name.lower().replace(' ', '_')}_{year}_design.csv",
        mime="text/csv",
    )

    st.divider()
    render_run_diagnostics(result)
    render_priority_explanation(result)
    st.divider()
    render_best_design_summary(result)
    st.divider()
    if result.recommendation_mode == "llm":
        render_llm_strategy_summary(result)
        st.divider()
    render_component_choices(result)
    st.divider()
    render_slider_controls(result)
    st.divider()
    render_physical_fit(result)
    render_predicted_outputs(result)
    st.divider()
    render_alternatives_considered(result)

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
    render_shared_year_skill_panel()
    st.divider()
    if is_auto_experimental_component_mode() and not is_llm_recommendation_mode():
        st.warning(AUTO_PICK_EXPERIMENTAL_LABEL)
    status_message = registry_status_message()
    if status_message:
        if wiki_model_available():
            st.info(status_message)
        else:
            st.warning(status_message)

    st.markdown("#### Optimizer controls")
    st.caption(
        "Click **Run optimization** below when you are ready. "
        "Changing options does not re-run the search automatically."
    )
    render_optimizer_controls()
    if is_llm_recommendation_mode():
        st.warning(LLM_ASSISTED_EXPERIMENTAL_LABEL)
        st.caption(
            "LLM mode skips multi-candidate beam search when the model picks valid components. "
            "If physical fit fails (torque, engine bay), the LLM auto-repairs and re-runs "
            "optimization up to 2 times."
        )
        llm_config = build_llm_config_from_session()
        if is_llm_configured(llm_config):
            if llm_config.backend == "ollama":
                if ollama_is_reachable(llm_config):
                    st.success(
                        f"Local Ollama ready at {llm_config.base_url} using model "
                        f"{llm_config.model}."
                    )
                else:
                    st.warning(
                        "Could not reach local Ollama. Start Ollama or switch to "
                        "Deterministic only."
                    )
            else:
                st.info(f"Using LLM backend: {llm_config.backend} ({llm_config.model})")
        else:
            st.warning(LLM_NOT_CONFIGURED_MESSAGE)
    session = get_design_session_values()
    availability = availability_context_from_session(session)

    available_choices = get_available_component_choices(
        session.year,
        session.chassis_skill,
        session.engine_skill,
        session.gearbox_skill,
        session.vehicle_skill,
        quarter=session.quarter,
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

    init_design_session_state()
    run_fingerprint = _design_optimizer_run_fingerprint(
        vehicle_type_name=vehicle_type_name,
        session=session,
        manual_choices=manual_choices,
    )
    run_col, _ = st.columns([1, 3])
    with run_col:
        run_clicked = st.button("Run optimization", type="primary", key="run_design_optimizer")

    cached_result: DesignOptimizationResult | None = st.session_state.design_optimizer_result
    cached_fingerprint = st.session_state.design_optimizer_run_fingerprint

    if run_clicked:
        with st.spinner("Running design optimization..."):
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
                    recommendation_mode="llm" if is_llm_recommendation_mode() else "deterministic",
                    llm_config=build_llm_config_from_session(),
                    quarter=session.quarter,
                    available_choices=available_choices,
                )
            )
            st.session_state.design_optimizer_result = design_result
            st.session_state.design_optimizer_run_fingerprint = run_fingerprint
            cached_result = design_result
            cached_fingerprint = run_fingerprint

    if cached_result is None:
        st.info(
            "Configure settings above, then click **Run optimization**. "
            "The search does not run automatically when you change year, skills, or other options."
        )
        return

    if cached_fingerprint != run_fingerprint:
        st.warning(
            "Settings changed since the last run. Click **Run optimization** to refresh results."
        )

    design_result = cached_result

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
