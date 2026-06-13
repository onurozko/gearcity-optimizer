"""Tests for evidence-backed terminology verification."""

from __future__ import annotations

from pathlib import Path

import pytest

from gearcity_optimizer.cli import main
from gearcity_optimizer.core.terminology import (
    clear_terminology_cache,
    get_verified_terminology_entry,
)
from gearcity_optimizer.core.terminology_verification import (
    search_terminology_sources,
    sources_available,
    verify_drivability_handling_mapping,
    verify_engine_power_rating_mapping,
    verify_final_vehicle_dependability_mapping,
    verify_term_search,
)


def _write_sources(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_drivability_handling_confirmed_when_sources_explicit(tmp_path: Path):
    """Explicit equivalence text should not rename the formula stat to Handling."""
    clear_terminology_cache()
    _write_sources(
        tmp_path,
        "sources/wiki_raw/handling.txt",
        "Vehicle Handling is the same as Drivability in the overview screen.",
    )
    entry = verify_drivability_handling_mapping(root=tmp_path)
    assert entry.status == "confirmed"
    assert entry.display_label == "Driveability"
    assert "Handling / Drivability" not in entry.display_label
    assert entry.evidence


def test_drivability_handling_unknown_when_both_terms_without_link(tmp_path: Path):
    """Both terms without a connection should stay unknown."""
    clear_terminology_cache()
    _write_sources(
        tmp_path,
        "sources/wiki_raw/mixed.txt",
        "Rating_Drivability is used in formulas. Handling appears in UI tables.",
    )
    entry = verify_drivability_handling_mapping(root=tmp_path)
    assert entry.status == "unknown"
    assert entry.display_label == "Driveability"


def test_drivability_handling_conflicting_when_sources_say_separate(tmp_path: Path):
    """Separate-stat wording should mark mapping as conflicting."""
    clear_terminology_cache()
    _write_sources(
        tmp_path,
        "sources/wiki_raw/separate.txt",
        "Handling and Drivability are separate stats on the overview screen.",
    )
    entry = verify_drivability_handling_mapping(root=tmp_path)
    assert entry.status == "conflicting"
    assert entry.display_label == "Driveability"
    assert "separate" in entry.explanation.lower()


def test_missing_sources_do_not_crash(tmp_path: Path):
    """Missing wiki files should return unknown status without raising."""
    clear_terminology_cache()
    assert not sources_available(tmp_path)
    entry = get_verified_terminology_entry("vehicle", "drivability", root=tmp_path)
    assert entry.status == "unknown"
    assert search_terminology_sources(["Handling"], root=tmp_path) == []


def test_terminology_audit_cli_runs(capsys):
    """terminology-audit CLI should exit cleanly."""
    exit_code = main(["terminology-audit", "--all"])
    assert exit_code == 0
    captured = capsys.readouterr().out
    assert "Terminology audit" in captured


def test_terminology_audit_cli_term_search(tmp_path: Path, capsys):
    """terminology-audit --term should print search results."""
    clear_terminology_cache()
    _write_sources(tmp_path, "sources/wiki_raw/test.txt", "Handling rating formula.")
    exit_code = main(["terminology-audit", "--term", "Handling"])
    assert exit_code == 0


def test_streamlit_helpers_import_cleanly():
    """Streamlit UI helpers should import when streamlit is available."""
    pytest.importorskip("streamlit")
    from gearcity_optimizer.ui import streamlit_helpers  # noqa: F401

    assert callable(streamlit_helpers.render_app)


def test_missing_sources_message_mentions_setup_commands(tmp_path: Path):
    """Missing terminology sources should print setup/download guidance."""
    clear_terminology_cache()
    _, note = verify_term_search("Handling", root=tmp_path)
    assert "Terminology sources are missing" in note
    assert "setup-sources" in note
    assert "download-wiki" in note
    assert "import-wiki" in note


def test_drivability_unknown_with_vehicle_formula_and_steering(tmp_path: Path):
    """Vehicle Rating_Drivability with steering inputs should stay unknown."""
    clear_terminology_cache()
    _write_sources(
        tmp_path,
        "sources/wiki_raw/vehicle.txt",
        (
            "Rating_Drivability uses SubComponent_FrSus_Steering. "
            "Handling appears in UI tables."
        ),
    )
    entry = verify_drivability_handling_mapping(root=tmp_path)
    assert entry.status == "unknown"
    assert entry.display_label == "Driveability"
    assert "Rating_Drivability" in entry.explanation or "Driveability" in entry.explanation
    assert "steering" in entry.explanation.lower() or "handling" in entry.explanation.lower()


def test_final_dependability_distinct_from_component_reliability(tmp_path: Path):
    """Final vehicle dependability should not collapse component reliability layers."""
    clear_terminology_cache()
    _write_sources(
        tmp_path,
        "sources/wiki_raw/vehicle.txt",
        (
            "Rating_Dependability = Selected_Chassis.Durability_Rating * 0.35\n"
            "Rating_Dependability = Rating_Dependability + "
            "Selected_Engine.Reliability_Rating * 0.35"
        ),
    )
    entry = verify_final_vehicle_dependability_mapping(root=tmp_path)
    assert entry.status == "confirmed"
    assert entry.display_label == "Dependability"
    assert "component-level" in entry.explanation.lower() or "component" in entry.explanation.lower()
    assert "not identical" in entry.explanation.lower()


def test_engine_power_rating_separate_from_horsepower_and_torque(tmp_path: Path):
    """Engine Power Rating should be described separately from horsepower and torque."""
    clear_terminology_cache()
    _write_sources(
        tmp_path,
        "sources/wiki_raw/engine.txt",
        (
            "Horsepower is calculated from Torque and RPM.\n"
            "Power_Rating = 100 * (Selected_Engine.HP / max_hp)"
        ),
    )
    entry = verify_engine_power_rating_mapping(root=tmp_path)
    assert entry.status == "confirmed"
    assert entry.display_label == "Engine Power Rating"
    assert "Horsepower" in entry.explanation
    assert "torque" in entry.explanation.lower()
    assert "separate" in entry.explanation.lower()
