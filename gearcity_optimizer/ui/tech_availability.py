"""Streamlit helpers for the Tech Availability tab."""

from __future__ import annotations

import streamlit as st

from gearcity_optimizer.importers.component_sources import (
    components_missing_message,
    discover_components_source,
    import_components_from_path,
    import_components_xml,
)
from gearcity_optimizer.importers.components_xml import (
    ComponentsValidationError,
    catalog_summary,
    classify_components,
    load_imported_components_catalog,
    validate_components_xml,
)
from gearcity_optimizer.reports.part_recommender import (
    RecommendationInput,
    build_recommendation_result,
)

EMPTY_STATE_MESSAGE = (
    "No Components.xml has been imported yet. Import your GearCity "
    "Components.xml file to enable tech unlock and part availability analysis."
)

EXAMPLE_COMPONENTS_PATH = (
    r"D:\SteamLibrary\steamapps\common\GearCity\media\Scripts\Components.xml"
)


def tech_availability_empty_state_message() -> str:
    """Return the empty-state message for the Tech Availability tab."""
    return EMPTY_STATE_MESSAGE


def _row_dict(row) -> dict[str, object]:
    component = row.component
    return {
        "name": component.name,
        "category": component.category,
        "subcategory": component.subcategory or "",
        "start year": component.start_year,
        "end year": component.end_year,
        "required skill": component.required_skill,
        "skill category": row.skill_category,
        "availability status": row.status,
        "reason": row.reason,
    }


