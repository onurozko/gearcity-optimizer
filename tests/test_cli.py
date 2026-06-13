"""Tests for CLI dispatch and formula browser integration."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from gearcity_optimizer.cli import SUBCOMMANDS, _resolve_subcommand, main
from gearcity_optimizer.formula_browser import (
    FormulaIndexError,
    export_formula_markdown,
    list_formula_pages,
    list_formula_sections,
    load_formula_index,
    search_formulas,
)
from gearcity_optimizer.importers.wiki_parser import is_wiki_page_json


@pytest.fixture
def fake_formula_index(tmp_path: Path) -> Path:
    """Create a small fake formula index JSON file."""
    index = {
        "gearbox_game_mechanics": {
            "Maximum Torque Support": "Max_Torque_Support = 10 * Number_Of_Gears",
            "Weight": "Weight = 20 + 15*(Number_Of_Gears+Has_Reverse)",
        },
        "dynamic_reports": {
            "Buyer Rating": "Current Buyer Rating = Vehicle Type Rating",
        },
    }
    path = tmp_path / "wiki_formula_index.json"
    path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return path


def test_formulas_is_a_known_subcommand():
    """The formulas command should be registered as a subcommand."""
    assert "formulas" in SUBCOMMANDS
    assert "setup-sources" in SUBCOMMANDS
    assert "design-checklist" in SUBCOMMANDS
    assert "calc-gearboxes" in SUBCOMMANDS
    assert "calc-chassis" in SUBCOMMANDS
    assert "calc-engines" in SUBCOMMANDS


def test_resolve_subcommand_recognizes_formulas():
    """CLI dispatch should route formulas to its subcommand parser."""
    command, remaining = _resolve_subcommand(
        ["formulas", "--page", "gearbox_game_mechanics", "--list-sections"]
    )
    assert command == "formulas"
    assert remaining == ["--page", "gearbox_game_mechanics", "--list-sections"]


def test_resolve_subcommand_legacy_rank_designs():
    """Legacy invocation without subcommand should route to rank-designs."""
    command, remaining = _resolve_subcommand(
        ["--vehicle-type", "Sedan", "--year", "1901", "--objective", "balanced"]
    )
    assert command is None
    assert remaining[0] == "--vehicle-type"


def test_unknown_subcommand_returns_error(capsys):
    """Unknown subcommands should not be routed to rank-designs."""
    exit_code = main(["not-a-real-command"])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Unknown command" in captured.out


def test_formulas_list_pages_with_fake_index(fake_formula_index: Path, capsys):
    """formulas --list-pages should print pages from the formula index."""
    exit_code = main(
        ["formulas", "--list-pages", "--formula-index", str(fake_formula_index)]
    )
    assert exit_code == 0
    captured = capsys.readouterr().out
    assert "gearbox_game_mechanics" in captured
    assert "dynamic_reports" in captured


def test_formulas_list_sections_with_fake_index(fake_formula_index: Path, capsys):
    """formulas --page ... --list-sections should list section names."""
    exit_code = main(
        [
            "formulas",
            "--page",
            "gearbox_game_mechanics",
            "--list-sections",
            "--formula-index",
            str(fake_formula_index),
        ]
    )
    assert exit_code == 0
    captured = capsys.readouterr().out
    assert "Maximum Torque Support" in captured
    assert "Weight" in captured


def test_formula_browser_search(fake_formula_index: Path):
    """search_formulas should find torque-related sections."""
    index = load_formula_index(fake_formula_index)
    results = search_formulas(index, "torque", page_name="gearbox_game_mechanics")
    assert len(results) >= 1
    assert results[0]["section"] == "Maximum Torque Support"


def test_is_wiki_page_json_excludes_metadata():
    """inspect-sources page counting should ignore metadata JSON files."""
    assert is_wiki_page_json(Path("wiki_formula_index.json")) is False
    assert is_wiki_page_json(Path("wiki_gearbox_game_mechanics.json")) is True


def test_export_formula_markdown(fake_formula_index: Path, tmp_path: Path):
    """export_formula_markdown should write a markdown file."""
    index = load_formula_index(fake_formula_index)
    out = export_formula_markdown(index, tmp_path / "wiki_formula_index.md")
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "# GearCity Wiki Formula Index" in content
    assert "Maximum Torque Support" in content


def test_load_formula_index_missing_raises():
    """Missing formula index should raise a helpful error."""
    with pytest.raises(FormulaIndexError, match="fresh clone"):
        load_formula_index("/nonexistent/wiki_formula_index.json")


def test_formulas_missing_index_prints_helpful_message(capsys, tmp_path: Path):
    """formulas should explain fresh-clone setup when the index is missing."""
    missing_index = tmp_path / "missing_formula_index.json"
    exit_code = main(
        ["formulas", "--list-pages", "--formula-index", str(missing_index)]
    )
    assert exit_code == 1
    captured = capsys.readouterr().out
    assert "fresh clone" in captured
    assert "download-wiki" in captured
    assert "import-wiki" in captured


def test_inspect_sources_prints_changed_values(capsys, tmp_path: Path):
    """inspect-sources should print readable changed vehicle type values."""
    raw_parsed = tmp_path / "generated" / "raw_parsed"
    normalized = tmp_path / "generated" / "normalized"
    raw_parsed.mkdir(parents=True)
    normalized.mkdir(parents=True)

    comparison = {
        "match": False,
        "missing_vehicle_types": [],
        "extra_vehicle_types": [],
        "changed_values": [
            {
                "vehicle_type": "Town Car",
                "column": "civilian_fleet",
                "existing": True,
                "generated": False,
            }
        ],
        "missing_count": 0,
        "extra_count": 0,
        "changed_count": 1,
    }
    (raw_parsed / "vehicle_type_table_comparison.json").write_text(
        json.dumps(comparison), encoding="utf-8"
    )
    (raw_parsed / "wiki_download_manifest.json").write_text(
        '{"pages": []}', encoding="utf-8"
    )
    (raw_parsed / "wiki_formula_index.json").write_text(
        '{"gearbox_game_mechanics": {"A": "x=1"}}', encoding="utf-8"
    )
    (raw_parsed / "wiki_gearbox_game_mechanics.json").write_text("{}", encoding="utf-8")
    (normalized / "vehicle_types_from_wiki.csv").write_text(
        "vehicle_type,performance,drivability,luxury,safety,fuel,power,cargo,"
        "dependability,wealth_demo,military_fleet,civilian_fleet\n"
        "Town Car,0.15,0.15,0.8,0.5,0.15,0.4,0.6,0.4,5,False,False\n",
        encoding="utf-8",
    )

    with patch(
        "gearcity_optimizer.cli.main.project_root_from_module",
        return_value=tmp_path,
    ):
        exit_code = main(
            [
                "inspect-sources",
                "--vehicle-types-file",
                str(tmp_path / "vehicle_types.csv"),
            ]
        )

    assert exit_code == 0
    captured = capsys.readouterr().out
    assert "Changed vehicle type values:" in captured
    assert "Town Car / civilian_fleet: data=True, wiki=False" in captured
    assert "Parsed pages: 1" in captured
