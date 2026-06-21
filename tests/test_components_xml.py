"""Tests for Components.xml import, parsing, and tech availability."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gearcity_optimizer.cli import SUBCOMMANDS, main
from gearcity_optimizer.core.cost_mode import CostMode, parse_cost_mode
from gearcity_optimizer.importers.component_sources import (
    import_components_from_path,
)
from gearcity_optimizer.importers.components_xml import (
    ComponentsValidationError,
    ComponentTech,
    filter_available_components,
    infer_skill_category,
    is_component_available,
    load_imported_components_catalog,
    parse_components_xml,
    validate_components_xml,
    validate_year_input,
)
from gearcity_optimizer.ui.tech_availability import (
    handle_missing_components_catalog,
    tech_availability_empty_state_message,
)


@pytest.fixture
def fixture_xml_path() -> Path:
    return (
        Path(__file__).resolve().parent
        / "fixtures"
        / "components"
        / "sample_components.xml"
    )


@pytest.fixture
def components_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "components"
    root.mkdir()
    monkeypatch.setattr(
        "gearcity_optimizer.importers.component_sources.components_root",
        lambda: root,
    )
    return root


def test_valid_fake_components_xml_imports_successfully(
    fixture_xml_path: Path,
    components_dir: Path,
):
    import_components_from_path(fixture_xml_path)

    saved_xml = components_dir / "Components.xml"
    assert saved_xml.is_file()
    assert saved_xml.read_bytes() == fixture_xml_path.read_bytes()

    metadata = json.loads((components_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["components_file"] == "Components.xml"
    assert metadata["source"] == "user_import"


def test_invalid_xml_is_rejected():
    with pytest.raises(ComponentsValidationError, match="Could not parse XML"):
        validate_components_xml("<Components><ChassisComponents>")


def test_invalid_components_without_entries_is_rejected():
    with pytest.raises(ComponentsValidationError, match="no recognizable component entries"):
        validate_components_xml("<Components></Components>")


def test_parsed_components_preserve_raw_attributes(fixture_xml_path: Path):
    catalog = parse_components_xml(fixture_xml_path)
    extra = next(
        component
        for component in catalog.components
        if component.id == "90003"
    )
    assert extra.raw_attributes["extraField"] == "keep-me"
    assert extra.raw_attributes["skill"] == "25"


def test_availability_filter_respects_start_year(fixture_xml_path: Path):
    catalog = parse_components_xml(fixture_xml_path)
    skill_levels = {"chassis": 100.0, "engine": 100.0, "gearbox": 100.0, "vehicle": 100.0}

    available_1900 = filter_available_components(catalog, 1900, skill_levels)
    names_1900 = {component.id for component in available_1900}
    assert "90001" in names_1900
    assert "90002" not in names_1900

    available_1910 = filter_available_components(catalog, 1910, skill_levels)
    names_1910 = {component.id for component in available_1910}
    assert "90002" in names_1910


def test_availability_filter_respects_end_year(fixture_xml_path: Path):
    catalog = parse_components_xml(fixture_xml_path)
    skill_levels = {"chassis": 100.0, "engine": 100.0, "gearbox": 100.0, "vehicle": 100.0}

    assert is_component_available(
        next(c for c in catalog.components if c.id == "90001"),
        1920,
        skill_levels,
    )
    assert not is_component_available(
        next(c for c in catalog.components if c.id == "90001"),
        1921,
        skill_levels,
    )


def test_availability_filter_respects_required_skill(fixture_xml_path: Path):
    catalog = parse_components_xml(fixture_xml_path)
    low_skill = {"chassis": 10.0, "engine": 10.0, "gearbox": 10.0, "vehicle": 10.0}
    high_skill = {"chassis": 30.0, "engine": 30.0, "gearbox": 30.0, "vehicle": 30.0}
    frame_1910 = next(c for c in catalog.components if c.id == "90002")

    assert not is_component_available(frame_1910, 1910, low_skill)
    assert is_component_available(frame_1910, 1910, high_skill)


def test_unknown_fields_do_not_crash_parser(fixture_xml_path: Path):
    catalog = parse_components_xml(fixture_xml_path)
    unknown = next(component for component in catalog.components if component.id == "93001")
    assert unknown.raw_attributes["weirdStart"] == "1905"
    assert unknown.start_year is None


def test_cli_import_components_and_tech_availability_registered():
    assert "import-components" in SUBCOMMANDS
    assert "tech-availability" in SUBCOMMANDS


def test_streamlit_helpers_handle_missing_components_gracefully(
    components_dir: Path,
):
    assert handle_missing_components_catalog() is True
    message = tech_availability_empty_state_message()
    assert "Components.xml has not been imported" in message


def test_cost_mode_enum_accepts_cheap_balanced_luxury_only():
    assert parse_cost_mode("cheap") is CostMode.CHEAP
    assert parse_cost_mode("balanced") is CostMode.BALANCED
    assert parse_cost_mode("luxury") is CostMode.LUXURY
    with pytest.raises(ValueError, match="Cost mode must be one of"):
        parse_cost_mode("premium")


def test_year_below_1900_is_rejected():
    with pytest.raises(ValueError, match="1900"):
        validate_year_input(1899)


def test_infer_skill_category_mapping():
    frame = ComponentTech(
        id="1",
        name="Frame",
        category="chassis",
        subcategory="frame",
        start_year=1900,
        end_year=None,
        required_skill=0.0,
        raw_attributes={},
        source_path=None,
    )
    layout = ComponentTech(
        id="2",
        name="Layout",
        category="engine",
        subcategory="layout",
        start_year=1900,
        end_year=None,
        required_skill=0.0,
        raw_attributes={},
        source_path=None,
    )
    gearbox = ComponentTech(
        id="3",
        name="Manual",
        category="gearbox",
        subcategory="transmission",
        start_year=1900,
        end_year=None,
        required_skill=0.0,
        raw_attributes={},
        source_path=None,
    )
    assert infer_skill_category(frame) == "chassis"
    assert infer_skill_category(layout) == "engine"
    assert infer_skill_category(gearbox) == "gearbox"


def test_load_imported_components_catalog(
    fixture_xml_path: Path,
    components_dir: Path,
):
    import_components_from_path(fixture_xml_path)
    catalog = load_imported_components_catalog()
    assert catalog is not None
    assert len(catalog.components) >= 7


def test_cli_tech_availability_missing_components(components_dir: Path):
    with pytest.raises(SystemExit, match="No Components.xml has been imported yet"):
        main(["tech-availability", "--year", "1905"])


def test_cli_tech_availability_with_imported_catalog(
    fixture_xml_path: Path,
    components_dir: Path,
    capsys,
):
    import_components_from_path(fixture_xml_path)
    exit_code = main(
        [
            "tech-availability",
            "--year",
            "1905",
            "--chassis-skill",
            "20",
            "--engine-skill",
            "25",
            "--gearbox-skill",
            "15",
            "--vehicle-skill",
            "10",
            "--category",
            "engine",
        ]
    )
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Tech availability for year 1905" in output
    assert "Available" in output
