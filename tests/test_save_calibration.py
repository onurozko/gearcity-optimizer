"""Tests for GearCity save game calibration against wiki formulas."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from gearcity_optimizer.importers.save_db import load_save_game
from gearcity_optimizer.reports.save_calibration import (
    calibrate_engine_record,
    calibrate_save_game,
)


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
                CylinderLengthArrangment INTEGER
            );
            INSERT INTO LayoutComponents VALUES ('W', 0.85, 1.3, 1.0, 0.5, 0.5, 3);

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
                CylinderNumberForCalculations INTEGER
            );
            INSERT INTO EngineInfo (
                Engine_ID, Company_ID, Name, yearbuilt, Layout, Cylinders, Fueltype,
                Induction, Valve, slider_displace, slider_length, slider_width,
                slider_weight, slider_rpm, slider_torq, slider_eco, slider_materials,
                slider_techniques, slider_tech, slider_compoenents,
                slider_designperformance, slider_designfueleco, slider_designdependability,
                hp, torque, rpm, weight, size_cc, length, width, fuelmilage,
                enginePower, engineFuelEco, engineReliability, overallRating,
                bore, stroke, DesignPace, CylinderNumberForCalculations
            ) VALUES (
                707, 0, 'R-204P-343T-G', 1906, 'W', '15', 'Gasoline',
                'Naturally Aspirated', 'DOHC', 0.388, 0.0, 0.0, 0.3, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0,
                1.0, 0.0, 0.0, 223, 291, 3000, 500, 10097, 56, 42, 8.78,
                24.6, 7.3, 50, 26, 123.0, 56.65, 0.318182, 15
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
                Tech_Material REAL,
                Tech_Parts REAL,
                Tech_Techniques REAL,
                Tech_Tech REAL,
                de_performance REAL,
                de_fuel REAL,
                de_depend REAL,
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
                MaxTorqueInput, Tech_Material, Tech_Parts, Tech_Techniques, Tech_Tech,
                de_performance, de_fuel, de_depend, PowerRating, FuelRating,
                PerformanceRating, ReliabiltyRating, OverallRating, Weight,
                GB_Weight, GB_Complexity, GB_Smoothness, GB_Comfort, GB_Fuel,
                GB_Performance, DesignPace
            ) VALUES (
                289, 0, 'R-341T-NS7', 1906, 7, 'Non-Synchronous',
                1, 0, 0, 0, 0.0, 0.0, 312, 0.3, 0.3, 0.3, 0.3,
                0.5, 0.35, 0.4, 17.0, 50.0, 50.0, 50.0, 50.0, 179,
                0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.5
            );
            """
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_load_save_game_reads_layout_and_engine(sample_save_db: Path):
    snapshot = load_save_game(sample_save_db, company_id=0)
    assert snapshot.current_year == 1906
    assert "W" in snapshot.layouts
    assert snapshot.layouts["W"].engine_length == pytest.approx(0.85)
    assert len(snapshot.engines) == 1
    assert snapshot.engines[0].engine_id == 707


def test_calibrate_engine_produces_metric_deltas(sample_save_db: Path):
    snapshot = load_save_game(sample_save_db, company_id=0)
    engine = snapshot.engines[0]
    result = calibrate_engine_record(engine, snapshot.layouts.get(engine.layout))
    metrics = {item.metric: item for item in result.deltas}
    assert "length_in" in metrics
    assert "torque_lbft" in metrics
    assert metrics["length_in"].game_value == pytest.approx(56.0)
    assert metrics["torque_lbft"].abs_error < 20.0
    assert metrics["horsepower"].predicted_value > 40.0


def test_calibrate_save_game_report(sample_save_db: Path):
    report = calibrate_save_game(str(sample_save_db), company_id=0, engine_limit=5, gearbox_limit=5)
    assert len(report.engines) == 1
    assert len(report.gearboxes) == 1
    assert "length_in_mean_abs_error" in report.engine_summary
