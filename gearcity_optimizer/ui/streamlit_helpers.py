"""Helpers for the Streamlit design checklist UI."""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from gearcity_optimizer.core.component_priorities import calculate_component_priorities
from gearcity_optimizer.core.models import VehicleType
from gearcity_optimizer.core.terminology import (
    DEPENDABILITY_LAYERS_MARKDOWN,
    DEPENDABILITY_LAYER_NOTE,
    DESIGN_SLIDER_SECTION_TITLE,
    DRIVEABILITY_HANDLING_NOTE,
    ENGINE_POWER_NOTE,
    FINAL_VEHICLE_RATING_SECTION_TITLE,
    GEARBOX_COMFORT_NOTE,
    HOW_TO_READ_PRIORITIES_MARKDOWN,
    TERMINOLOGY_AUDIT_CLI_HINT,
    list_terminology_audit_rows,
    list_terminology_layers,
)
from gearcity_optimizer.core.vehicle_types import load_vehicle_types
from gearcity_optimizer.data_sources import project_root as repo_root
from gearcity_optimizer.formula_browser import (
    wiki_sources_missing,
    wiki_sources_missing_message,
)
from gearcity_optimizer.reports.design_checklist import (
    DesignChecklistReport,
    build_design_checklist,
    format_final_vehicle_rating_priorities_from_vehicle_type,
    format_priority_table,
    render_design_checklist_markdown,
)
from gearcity_optimizer.reports.naming_guide import (
    MISSING_NAMING_GUIDE_MESSAGE,
    load_naming_guide_markdown,
)


def project_root() -> Path:
    """Return project root directory."""
    return repo_root()


def default_vehicle_types_path() -> str:
    """Default path to vehicle types CSV."""
    return str(project_root() / "data" / "vehicle_types.csv")


def list_vehicle_type_names(path: str) -> list[str]:
    """Load sorted vehicle type names from CSV."""
    return sorted(load_vehicle_types(path).keys())


def load_vehicle_type(path: str, name: str) -> VehicleType:
    """Load one vehicle type by name."""
    return load_vehicle_types(path)[name]


def generate_checklist(
    vehicle_type: VehicleType,
    year: int,
) -> DesignChecklistReport:
    """Build a design checklist report."""
    return build_design_checklist(vehicle_type, year=year)


def checklist_markdown(report: DesignChecklistReport) -> str:
    """Return markdown for a checklist report."""
    return render_design_checklist_markdown(report)


def component_priority_lines(
    vehicle_type: VehicleType,
) -> dict[str, list[str]]:
    """Return formatted priority lines per component category."""
    priorities = calculate_component_priorities(vehicle_type)
    return {
        component: format_priority_table(items, component)
        for component, items in priorities.items()
    }


