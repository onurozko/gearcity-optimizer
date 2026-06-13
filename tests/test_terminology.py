"""Tests for component priority terminology mapping."""

from __future__ import annotations

from pathlib import Path

import pytest

from gearcity_optimizer.core.terminology import (
    DEPENDABILITY_LAYERS_MARKDOWN,
    DRIVEABILITY_HANDLING_NOTE,
    clear_terminology_cache,
    format_final_vehicle_rating_label,
    format_priority_label,
    get_terminology_entry,
    list_terminology_entries,
    list_terminology_layers,
)
from gearcity_optimizer.core.component_priorities import (
    calculate_component_priorities,
    enrich_engine_priorities_for_display,
    format_stat_label,
)
from gearcity_optimizer.core.vehicle_types import load_vehicle_types
from gearcity_optimizer.reports.design_checklist import build_design_checklist


def _vehicle_types_path() -> str:
    return str(Path(__file__).resolve().parent.parent / "data" / "vehicle_types.csv")


def _write_sources(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_chassis_durability_is_not_confirmed_without_evidence(tmp_path: Path):
    """Chassis durability should stay unknown without explicit equivalence evidence."""
    clear_terminology_cache()
    _write_sources(
        tmp_path,
        "sources/wiki_raw/chassis.txt",
        "Durability_Rating is calculated from chassis sliders.",
    )
    entry = get_terminology_entry("chassis", "durability", root=tmp_path)
    assert entry.status in {"unknown", "conflicting"}
    assert entry.status != "confirmed"
    assert "Durability Rating" in entry.display_label


def test_gearbox_comfort_unknown_without_equivalence_proof(tmp_path: Path):
    """Gearbox comfort should not claim confirmed Smoothness mapping without proof."""
    clear_terminology_cache()
    _write_sources(
        tmp_path,
        "sources/wiki_raw/gearbox.txt",
        "Comfort_Rating uses shifting ease variables. Smoothness appears elsewhere.",
    )
    entry = get_terminology_entry("gearbox", "comfort", root=tmp_path)
    assert entry.status != "confirmed"
    assert entry.display_label == "Gearbox Comfort Rating"
    assert "ease" in entry.explanation.lower()
    assert "smoothness" in entry.explanation.lower()


def test_engine_terminology_includes_power_rating(tmp_path: Path):
    """Engine terminology should distinguish Power Rating from horsepower/torque."""
    clear_terminology_cache()
    _write_sources(
        tmp_path,
        "sources/wiki_raw/engine.txt",
        "Horsepower from Torque. Power_Rating = formula output.",
    )
    entry = get_terminology_entry("engine", "power_rating", root=tmp_path)
    assert entry.formula_label == "Power Rating"
    assert entry.display_label == "Engine Power Rating"
    assert entry.observed_game_label == "Power"
    assert "Horsepower" in entry.explanation or "Torque" in entry.explanation

    sedan = load_vehicle_types(_vehicle_types_path())["Sedan"]
    priorities = calculate_component_priorities(sedan)["engine"]
    enriched = enrich_engine_priorities_for_display(priorities)
    stats = [item.stat for item in enriched]
    assert "power_rating" in stats
    assert "Engine Power Rating" in format_stat_label("engine", "power_rating")


def test_terminology_includes_separate_dependability_layers():
    """Terminology should distinguish component stats from final vehicle stats."""
    clear_terminology_cache()
    engine_rel = get_terminology_entry("engine", "reliability")
    chassis_dur = get_terminology_entry("chassis", "durability")
    gearbox_rel = get_terminology_entry("gearbox", "reliability")
    final_dep = get_terminology_entry("vehicle", "dependability")
    overall = get_terminology_entry("vehicle", "overall")
    drivability = get_terminology_entry("vehicle", "drivability")

    assert engine_rel.display_label == "Engine Reliability Rating"
    assert "Durability" in chassis_dur.display_label
    assert gearbox_rel.display_label == "Gearbox Reliability Rating"
    assert final_dep.display_label == "Dependability"
    assert drivability.display_label == "Driveability"
    assert overall.display_label == "Overall Rating"

    layer_names = {layer.name for layer in list_terminology_layers()}
    assert "Engine Reliability Rating" in layer_names
    assert "Vehicle Dependability Rating" in layer_names
    assert "Overall Rating" in layer_names

    keys = {(e.component, e.internal_key) for e in list_terminology_entries()}
    assert ("vehicle_type", "dependability") in keys


def test_drivability_display_uses_driveability_label(tmp_path: Path):
    """Final vehicle drivability label should always be Driveability."""
    clear_terminology_cache()
    _write_sources(
        tmp_path,
        "sources/wiki_raw/confirm.txt",
        "Handling is the same as Drivability for vehicle type importance.",
    )
    entry = get_terminology_entry("vehicle", "drivability", root=tmp_path)
    assert entry.display_label == "Driveability"
    assert format_final_vehicle_rating_label("drivability", root=tmp_path) == "Driveability"
    assert format_priority_label("vehicle", "drivability", root=tmp_path) == "Driveability"
    assert "Handling / Driveability" not in entry.display_label


def test_dependability_heavy_checklist_mentions_layer_distinction():
    """Dependability-heavy types should explain component vs final vehicle layers."""
    pickup = load_vehicle_types(_vehicle_types_path())["Pickup Truck"]
    report = build_design_checklist(pickup, year=1901)
    text = report.markdown.lower()

    assert "final vehicle dependability matters" in text
    assert "component-level stat" in text
    assert "engine reliability" in text
    assert "gearbox reliability" in text


def test_design_checklist_still_builds():
    """Design checklist generation should still work after terminology changes."""
    sedan = load_vehicle_types(_vehicle_types_path())["Sedan"]
    report = build_design_checklist(sedan, year=1901)
    assert report.vehicle_type == "Sedan"
    assert report.sections
    assert "component-level stat" in report.markdown.lower()


def test_list_terminology_entries_covers_components():
    """Terminology audit list should include chassis, engine, and gearbox."""
    clear_terminology_cache()
    components = {entry.component for entry in list_terminology_entries()}
    assert {"chassis", "engine", "gearbox", "vehicle_design", "vehicle"}.issubset(
        components
    )


def test_final_vehicle_rating_labels_are_canonical():
    """Final vehicle priority labels should use wiki-backed canonical names."""
    assert format_final_vehicle_rating_label("drivability") == "Driveability"
    assert format_final_vehicle_rating_label("fuel") == "Fuel economy"
    assert format_final_vehicle_rating_label("dependability") == "Dependability"


def test_terminology_notes_mention_driveability_handling():
    """Terminology notes should explain Driveability vs UI Handling."""
    assert "Driveability" in DRIVEABILITY_HANDLING_NOTE
    assert "Rating_Drivability" in DRIVEABILITY_HANDLING_NOTE
    assert "Handling" in DRIVEABILITY_HANDLING_NOTE
    assert "steering" in DRIVEABILITY_HANDLING_NOTE.lower()


def test_dependability_layers_markdown_is_plain_language():
    """Layer explanation markdown should describe the rating stack."""
    assert "Engine Reliability Rating" in DEPENDABILITY_LAYERS_MARKDOWN
    assert "Vehicle Dependability Rating" in DEPENDABILITY_LAYERS_MARKDOWN
    assert "Overall Rating" in DEPENDABILITY_LAYERS_MARKDOWN
    assert "not the same stat" in DEPENDABILITY_LAYERS_MARKDOWN.lower()
