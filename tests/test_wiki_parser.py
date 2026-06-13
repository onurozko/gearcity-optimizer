"""Tests for GearCity Wiki parser."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from gearcity_optimizer.importers.wiki_parser import (
    build_formula_index,
    compare_vehicle_type_tables,
    extract_dokuwiki_sections,
    extract_formula_chunks,
    extract_formula_sections_from_raw,
    extract_vehicle_type_importance,
    is_wiki_page_json,
    parse_dokuwiki_tables,
    parse_html_content,
    parse_raw_content,
    parse_wiki_page,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "wiki"


def test_parse_dokuwiki_tables_parses_header_and_rows():
    """DokuWiki table parser should read ^ headers and | data rows."""
    text = (FIXTURES / "dokuwiki_mini_table.txt").read_text(encoding="utf-8")
    tables = parse_dokuwiki_tables(text)

    assert len(tables) == 1
    assert tables[0]["headers"] == ["Vehicle Type", "Performance", "Drivability"]
    assert tables[0]["rows"] == [["Sedan", "0.4", "0.4"], ["Phaeton", "0.1", "0.3"]]
    assert tables[0]["source"] == "dokuwiki_raw"


def test_parse_html_extracts_title_headings_and_tables():
    """Parser should extract title, headings, and tables from HTML."""
    html = (FIXTURES / "sample_chassis.html").read_text(encoding="utf-8")
    parsed = parse_html_content(html, "html")

    assert parsed["title"] == "Chassis Game Mechanics"
    assert any(h["text"] == "Comfort Rating" for h in parsed["headings"])
    assert len(parsed["tables"]) == 1
    assert parsed["tables"][0][0]["variable"] == "Slider_Comfort"


def test_extract_formula_chunks_from_text():
    """Formula extractor should capture pseudo-code lines."""
    text = (FIXTURES / "formula_snippet.txt").read_text(encoding="utf-8")
    chunks = extract_formula_chunks(text)

    assert any("Comfort_Rating =" in chunk for chunk in chunks)
    assert any("if Selected_Chassis_Comfort" in chunk for chunk in chunks)
    assert any("Buyer Rating" in chunk for chunk in chunks)
    assert any("Quality to Price" in chunk for chunk in chunks)


def test_parse_raw_content_extracts_headings_and_formulas():
    """Raw wiki export text should parse headings and formula chunks."""
    raw = (FIXTURES / "formula_snippet.txt").read_text(encoding="utf-8")
    parsed = parse_raw_content(raw)

    assert any(h["text"] == "Comfort Rating" for h in parsed["headings"])
    assert len(parsed["formula_chunks"]) >= 3


def test_extract_dokuwiki_sections_parses_headings():
    """DokuWiki section extractor should parse nested headings."""
    raw = (FIXTURES / "gearbox_raw_sample.txt").read_text(encoding="utf-8")
    sections = extract_dokuwiki_sections(raw)
    titles = [section["title"] for section in sections]

    assert "Gearbox Game Mechanics" in titles
    assert "Maximum Torque Support" in titles
    assert "Power Rating" in titles


def test_extract_formula_sections_from_raw_creates_named_sections():
    """Formula section extractor should group code by heading title."""
    raw = (FIXTURES / "gearbox_raw_sample.txt").read_text(encoding="utf-8")
    sections = extract_formula_sections_from_raw(raw)

    assert "Maximum Torque Support" in sections
    assert "Max_Torque_Support" in sections["Maximum Torque Support"]
    assert "Power Rating" in sections


def test_extract_vehicle_type_importance_from_dokuwiki_table():
    """Vehicle type extractor should parse DokuWiki raw tables."""
    raw = (FIXTURES / "vehicle_type_dokuwiki.txt").read_text(encoding="utf-8")
    parsed = parse_raw_content(raw)
    rows = extract_vehicle_type_importance(parsed)

    assert len(rows) == 2
    sedan = next(row for row in rows if row["vehicle_type"] == "Sedan")
    assert sedan["fuel"] == 0.65
    assert sedan["military_fleet"] is False
    assert sedan["civilian_fleet"] is True
    pickup = next(row for row in rows if row["vehicle_type"] == "Pickup Truck")
    assert pickup["power"] == 0.9


def test_extract_vehicle_type_importance_from_html_table():
    """Vehicle type extractor should still parse HTML tables."""
    html = (FIXTURES / "vehicle_type_importance.html").read_text(encoding="utf-8")
    parsed = parse_wiki_page("vehicle_type_importance", html, "html")
    rows = extract_vehicle_type_importance(parsed)

    assert len(rows) == 2
    sedan = next(row for row in rows if row["vehicle_type"] == "Sedan")
    assert sedan["fuel"] == 0.65


def test_build_formula_index_from_gearbox_raw_page():
    """Formula index builder should produce sections for gearbox raw page."""
    raw = (FIXTURES / "gearbox_raw_sample.txt").read_text(encoding="utf-8")
    parsed = parse_raw_content(raw)
    parsed["name"] = "gearbox_game_mechanics"
    index = build_formula_index({"gearbox_game_mechanics": parsed})

    assert len(index["gearbox_game_mechanics"]) >= 1
    assert "Maximum Torque Support" in index["gearbox_game_mechanics"]


def test_is_wiki_page_json_excludes_metadata_files():
    """Metadata JSON files should not count as parsed wiki pages."""
    assert is_wiki_page_json(Path("wiki_chassis_game_mechanics.json")) is True
    assert is_wiki_page_json(Path("wiki_formula_index.json")) is False
    assert is_wiki_page_json(Path("wiki_download_manifest.json")) is False
    assert is_wiki_page_json(Path("vehicle_type_table_comparison.json")) is False


def test_compare_vehicle_type_tables_detects_match(tmp_path: Path):
    """Comparison should report no differences for identical tables."""
    existing = tmp_path / "existing.csv"
    generated = tmp_path / "generated.csv"
    df = pd.DataFrame(
        [
            {
                "vehicle_type": "Sedan",
                "performance": 0.4,
                "drivability": 0.4,
                "luxury": 0.45,
                "safety": 0.65,
                "fuel": 0.65,
                "power": 0.45,
                "cargo": 0.5,
                "dependability": 0.45,
                "wealth_demo": 4,
                "military_fleet": False,
                "civilian_fleet": True,
            }
        ]
    )
    df.to_csv(existing, index=False)
    df.to_csv(generated, index=False)

    result = compare_vehicle_type_tables(existing, generated)
    assert result["match"] is True
    assert result["missing_vehicle_types"] == []
    assert result["changed_values"] == []


def test_compare_vehicle_type_tables_detects_changes(tmp_path: Path):
    """Comparison should detect changed values between tables."""
    existing = tmp_path / "existing.csv"
    generated = tmp_path / "generated.csv"

    base = {
        "vehicle_type": "Sedan",
        "performance": 0.4,
        "drivability": 0.4,
        "luxury": 0.45,
        "safety": 0.65,
        "fuel": 0.65,
        "power": 0.45,
        "cargo": 0.5,
        "dependability": 0.45,
        "wealth_demo": 4,
        "military_fleet": False,
        "civilian_fleet": True,
    }
    changed = dict(base)
    changed["fuel"] = 0.70

    pd.DataFrame([base]).to_csv(existing, index=False)
    pd.DataFrame([changed]).to_csv(generated, index=False)

    result = compare_vehicle_type_tables(existing, generated)
    assert result["match"] is False
    assert len(result["changed_values"]) == 1
    assert result["changed_values"][0]["column"] == "fuel"
