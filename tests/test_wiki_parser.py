"""Tests for GearCity Wiki parser."""

from __future__ import annotations

import json
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


def test_build_formula_index_from_vehicle_game_mechanics_page():
    """Formula index builder should include vehicle game mechanics sections."""
    raw = (FIXTURES / "vehicle_game_mechanics_sample.txt").read_text(encoding="utf-8")
    parsed = parse_raw_content(raw)
    parsed["name"] = "vehicle_game_mechanics"
    index = build_formula_index({"vehicle_game_mechanics": parsed})

    assert "vehicle_game_mechanics" in index
    sections = index["vehicle_game_mechanics"]
    assert "Dependability Rating" in sections
    assert "Rating_Dependability" in sections["Dependability Rating"]
    assert "Driveability Rating" in sections or "Drivability Rating" in sections


def test_import_wiki_parses_vehicle_game_mechanics(tmp_path: Path):
    """import-wiki should parse a cached vehicle_game_mechanics raw page."""
    from gearcity_optimizer.importers.wiki_parser import import_wiki_pages

    fixture = (FIXTURES / "vehicle_game_mechanics_sample.txt").read_text(encoding="utf-8")
    raw_dir = tmp_path / "sources" / "wiki_raw"
    raw_dir.mkdir(parents=True)
    (raw_dir / "vehicle_game_mechanics.txt").write_text(fixture, encoding="utf-8")

    urls_file = tmp_path / "sources" / "wiki_urls.json"
    urls_file.parent.mkdir(parents=True, exist_ok=True)
    urls_file.write_text(
        json.dumps(
            [
                {
                    "name": "vehicle_game_mechanics",
                    "url": "https://wiki.gearcity.info/doku.php?id=gamemanual:gm_vehicles_design",
                    "purpose": "Final vehicle formulas",
                }
            ]
        ),
        encoding="utf-8",
    )

    summary = import_wiki_pages(
        urls_file=urls_file,
        raw_dir=raw_dir,
        text_dir=tmp_path / "sources" / "wiki_text",
        html_dir=tmp_path / "sources" / "wiki_html",
        output_dir=tmp_path / "generated" / "raw_parsed",
        normalized_dir=tmp_path / "generated" / "normalized",
        existing_vehicle_types_csv=tmp_path / "data" / "vehicle_types.csv",
    )

    assert summary["missing_sources"] == []
    assert len(summary["parsed"]) == 1
    assert summary["parsed"][0]["name"] == "vehicle_game_mechanics"
    assert "vehicle_game_mechanics" in summary["formula_index_counts"]
    assert summary["formula_index_counts"]["vehicle_game_mechanics"] >= 1

    parsed_json = tmp_path / "generated" / "raw_parsed" / "wiki_vehicle_game_mechanics.json"
    assert parsed_json.is_file()
    data = json.loads(parsed_json.read_text(encoding="utf-8"))
    assert data["name"] == "vehicle_game_mechanics"
    assert "Rating_Dependability" in json.dumps(data["formula_sections"])


def test_wiki_urls_contains_vehicle_game_mechanics():
    """Configured wiki URLs should include vehicle game mechanics."""
    urls_path = Path(__file__).resolve().parent.parent / "sources" / "wiki_urls.json"
    entries = json.loads(urls_path.read_text(encoding="utf-8"))
    names = {entry["name"] for entry in entries}
    assert "vehicle_game_mechanics" in names
    vehicle_entry = next(entry for entry in entries if entry["name"] == "vehicle_game_mechanics")
    assert "gm_vehicles_design" in vehicle_entry["url"]
    assert "dependability" in vehicle_entry["purpose"].lower()


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
