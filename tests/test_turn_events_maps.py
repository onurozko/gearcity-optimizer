"""Tests for map TurnEvents import, parsing, and danger periods."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gearcity_optimizer.cli import SUBCOMMANDS, main
from gearcity_optimizer.importers.map_sources import (
    discover_map_sources,
    generate_map_id,
    import_map_from_path,
    import_map_turn_events,
    load_map_source,
)
from gearcity_optimizer.importers.turn_events_parser import (
    TurnEventsValidationError,
    load_turn_events_for_map,
    parse_turn_events_xml,
    validate_turn_events_xml,
)
from gearcity_optimizer.reports.danger_periods import danger_periods_for_map
from gearcity_optimizer.ui.historical_events import historical_events_empty_state_message


@pytest.fixture
def fixture_xml_path() -> Path:
    return Path(__file__).resolve().parent / "fixtures" / "turn_events" / "sample_turn_events.xml"


@pytest.fixture
def user_maps_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    maps_dir = tmp_path / "maps"
    maps_dir.mkdir()
    monkeypatch.setattr(
        "gearcity_optimizer.importers.map_sources.user_maps_root",
        lambda: maps_dir,
    )
    return maps_dir


def test_validate_turn_events_requires_evts_root():
    with pytest.raises(TurnEventsValidationError, match="<Evts>"):
        validate_turn_events_xml("<root><year y='1900'><turn t='1'/></year></root>")


def test_invalid_xml_is_rejected():
    with pytest.raises(TurnEventsValidationError, match="Could not parse XML"):
        validate_turn_events_xml("<Evts><year")


def test_imported_xml_saved_to_user_data_maps(
    fixture_xml_path: Path,
    user_maps_dir: Path,
):
    xml_bytes = fixture_xml_path.read_bytes()
    import_map_turn_events(
        map_id="base_city",
        name="Base City Map",
        xml_content=xml_bytes,
    )

    saved_xml = user_maps_dir / "base_city" / "TurnEvents.xml"
    assert saved_xml.is_file()
    assert saved_xml.read_bytes() == xml_bytes


def test_map_json_is_created(fixture_xml_path: Path, user_maps_dir: Path):
    import_map_turn_events(
        map_id="base_city",
        name="Base City Map",
        xml_content=fixture_xml_path.read_bytes(),
    )

    metadata_path = user_maps_dir / "base_city" / "map.json"
    assert metadata_path.is_file()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata == {
        "id": "base_city",
        "name": "Base City Map",
        "description": "Imported GearCity map timeline.",
        "turn_events_file": "TurnEvents.xml",
    }


def test_map_discovery_finds_imported_maps(
    fixture_xml_path: Path,
    user_maps_dir: Path,
):
    import_map_turn_events(
        map_id="base_city",
        name="Base City Map",
        xml_content=fixture_xml_path.read_bytes(),
    )

    sources = discover_map_sources()
    assert len(sources) == 1
    assert sources[0].id == "base_city"
    assert sources[0].name == "Base City Map"
    assert sources[0].turn_events_file.name == "TurnEvents.xml"


def test_local_path_import_missing_file_shows_helpful_error(user_maps_dir: Path):
    with pytest.raises(FileNotFoundError, match="TurnEvents file not found"):
        import_map_from_path(
            map_id="base_city",
            name="Base City Map",
            source_path=user_maps_dir / "missing.xml",
        )


def test_historical_events_empty_state_message():
    message = historical_events_empty_state_message()
    assert "No map event timelines have been imported yet" in message
    assert "TurnEvents.xml" in message


def test_cli_import_map_and_list_maps_registered():
    assert "import-map" in SUBCOMMANDS
    assert "list-maps" in SUBCOMMANDS
    assert "danger-periods" in SUBCOMMANDS
    assert "events-summary" in SUBCOMMANDS


def test_danger_period_output_includes_map_id_and_name(
    fixture_xml_path: Path,
    user_maps_dir: Path,
):
    import_map_turn_events(
        map_id="base_city",
        name="Base City Map",
        xml_content=fixture_xml_path.read_bytes(),
    )
    map_source = load_map_source("base_city")
    periods = danger_periods_for_map(map_source)

    assert periods
    for period in periods:
        assert period.map_id == "base_city"
        assert period.map_name == "Base City Map"


def test_parse_turn_events_extracts_sections(fixture_xml_path: Path):
    timeline = parse_turn_events_xml(fixture_xml_path)
    assert len(timeline.turns) == 3

    first_turn = timeline.turns[0]
    assert first_turn.year == 1900
    assert first_turn.turn == 1
    assert first_turn.buyrate == pytest.approx(0.94)
    assert first_turn.stockrate == pytest.approx(0.88)
    assert first_turn.interest == pytest.approx(1.06)
    assert first_turn.gas == pytest.approx(1.5)
    assert first_turn.carprice == pytest.approx(1.4)
    assert first_turn.pension_growth == pytest.approx(1.003)
    assert len(first_turn.vehicle_pops) == 1
    assert first_turn.vehicle_pops[0].selected_index == 1087
    assert len(first_turn.news_comments) == 1
    assert first_turn.news_comments[0].image == "PanicOf1901.jpg"

    world_turn = timeline.turns[2]
    assert len(world_turn.city_changes) == 1
    assert world_turn.city_changes[0].city_id == "200"
    assert world_turn.city_changes[0].attributes["Nation"] == "Australia"


def test_generate_map_id_from_display_name():
    assert generate_map_id("Base City Map") == "base_city"


def test_cli_list_maps_reports_empty(capsys, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    maps_dir = tmp_path / "maps"
    maps_dir.mkdir()
    monkeypatch.setattr(
        "gearcity_optimizer.importers.map_sources.user_maps_root",
        lambda: maps_dir,
    )
    exit_code = main(["list-maps"])
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "No map timelines imported yet" in output


def test_load_turn_events_for_map_uses_metadata(
    fixture_xml_path: Path,
    user_maps_dir: Path,
):
    import_map_turn_events(
        map_id="base_city",
        name="Base City Map",
        xml_content=fixture_xml_path.read_bytes(),
    )
    map_source = load_map_source("base_city")
    timeline = load_turn_events_for_map(map_source)
    assert timeline.map_id == "base_city"
    assert timeline.map_name == "Base City Map"


def test_stock_market_timeline_lists_non_base_rates(fixture_xml_path: Path):
    from gearcity_optimizer.reports.stock_market_timeline import (
        build_stock_market_timeline,
    )

    timeline = parse_turn_events_xml(fixture_xml_path)
    rows = build_stock_market_timeline(timeline)

    assert len(rows) == 2
    assert rows[0].year == 1900
    assert rows[0].turn == 1
    assert rows[0].stockrate == pytest.approx(0.88)
    assert rows[0].delta_from_base == pytest.approx(-0.12)
    assert rows[0].explicit_update is True
    assert rows[0].delta_from_previous is None

    assert rows[1].year == 1900
    assert rows[1].turn == 2
    assert rows[1].stockrate == pytest.approx(0.88)
    assert rows[1].explicit_update is False
    assert rows[1].delta_from_previous == pytest.approx(0.0)
