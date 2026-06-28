"""Tests for all-company save calibration and skipped bad designs."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from gearcity_optimizer.reports.save_calibration import calibrate_save_game
from gearcity_optimizer.reports.save_calibration_dataset import build_save_dataset_pipeline


def _insert_bad_ai_engine(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
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
                9999, 99, 'Bad AI Engine', 1906, 'W', '15', 'Gasoline',
                'Naturally Aspirated', 'DOHC', 0.388, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.101, 1.0, 1.0, 1.0,
                1.0, 0.0, 0.0, 223, 291, 3000, 596, 10097, 56, 42, 8.78,
                24.6, 7.3, 14.6, 13.6, 123.0, 56.65, 0.318182, 15,
                0, 1906, 23.0, 6.0, 60.0
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def test_calibrate_save_game_default_includes_all_companies(
    sample_save_db: Path,
    tmp_path: Path,
):
    db_path = tmp_path / "mixed.db"
    shutil.copy(sample_save_db, db_path)
    _insert_bad_ai_engine(db_path)

    player_only = calibrate_save_game(
        str(db_path),
        company_id=0,
        engine_limit=None,
        gearbox_limit=None,
        apply_corrections=False,
    )
    all_companies = calibrate_save_game(
        str(db_path),
        engine_limit=None,
        gearbox_limit=None,
        apply_corrections=False,
    )

    assert len(player_only.engines) == 1
    assert len(all_companies.engines) == 1
    assert len(all_companies.skipped_designs) == 1
    assert all_companies.skipped_designs[0].kind == "engine"
    assert all_companies.skipped_designs[0].company_id == 99
    assert "tech_materials" in all_companies.skipped_designs[0].reason


def test_build_save_dataset_pipeline_exports_skipped_designs(
    sample_save_db: Path,
    tmp_path: Path,
):
    db_path = tmp_path / "mixed.db"
    shutil.copy(sample_save_db, db_path)
    _insert_bad_ai_engine(db_path)
    out = tmp_path / "datasets"

    result = build_save_dataset_pipeline([db_path], output_dir=out, apply_corrections=False)

    assert result["skipped_design_count"] == 1
    assert (out / "skipped_designs.csv").is_file()
    assert len(result["engine_df"]) >= 1


@pytest.mark.skipif(
    not Path("2001-start.db").is_file(),
    reason="local 2001-start.db save not present",
)
def test_2001_start_save_loads_many_designs():
    report = calibrate_save_game(
        "2001-start.db",
        engine_limit=None,
        gearbox_limit=None,
        apply_corrections=False,
    )
    assert len(report.engines) >= 1000
    assert len(report.gearboxes) >= 100
    assert len(report.skipped_designs) <= 5
