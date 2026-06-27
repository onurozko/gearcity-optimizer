"""Shared pytest fixtures for wiki-backed optimizer tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from gearcity_optimizer.core import slider_registry as registry_module
from gearcity_optimizer.core.slider_registry import load_slider_registry
from gearcity_optimizer.importers.wiki_knowledge_builder import (
    FORMULA_EFFECTS_FILENAME,
    SLIDER_REGISTRY_FILENAME,
    build_wiki_knowledge,
)
from gearcity_optimizer.importers.wiki_parser import parse_wiki_page

FIXTURES = Path(__file__).parent / "fixtures" / "wiki"


@pytest.fixture(autouse=True)
def clear_registry_cache() -> None:
    load_slider_registry.cache_clear()
    yield
    load_slider_registry.cache_clear()


@pytest.fixture
def missing_wiki_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the slider registry at paths with no wiki artifacts."""
    missing_dir = tmp_path / "empty"
    missing_dir.mkdir()
    monkeypatch.setattr(
        registry_module,
        "_registry_paths",
        lambda: (
            missing_dir / "wiki_slider_registry.json",
            missing_dir / "wiki_formula_effects.json",
        ),
    )
    load_slider_registry.cache_clear()
    return missing_dir


@pytest.fixture
def wiki_model_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Build and patch a full wiki slider/formula model from test fixtures."""
    parsed_pages = {
        "engine_game_mechanics": parse_wiki_page(
            "engine_game_mechanics",
            (FIXTURES / "engine_sliders_sample.txt").read_text(encoding="utf-8"),
            "raw",
        ),
        "chassis_game_mechanics": parse_wiki_page(
            "chassis_game_mechanics",
            (FIXTURES / "chassis_sliders_sample.txt").read_text(encoding="utf-8"),
            "raw",
        ),
        "gearbox_game_mechanics": parse_wiki_page(
            "gearbox_game_mechanics",
            (FIXTURES / "gearbox_sliders_sample.txt").read_text(encoding="utf-8"),
            "raw",
        ),
        "vehicle_game_mechanics": parse_wiki_page(
            "vehicle_game_mechanics",
            (FIXTURES / "vehicle_sliders_sample.txt").read_text(encoding="utf-8"),
            "raw",
        ),
    }
    build_wiki_knowledge(parsed_pages, output_dir=tmp_path)
    monkeypatch.setattr(
        registry_module,
        "_registry_paths",
        lambda: (
            tmp_path / SLIDER_REGISTRY_FILENAME,
            tmp_path / FORMULA_EFFECTS_FILENAME,
        ),
    )
    load_slider_registry.cache_clear()
    return tmp_path


@pytest.fixture
def sample_save_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "sample.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(
            """
            CREATE TABLE GameInfo (
                GameInfo_Varible VARCHAR(64),
                GameInfo_Data VARCHAR(64)
            );
            INSERT INTO GameInfo VALUES ('Current_Year', '1906');

            CREATE TABLE LayoutComponents (
                Name VARCHAR(64),
                Engine_Length REAL,
                Engine_Width REAL,
                Engine_LayoutPower REAL,
                Engine_LayoutFuel REAL,
                Engine_LayoutSmooth REAL,
                CylinderLengthArrangment INTEGER,
                Weight REAL
            );
            INSERT INTO LayoutComponents VALUES ('W', 0.85, 1.3, 1.0, 0.5, 0.5, 3, 1.5);

            CREATE TABLE EngineInfo (
                Engine_ID INTEGER PRIMARY KEY,
                Company_ID INTEGER,
                Name VARCHAR(64),
                yearbuilt INTEGER,
                Layout VARCHAR(32),
                Cylinders VARCHAR(32),
                Fueltype VARCHAR(32),
                Induction VARCHAR(32),
                Valve VARCHAR(32),
                slider_displace REAL,
                slider_length REAL,
                slider_width REAL,
                slider_weight REAL,
                slider_rpm REAL,
                slider_torq REAL,
                slider_eco REAL,
                slider_materials REAL,
                slider_techniques REAL,
                slider_tech REAL,
                slider_compoenents REAL,
                slider_designperformance REAL,
                slider_designfueleco REAL,
                slider_designdependability REAL,
                hp INTEGER,
                torque INTEGER,
                rpm REAL,
                weight INTEGER,
                size_cc INTEGER,
                length REAL,
                width INTEGER,
                fuelmilage REAL,
                desighnreq INTEGER,
                manureq INTEGER,
                enginePower REAL,
                engineFuelEco REAL,
                engineReliability REAL,
                overallRating INTEGER,
                bore REAL,
                stroke REAL,
                DesignPace REAL,
                CylinderNumberForCalculations INTEGER,
                ModAmount INTEGER,
                ModYear INTEGER,
                StaticenginePower REAL,
                StaticengineFuelEco REAL,
                StaticengineReliability REAL
            );
            INSERT INTO EngineInfo (
                Engine_ID, Company_ID, Name, yearbuilt, Layout, Cylinders, Fueltype,
                Induction, Valve, slider_displace, slider_length, slider_width,
                slider_weight, slider_rpm, slider_torq, slider_eco, slider_materials,
                slider_techniques, slider_tech, slider_compoenents,
                slider_designperformance, slider_designfueleco, slider_designdependability,
                hp, torque, rpm, weight, size_cc, length, width, fuelmilage,
                enginePower, engineFuelEco, engineReliability, overallRating,
                bore, stroke, DesignPace, CylinderNumberForCalculations,
                ModAmount, ModYear, StaticenginePower, StaticengineFuelEco, StaticengineReliability
            ) VALUES (
                707, 0, 'R-204P-343T-G', 1906, 'W', '15', 'Gasoline',
                'Naturally Aspirated', 'DOHC', 0.388, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0,
                1.0, 0.0, 0.0, 223, 291, 3000, 596, 10097, 56, 42, 8.78,
                24.6, 7.3, 14.6, 13.6, 123.0, 56.65, 0.318182, 15,
                2, 1920, 23.0, 6.0, 60.0
            );

            CREATE TABLE GearboxInfo (
                Gearbox_ID INTEGER PRIMARY KEY,
                Company_ID INTEGER,
                Name VARCHAR(64),
                YearBuilt INTEGER,
                Gears INTEGER,
                GearboxType VARCHAR(64),
                Reverse BOOL,
                Overdrive BOOL,
                Limited BOOL,
                Transaxle BOOL,
                LoRatio REAL,
                HiRatio REAL,
                TorqueInputRatio REAL,
                MaxTorqueInput INTEGER,
                ModAmount INTEGER,
                Tech_Material REAL,
                Tech_Parts REAL,
                Tech_Techniques REAL,
                Tech_Tech REAL,
                de_performance REAL,
                de_fuel REAL,
                de_depend REAL,
                de_comfort REAL,
                PowerRating REAL,
                FuelRating REAL,
                PerformanceRating REAL,
                ReliabiltyRating REAL,
                OverallRating REAL,
                Weight INTEGER,
                GB_Weight REAL,
                GB_Complexity REAL,
                GB_Smoothness REAL,
                GB_Comfort REAL,
                GB_Fuel REAL,
                GB_Performance REAL,
                DesignPace REAL
            );
            INSERT INTO GearboxInfo (
                Gearbox_ID, Company_ID, Name, YearBuilt, Gears, GearboxType,
                Reverse, Overdrive, Limited, Transaxle, LoRatio, HiRatio,
                TorqueInputRatio, MaxTorqueInput, ModAmount, Tech_Material, Tech_Parts, Tech_Techniques, Tech_Tech,
                de_performance, de_fuel, de_depend, de_comfort, PowerRating, FuelRating,
                PerformanceRating, ReliabiltyRating, OverallRating, Weight,
                GB_Weight, GB_Complexity, GB_Smoothness, GB_Comfort, GB_Fuel,
                GB_Performance, DesignPace
            ) VALUES (
                289, 0, 'R-341T-NS7', 1906, 7, 'Non-Synchronous',
                1, 0, 0, 0, 0.0, 0.0, 1.0, 312, 2, 0.3, 0.3, 0.3, 0.3,
                0.5, 0.35, 0.4, 0.3, 17.0, 50.0, 50.0, 50.0, 50.0, 179,
                0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.5
            );
            """
        )
        conn.commit()
    finally:
        conn.close()
    return db_path