def wiki_status(project_root_path: Path | None = None) -> dict[str, object]:
    """Summarize local wiki cache and formula index status."""
    root = project_root_path or project_root()
    formula_index = root / "generated" / "raw_parsed" / "wiki_formula_index.json"
    wiki_html = root / "sources" / "wiki_html"
    wiki_raw = root / "sources" / "wiki_raw"

    html_files = list(wiki_html.glob("*.html")) if wiki_html.exists() else []
    raw_files = list(wiki_raw.glob("*.txt")) if wiki_raw.exists() else []

    pages: dict[str, int] = {}
    if formula_index.exists():
        with formula_index.open(encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            pages = {name: len(sections) for name, sections in data.items()}

    return {
        "wiki_html_count": len(html_files),
        "wiki_raw_count": len(raw_files),
        "formula_index_exists": formula_index.exists(),
        "formula_pages": pages,
    }


def render_app() -> None:
    """Render the GearCity vehicle design helper Streamlit UI."""
    st.set_page_config(page_title="GearCity Vehicle Design Helper", layout="wide")
    st.title("GearCity Vehicle Design Helper")
    st.caption(
        "Deterministic checklists from vehicle type importance weights and "
        "component priority mappings."
    )

    with st.sidebar:
        st.header("Settings")
        types_path = st.text_input(
            "Vehicle types file",
            value=default_vehicle_types_path(),
        )
        try:
            vehicle_names = list_vehicle_type_names(types_path)
        except Exception as exc:
            st.error(f"Could not load vehicle types: {exc}")
            vehicle_names = []

        vehicle_type_name = (
            st.selectbox(
                "Vehicle type",
                options=vehicle_names,
                index=vehicle_names.index("Sedan") if "Sedan" in vehicle_names else 0,
            )
            if vehicle_names
            else None
        )

        year = st.number_input("Year", min_value=1899, max_value=2100, value=1901)
        generate = st.button("Generate Checklist", type="primary")

    if not vehicle_names or vehicle_type_name is None:
        st.warning("Load a valid vehicle types CSV to continue.")
        st.stop()

    vehicle_type = load_vehicle_type(types_path, vehicle_type_name)

    if "checklist_report" not in st.session_state:
        st.session_state.checklist_report = generate_checklist(vehicle_type, int(year))

    if generate:
        st.session_state.checklist_report = generate_checklist(vehicle_type, int(year))

    report = st.session_state.checklist_report
    priorities = component_priority_lines(vehicle_type)
    wiki = wiki_status()
    final_rating_lines = format_final_vehicle_rating_priorities_from_vehicle_type(
        vehicle_type,
        include_stars=True,
    )

    st.markdown(f"### Selected vehicle type: **{vehicle_type_name}**")

    tab_checklist, tab_priorities, tab_naming, tab_wiki, tab_packages = st.tabs(
        [
            "Design Checklist",
            "Component Priorities",
            "Naming Guide",
            "Wiki / Formula Tools",
            "Package Optimizer",
        ]
    )

    with tab_checklist:
        st.subheader(f"{report.vehicle_type} Design Checklist, {report.year}")

        st.markdown(f"## {FINAL_VEHICLE_RATING_SECTION_TITLE}")
        for line in final_rating_lines:
            st.write(line)

        st.divider()

        for section in report.sections:
            st.markdown(f"### {section.title}")
            for bullet in section.bullets:
                st.write(f"- {bullet}")

        st.markdown("### Things to avoid")
        for warning in report.warnings:
            st.write(f"- {warning}")

        st.download_button(
            "Download checklist as Markdown",
            data=checklist_markdown(report),
            file_name=(
                f"{report.vehicle_type.lower().replace(' ', '_')}_"
                f"{report.year}_checklist.md"
            ),
            mime="text/markdown",
        )

    with tab_priorities:
        st.subheader("Priorities and terminology")

        st.markdown(f"## {FINAL_VEHICLE_RATING_SECTION_TITLE}")
        st.caption(
            "Formula-backed final vehicle stats for the selected vehicle type. "
            "Matches the in-game New Car Design overview importance list."
        )
        for line in final_rating_lines:
            st.write(line)

        with st.expander("How to read these priorities"):
            st.markdown(HOW_TO_READ_PRIORITIES_MARKDOWN)

        st.divider()

        st.markdown("## Component Priorities")
        st.caption(
            "Translate final vehicle needs into chassis, engine, and gearbox focus "
            "areas. Labels follow GearCity Wiki formula names."
        )

        st.markdown("### Chassis")
        for line in priorities["chassis"]:
            st.text(line)

        st.markdown("")
        st.markdown("### Engine")
        for line in priorities["engine"]:
            st.text(line)
        st.caption(ENGINE_POWER_NOTE)

        st.markdown("")
        st.markdown("### Gearbox")
        for line in priorities["gearbox"]:
            st.text(line)
        st.caption(GEARBOX_COMFORT_NOTE)

        st.divider()

        st.markdown(f"## {DESIGN_SLIDER_SECTION_TITLE}")
        st.caption(
            "Design focus sliders, testing sliders, and material quality. "
            "Not the same as final vehicle rating importance above."
        )
        for line in priorities["vehicle_design"]:
            st.text(line)

        st.divider()

        st.markdown("## Terminology Notes / Audit")

        with st.expander("Terminology notes", expanded=True):
            st.markdown(DRIVEABILITY_HANDLING_NOTE)
            st.markdown("")
            st.markdown(DEPENDABILITY_LAYER_NOTE)
            st.markdown("")
            st.markdown(GEARBOX_COMFORT_NOTE)
            st.markdown("")
            st.markdown(ENGINE_POWER_NOTE)
            st.markdown("")
            st.markdown(
                "- Labels are based on GearCity Wiki formula names where available.\n"
                "- Some in-game screens may use different labels.\n"
                "- Mappings marked with uncertain status in the audit table are not "
                "confirmed as exact UI matches."
            )

        with st.expander("Dependability / reliability / durability layers"):
            st.markdown(DEPENDABILITY_LAYERS_MARKDOWN)
            for layer in list_terminology_layers():
                st.markdown(f"**{layer.name}** ({layer.level})")
                st.caption(layer.description)
                if layer.related_but_not_same_as:
                    st.caption(
                        "Related but not the same as: "
                        + ", ".join(layer.related_but_not_same_as)
                    )

        with st.expander("Terminology Audit"):
            st.caption(TERMINOLOGY_AUDIT_CLI_HINT)
            audit_rows = list_terminology_audit_rows()
            st.dataframe(
                audit_rows,
                use_container_width=True,
                hide_index=True,
            )
            drivability_entry = next(
                (
                    row
                    for row in audit_rows
                    if row["internal key"] == "drivability"
                    and row["component"] == "vehicle"
                ),
                None,
            )
            if drivability_entry:
                st.markdown("**Driveability vs Handling**")
                st.markdown(f"Status: `{drivability_entry['status']}`")
                st.markdown(drivability_entry["explanation"])

    with tab_naming:
        st.subheader("GearCity Component Naming Standard")
        naming_guide = load_naming_guide_markdown()
        if naming_guide is None:
            st.warning(MISSING_NAMING_GUIDE_MESSAGE)
        else:
            st.markdown(naming_guide)
            st.download_button(
                "Download naming guide as Markdown",
                data=naming_guide,
                file_name="component_naming_standard.md",
                mime="text/markdown",
            )

    with tab_wiki:
        st.subheader("Wiki / formula tools")
        if wiki_sources_missing(wiki):
            st.info(wiki_sources_missing_message())
        st.write(f"Cached wiki HTML files: {wiki['wiki_html_count']}")
        st.write(f"Cached wiki raw text files: {wiki['wiki_raw_count']}")
        st.write(
            "Formula index available:"
            f" {'yes' if wiki['formula_index_exists'] else 'no'}"
        )
        if wiki["formula_pages"]:
            st.markdown("**Formula pages**")
            for page, count in sorted(wiki["formula_pages"].items()):
                st.write(f"- {page}: {count} sections")

    with tab_packages:
        st.subheader("Package optimizer")
        st.warning("Experimental: advanced tool, not the main workflow.")
        st.write(
            "Use the CLI for package ranking and formula-backed component calculators:"
        )
        st.code(
            "python -m gearcity_optimizer.cli design-checklist "
            f"--vehicle-type {vehicle_type_name} --year {int(year)}"
        )
        st.code(
            "python -m gearcity_optimizer.cli packages --vehicle-type "
            f"{vehicle_type_name} --year {int(year)} --objective formula_fit"
        )
        st.caption("Placeholder tab for future simple package controls.")
