"""Streamlit helpers for the Historical Events / Timeline tab."""

from __future__ import annotations

import streamlit as st

from gearcity_optimizer.importers.map_sources import (
    MapSource,
    discover_map_sources,
    generate_map_id,
    import_map_from_path,
    import_map_turn_events,
)
from gearcity_optimizer.importers.turn_events_parser import (
    TurnEventsValidationError,
    load_turn_events_for_map,
)
from gearcity_optimizer.reports.danger_periods import (
    danger_periods_for_map,
    summarize_timeline,
)
from gearcity_optimizer.reports.stock_market_timeline import (
    format_rate_delta,
    format_stockrate,
    stock_market_timeline_for_map,
)

EMPTY_STATE_MESSAGE = (
    "No map event timelines have been imported yet. Import a `TurnEvents.xml` "
    "file from your GearCity map folder to enable historical timeline and "
    "danger-period analysis."
)

MAP_SPECIFIC_NOTE = (
    "TurnEvents files are map-specific. The Base City Map timeline may not "
    "match other maps."
)


def historical_events_empty_state_message() -> str:
    """Return the empty-state message for the Historical Events tab."""
    return EMPTY_STATE_MESSAGE


def render_historical_events_tab() -> None:
    """Render map import, selection, and danger-period analysis."""
    st.subheader("Historical Events / Timeline")
    st.caption(MAP_SPECIFIC_NOTE)

    maps = discover_map_sources()
    if not maps:
        st.info(EMPTY_STATE_MESSAGE)
        _render_import_panel(key_prefix="empty")
        return

    map_by_id = {source.id: source for source in maps}
    map_ids = [source.id for source in maps]
    default_index = 0

    selected_map_id = st.selectbox(
        "Selected map",
        options=map_ids,
        index=default_index,
        format_func=lambda map_id: f"{map_by_id[map_id].name} ({map_id})",
        key="historical_events_selected_map",
    )
    selected_map = map_by_id[selected_map_id]

    _render_timeline_summary(selected_map)
    st.divider()
    _render_stock_market_timeline(selected_map)
    st.divider()
    _render_danger_periods(selected_map)
    st.divider()
    _render_import_panel(key_prefix="existing")


def _render_timeline_summary(map_source: MapSource) -> None:
    timeline = load_turn_events_for_map(map_source)
    summary = summarize_timeline(timeline)
    st.markdown(f"### {map_source.name} timeline")
    st.write(f"Turns parsed: **{summary['turn_count']}**")
    if summary["year_start"] is not None and summary["year_end"] is not None:
        st.write(
            f"Years covered: **{summary['year_start']}** to **{summary['year_end']}**"
        )
    st.write(f"Turns with economy data: **{summary['turns_with_economy']}**")
    st.write(f"Turns with world events: **{summary['turns_with_world_events']}**")
    st.write(f"Turns with news events: **{summary['turns_with_news']}**")


def _render_stock_market_timeline(map_source: MapSource) -> None:
    rows_data = stock_market_timeline_for_map(map_source)
    st.markdown(f"### {map_source.name} stock market below base")
    st.caption(
        "Shows turns where the stock market multiplier is not the normal base "
        f"of {format_stockrate(1.0)}. Values are carried forward between "
        "explicit TurnEvents updates, including gradual crash recoveries."
    )
    if not rows_data:
        st.write("Stock market stayed at the base rate in this map timeline.")
        return

    rows = [
        {
            "Year": item.year,
            "Turn": item.turn,
            "Stock market rate": format_stockrate(item.stockrate),
            "vs base": format_rate_delta(item.delta_from_base),
            "Change from prev turn": format_rate_delta(item.delta_from_previous),
            "Updated this turn": "yes" if item.explicit_update else "carried",
        }
        for item in rows_data
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _render_danger_periods(map_source: MapSource) -> None:
    periods = danger_periods_for_map(map_source)
    st.markdown(f"### {map_source.name} danger periods")
    if not periods:
        st.write("No elevated danger periods were detected in this map timeline.")
        return

    rows = [
        {
            "Start": f"{period.start_year} turn {period.start_turn}",
            "End": f"{period.end_year} turn {period.end_turn}",
            "Type": period.danger_type,
            "Severity": period.severity,
            "Label": period.label,
            "Supporting turns": len(period.supporting_events),
        }
        for period in periods
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _session_map_fields(key_prefix: str) -> tuple[str, str]:
    """Read map name and id from Streamlit session state."""
    map_name = str(st.session_state.get(f"{key_prefix}_map_name", "Base City Map")).strip()
    map_id = str(st.session_state.get(f"{key_prefix}_map_id", "")).strip()
    if not map_id:
        map_id = generate_map_id(map_name)
    return map_name, map_id


def _render_import_panel(*, key_prefix: str) -> None:
    with st.expander("Import map TurnEvents.xml", expanded=not discover_map_sources()):
        map_name = st.text_input(
            "Map name",
            value="Base City Map",
            key=f"{key_prefix}_map_name",
        )
        suggested_map_id = generate_map_id(map_name)

        with st.expander("Advanced options"):
            if f"{key_prefix}_map_id" not in st.session_state:
                st.session_state[f"{key_prefix}_map_id"] = suggested_map_id
            st.text_input(
                "Map ID",
                key=f"{key_prefix}_map_id",
            )

        uploaded = st.file_uploader(
            "Select TurnEvents.xml",
            type=["xml"],
            key=f"{key_prefix}_turn_events_upload",
        )
        map_name_value, map_id_value = _session_map_fields(key_prefix)
        if uploaded is not None and st.button(
            "Import uploaded file",
            key=f"{key_prefix}_import_upload",
        ):
            try:
                import_map_turn_events(
                    map_id=map_id_value,
                    name=map_name_value,
                    xml_content=uploaded.getvalue(),
                    overwrite=False,
                )
                st.success(
                    f"Imported timeline for {map_name_value} as map id "
                    f"{map_id_value}."
                )
                st.rerun()
            except TurnEventsValidationError as exc:
                st.error(str(exc))
            except FileExistsError as exc:
                st.error(str(exc))
            except ValueError as exc:
                st.error(str(exc))

        with st.expander("Advanced: import from local path"):
            st.caption(
                "Works only when Streamlit is running locally on the same computer "
                "as your GearCity install. File upload is the recommended method."
            )
            with st.form(key=f"{key_prefix}_path_import_form", clear_on_submit=False):
                st.text_input(
                    "Full path to TurnEvents.xml",
                    placeholder=(
                        "D:\\SteamLibrary\\steamapps\\common\\GearCity\\media\\Maps\\"
                        "Base City Map\\scripts\\TurnEvents.xml"
                    ),
                    key=f"{key_prefix}_local_path",
                )
                submitted = st.form_submit_button("Import from path")

            if submitted:
                local_path = str(
                    st.session_state.get(f"{key_prefix}_local_path", "")
                ).strip()
                map_name_value, map_id_value = _session_map_fields(key_prefix)
                if not local_path:
                    st.error("Enter a full local path to TurnEvents.xml.")
                else:
                    try:
                        import_map_from_path(
                            map_id=map_id_value,
                            name=map_name_value,
                            source_path=local_path,
                            overwrite=False,
                        )
                        st.success(
                            f"Imported timeline for {map_name_value} from local path."
                        )
                        st.rerun()
                    except TurnEventsValidationError as exc:
                        st.error(str(exc))
                    except FileNotFoundError as exc:
                        st.error(str(exc))
                    except FileExistsError as exc:
                        st.error(str(exc))
                    except ValueError as exc:
                        st.error(str(exc))
