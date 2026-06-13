"""Tests for design checklist generation and CLI."""

from __future__ import annotations

from pathlib import Path

import pytest

from gearcity_optimizer.cli import main
from gearcity_optimizer.reports.design_checklist import (
    build_design_checklist,
    render_design_checklist_markdown,
)
from gearcity_optimizer.core.vehicle_types import load_vehicle_types


def _vehicle_types_path() -> str:
    return str(Path(__file__).resolve().parent.parent / "data" / "vehicle_types.csv")


def _load_type(name: str):
    return load_vehicle_types(_vehicle_types_path())[name]


def _report_text(name: str) -> str:
    report = build_design_checklist(_load_type(name))
    return "\n".join(
        [
            render_design_checklist_markdown(report),
            report.markdown,
            *(" ".join(section.bullets) for section in report.sections),
            " ".join(report.warnings),
        ]
    ).lower()


def test_build_design_checklist_returns_report_for_sedan():
    """Sedan should produce a complete checklist report."""
    report = build_design_checklist(_load_type("Sedan"), year=1901)

    assert report.vehicle_type == "Sedan"
    assert report.year == 1901
    assert len(report.final_stat_priorities) >= 5
    assert len(report.sections) == 4
    assert report.warnings
    assert report.markdown
    assert "Sedan Design Checklist" in report.markdown


def test_sedan_checklist_mentions_fuel_economy_and_safety():
    """Sedan checklist should emphasize fuel economy and safety."""
    text = _report_text("Sedan")
    assert "fuel economy" in text
    assert "safety" in text


def test_pickup_truck_checklist_mentions_cargo_power_torque_gearbox():
    """Pickup Truck checklist should call out utility and torque support."""
    text = _report_text("Pickup Truck")
    assert "cargo" in text
    assert "power" in text or "torque" in text
    assert "max torque" in text


def test_roadster_checklist_mentions_performance_drivability_horsepower():
    """Roadster checklist should emphasize performance and drivability."""
    text = _report_text("Roadster")
    assert "performance" in text
    assert "driveability" in text
    assert "horsepower" in text


def test_luxury_sedan_checklist_mentions_luxury_smoothness_comfort():
    """Luxury Sedan checklist should emphasize luxury-oriented stats."""
    text = _report_text("Luxury Sedan")
    assert "luxury" in text
    assert "smoothness" in text
    assert "comfort" in text


def test_markdown_renderer_includes_major_sections():
    """Markdown output should include all major checklist sections."""
    report = build_design_checklist(_load_type("Sedan"))
    markdown = render_design_checklist_markdown(report)

    assert "## Final vehicle rating priorities" in markdown
    assert "Driveability" in markdown
    assert "Handling / Drivability" not in markdown
    assert "## Chassis focus" in markdown
    assert "## Engine focus" in markdown
    assert "## Gearbox focus" in markdown
    assert "## Design sliders & testing focus" in markdown
    assert "## Things to avoid" in markdown
    assert "Selected vehicle type:" in markdown


def test_sedan_checklist_final_ratings_and_slider_labels():
    """Sedan checklist should separate final ratings from design slider guidance."""
    report = build_design_checklist(_load_type("Sedan"))
    markdown = render_design_checklist_markdown(report)

    assert "Final vehicle rating priorities" in markdown
    assert "Design sliders & testing focus" in markdown
    assert "Design Focus:" in markdown or "Testing:" in markdown
    assert "universal buyer-rating factor" in markdown.lower()


def test_sedan_slider_labels_use_prefixes():
    """Design slider priority labels should include Design Focus or Testing prefixes."""
    from gearcity_optimizer.core.component_priorities import format_stat_label

    assert format_stat_label("vehicle_design", "safety_focus") == "Design Focus: Safety"
    assert format_stat_label("vehicle_design", "testing_fuel") == "Testing: Fuel Economy"
    assert format_stat_label("vehicle_design", "material_quality") == (
        "Materials: Material Quality"
    )


def test_cli_design_checklist_runs_without_crashing(capsys):
    """CLI design-checklist command should exit cleanly."""
    exit_code = main(
        [
            "design-checklist",
            "--vehicle-type",
            "Sedan",
            "--year",
            "1901",
            "--vehicle-types-file",
            _vehicle_types_path(),
        ]
    )
    assert exit_code == 0
    captured = capsys.readouterr().out
    assert "Sedan Design Checklist" in captured
    assert "Fuel economy" in captured or "fuel economy" in captured.lower()


def test_cli_writes_markdown_output_file(tmp_path: Path):
    """CLI should write markdown when --output-markdown is provided."""
    output_path = tmp_path / "sedan_checklist.md"
    exit_code = main(
        [
            "design-checklist",
            "--vehicle-type",
            "Sedan",
            "--year",
            "1901",
            "--vehicle-types-file",
            _vehicle_types_path(),
            "--output-markdown",
            str(output_path),
        ]
    )
    assert exit_code == 0
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "Sedan Design Checklist" in content
    assert "## Chassis focus" in content


def test_streamlit_app_imports_without_crashing():
    """Streamlit UI helpers should import when streamlit is available."""
    pytest.importorskip("streamlit")
    from gearcity_optimizer.ui.streamlit_helpers import render_app  # noqa: F401


def test_wiki_sources_missing_detects_fresh_clone_state():
    """Wiki helper should detect missing cache and generated parser outputs."""
    from gearcity_optimizer.formula_browser import (
        wiki_sources_missing,
        wiki_sources_missing_message,
    )

    assert wiki_sources_missing(
        {
            "formula_index_exists": False,
            "wiki_html_count": 0,
            "wiki_raw_count": 0,
        }
    )
    message = wiki_sources_missing_message()
    assert "fresh clone" in message
    assert "download-wiki" in message
    assert "import-wiki" in message