def render_tech_availability_tab(
    *,
    vehicle_type_name: str | None = None,
    vehicle_type=None,
) -> None:
    """Render Components.xml import and tech availability browser."""
    st.subheader("Tech Availability")
    st.caption(
        "Filter GearCity sub-components by unlock year and design skill. "
        "Import your own Components.xml from your game install."
    )

    source = discover_components_source()
    catalog = load_imported_components_catalog()

    if catalog is None:
        st.info(EMPTY_STATE_MESSAGE)
        _render_import_panel(key_prefix="empty", expanded=True)
        return

    st.success(
        f"Loaded **{source.name if source else 'Components.xml'}** "
        f"({len(catalog.components)} entries from `{catalog.source_path}`)."
    )
    summary = catalog_summary(catalog)
    if summary:
        summary_text = ", ".join(f"{key}: {count}" for key, count in sorted(summary.items()))
        st.caption(f"Detected categories: {summary_text}")

    col_year, col_chassis, col_engine = st.columns(3)
    col_gearbox, col_vehicle, col_category = st.columns(3)

    with col_year:
        year = st.number_input(
            "Year",
            min_value=1900,
            max_value=2100,
            value=1900,
            key="tech_availability_year",
        )
    with col_chassis:
        chassis_skill = st.number_input(
            "Chassis skill",
            min_value=0.0,
            max_value=100.0,
            value=0.0,
            step=1.0,
            key="tech_availability_chassis_skill",
        )
    with col_engine:
        engine_skill = st.number_input(
            "Engine skill",
            min_value=0.0,
            max_value=100.0,
            value=0.0,
            step=1.0,
            key="tech_availability_engine_skill",
        )
    with col_gearbox:
        gearbox_skill = st.number_input(
            "Gearbox skill",
            min_value=0.0,
            max_value=100.0,
            value=0.0,
            step=1.0,
            key="tech_availability_gearbox_skill",
        )
    with col_vehicle:
        vehicle_skill = st.number_input(
            "Vehicle / Coachwork skill",
            min_value=0.0,
            max_value=100.0,
            value=0.0,
            step=1.0,
            key="tech_availability_vehicle_skill",
        )
    with col_category:
        category_filter = st.selectbox(
            "Category filter",
            options=["all", "chassis", "engine", "gearbox", "vehicle", "unknown"],
            key="tech_availability_category_filter",
        )

    name_search = st.text_input(
        "Search by component name",
        value="",
        key="tech_availability_name_search",
    )

    skill_levels = {
        "chassis": float(chassis_skill),
        "engine": float(engine_skill),
        "gearbox": float(gearbox_skill),
        "vehicle": float(vehicle_skill),
    }
    category = None if category_filter == "all" else category_filter

    available_rows, locked_rows = classify_components(
        catalog,
        int(year),
        skill_levels,
        category_filter=category,
        name_search=name_search,
    )

    st.markdown(f"### Available components ({len(available_rows)})")
    if available_rows:
        st.dataframe(
            [_row_dict(row) for row in available_rows],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.write("No available components match the current filters.")

    st.markdown(f"### Locked / unavailable components ({len(locked_rows)})")
    if locked_rows:
        st.dataframe(
            [_row_dict(row) for row in locked_rows],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.write("No locked components for the current filters.")

    if vehicle_type is not None and vehicle_type_name:
        st.divider()
        st.markdown("### Recommendation preview (experimental)")
        cost_mode = st.selectbox(
            "Cost mode",
            options=["cheap", "balanced", "luxury"],
            key="tech_availability_cost_mode",
        )
        rec_input = RecommendationInput(
            vehicle_type_name=vehicle_type_name,
            year=int(year),
            cost_mode=cost_mode,
            chassis_skill=float(chassis_skill),
            engine_skill=float(engine_skill),
            gearbox_skill=float(gearbox_skill),
            vehicle_skill=float(vehicle_skill),
        )
        result = build_recommendation_result(
            vehicle_type=vehicle_type,
            inputs=rec_input,
            catalog=catalog,
        )
        st.write(
            f"Available tech entries: **{result.available_component_count}** | "
            f"Locked/unavailable: **{result.unavailable_component_count}**"
        )
        for note in result.limitations:
            st.caption(note)
        for bullet in result.recommended_focus:
            st.write(f"- {bullet}")

    st.divider()
    _render_import_panel(key_prefix="existing", expanded=False)


def _render_import_panel(*, key_prefix: str, expanded: bool) -> None:
    with st.expander("Import Components.xml", expanded=expanded):
        st.caption(
            "Example GearCity path (Steam install location may differ):\n\n"
            f"`{EXAMPLE_COMPONENTS_PATH}`"
        )

        uploaded = st.file_uploader(
            "Select Components.xml",
            type=["xml"],
            key=f"{key_prefix}_components_uploader",
        )
        import_name = st.text_input(
            "Import label",
            value="Default GearCity Components",
            key=f"{key_prefix}_components_name",
        )

        if uploaded is not None and st.button(
            "Import uploaded Components.xml",
            key=f"{key_prefix}_components_upload_button",
        ):
            try:
                result = validate_components_xml(uploaded.getvalue())
                for warning in result.warnings:
                    st.warning(warning)
                import_components_xml(
                    xml_content=uploaded.getvalue(),
                    name=import_name,
                    overwrite=True,
                )
                st.success("Components.xml imported successfully.")
                st.rerun()
            except (ComponentsValidationError, OSError, ValueError) as exc:
                st.error(str(exc))

        st.markdown("**Advanced: import from local path**")
        st.caption(
            "Local path import only works when the app is running on the same "
            "computer as the GearCity install. File upload is the safer option."
        )
        local_path = st.text_input(
            "Local Components.xml path",
            value="",
            placeholder=EXAMPLE_COMPONENTS_PATH,
            key=f"{key_prefix}_components_local_path",
        )
        if local_path.strip() and st.button(
            "Import from local path",
            key=f"{key_prefix}_components_path_button",
        ):
            try:
                import_components_from_path(
                    local_path.strip(),
                    name=import_name,
                    overwrite=True,
                )
                st.success("Components.xml imported successfully.")
                st.rerun()
            except (ComponentsValidationError, OSError, ValueError) as exc:
                st.error(str(exc))


def handle_missing_components_catalog() -> bool:
    """Return True when no catalog is loaded (for tests and guards)."""
    return load_imported_components_catalog() is None


def missing_components_guidance() -> str:
    """Return CLI-style guidance for missing Components.xml."""
    return components_missing_message()
