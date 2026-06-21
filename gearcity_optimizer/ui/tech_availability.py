"""Streamlit helpers for the Tech Availability tab."""

from __future__ import annotations

import streamlit as st

from gearcity_optimizer.core.component_availability import (
    MISSING_CATALOG_WARNING,
    ComponentAvailabilityContext,
)
from gearcity_optimizer.importers.component_sources import (
    components_missing_message,
    discover_components_source,
    import_components_from_path,
    import_components_xml,
)
from gearcity_optimizer.importers.components_xml import (
    ComponentsValidationError,
    catalog_summary,
    load_imported_components_catalog,
    validate_components_xml,
)
from gearcity_optimizer.ui.design_session import (
    availability_context_from_session,
    get_design_session_values,
)

EMPTY_STATE_MESSAGE = MISSING_CATALOG_WARNING

EXAMPLE_COMPONENTS_PATH = (
    r"D:\SteamLibrary\steamapps\common\GearCity\media\Scripts\Components.xml"
)

DESIGN_OPTIMIZER_NOTE = (
    "Use **Design Optimizer** for exact recommended design controls. This tab only "
    "shows which technologies/components are available for the selected year and "
    "research skills."
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


def render_availability_tables(context: ComponentAvailabilityContext) -> None:
    """Render available and locked component tables from shared context."""
    st.markdown(f"### Available components ({context.available_count})")
    st.caption("Sub-components unlocked for the selected year and design skills.")
    if context.available_rows:
        st.dataframe(
            [_row_dict(row) for row in context.available_rows],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.write("No available components match the current filters.")

    with st.expander(
        f"Locked / unavailable components ({context.locked_count})",
        expanded=False,
    ):
        st.caption(
            "Components blocked by unlock year, required skill, expiry, or the "
            "current category/name filter."
        )
        if context.locked_rows:
            st.dataframe(
                [_row_dict(row) for row in context.locked_rows],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.write("No locked components for the current filters.")


def render_tech_availability_tab(
    *,
    vehicle_type_name: str | None = None,
    vehicle_type=None,
) -> None:
    """Render Components.xml import and tech availability browser."""
    del vehicle_type_name, vehicle_type

    st.subheader("Tech Availability")
    st.caption(
        "Filter imported GearCity Components.xml entries by unlock year and "
        "research/design skill."
    )
    st.info(DESIGN_OPTIMIZER_NOTE)

    _render_import_panel(key_prefix="tech", expanded=False)

    source = discover_components_source()
    catalog = load_imported_components_catalog()

    st.caption(
        "Year and research skills are set in the sidebar under "
        "Design Optimizer / Tech Availability."
    )
    session = get_design_session_values()

    col_category, col_search = st.columns([1, 2])
    with col_category:
        category_filter = st.selectbox(
            "Category filter",
            options=["all", "chassis", "engine", "gearbox", "vehicle", "unknown"],
            key="tech_availability_category_filter",
        )
    with col_search:
        name_search = st.text_input(
            "Search by component name",
            value="",
            key="tech_availability_name_search",
        )

    category = None if category_filter == "all" else category_filter
    context = availability_context_from_session(
        session,
        category_filter=category,
        name_search=name_search or None,
    )

    if not context.catalog_loaded:
        st.warning(EMPTY_STATE_MESSAGE)
        for warning in context.warnings:
            st.caption(warning)
        return

    st.success(
        f"Loaded **{source.name if source else 'Components.xml'}** "
        f"({len(catalog.components)} entries from `{catalog.source_path}`)."
    )
    summary = catalog_summary(catalog)
    if summary:
        summary_text = ", ".join(f"{key}: {count}" for key, count in sorted(summary.items()))
        st.caption(f"Detected categories: {summary_text}")

    render_availability_tables(context)


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
                validation = validate_components_xml(uploaded.getvalue())
                for warning in validation.warnings:
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
