"""Read GearCity SQLite save games (.db) for formula calibration."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SaveLayoutComponent:
    """Engine layout row from LayoutComponents (Components.xml snapshot in save)."""

    name: str
    engine_length: float
    engine_width: float
    layout_power: float
    layout_fuel: float
    layout_smooth: float
    cylinder_length_arrangement: int
    layout_weight: float


@dataclass(frozen=True)
class SaveEngineRecord:
    """One finished or in-progress engine design from EngineInfo."""

    engine_id: int
    company_id: int
    name: str
    year_built: int
    layout: str
    cylinders_label: str
    cylinder_count: int
    fuel_type: str
    induction: str
    valve: str
    bore: float
    stroke: float
    displacement_cc: int
    length_in: float
    width_in: float
    weight_lb: float
    torque_lbft: float
    horsepower: float
    rpm: float
    fuel_mpg: float
    engine_power_rating: float
    engine_fuel_rating: float
    engine_reliability_rating: float
    overall_rating: float
    slider_displace: float
    slider_length: float
    slider_width: float
    slider_weight: float
    slider_rpm: float
    slider_torq: float
    slider_eco: float
    slider_materials: float
    slider_techniques: float
    slider_tech: float
    slider_components: float
    slider_design_performance: float
    slider_design_fuel: float
    slider_design_dependability: float
    design_pace: float
    mod_amount: int
    mod_year: int
    static_engine_power_rating: float
    static_engine_fuel_rating: float
    static_engine_reliability_rating: float


@dataclass(frozen=True)
class SaveGearboxRecord:
    """One gearbox design from GearboxInfo."""

    gearbox_id: int
    company_id: int
    name: str
    year_built: int
    gears: int
    gearbox_type: str
    has_reverse: bool
    has_overdrive: bool
    has_limited_slip: bool
    has_transaxle: bool
    low_ratio: float
    high_ratio: float
    torque_input_ratio: float
    max_torque_input_lbft: float
    mod_amount: int
    weight_lb: float
    power_rating: float
    fuel_rating: float
    performance_rating: float
    reliability_rating: float
    overall_rating: float
    tech_material: float
    tech_parts: float
    tech_techniques: float
    tech_tech: float
    design_performance: float
    design_fuel: float
    design_dependability: float
    design_ease: float
    sub_weight: float
    sub_complexity: float
    sub_smoothness: float
    sub_comfort: float
    sub_fuel: float
    sub_performance: float
    design_pace: float


@dataclass(frozen=True)
class SaveGameSnapshot:
    """Parsed subset of a GearCity save used for calibration."""

    path: Path
    current_year: int | None
    layouts: dict[str, SaveLayoutComponent]
    engines: list[SaveEngineRecord]
    gearboxes: list[SaveGearboxRecord]


def _float(value: object, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: object, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _bool(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes"}



def load_save_game(path: str | Path, *, company_id: int | None = None) -> SaveGameSnapshot:
    """Load engine/gearbox designs and layout components from a save database."""
    db_path = Path(path)
    if not db_path.is_file():
        raise FileNotFoundError(f"Save game not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        current_year: int | None = None
        try:
            row = conn.execute(
                "SELECT GameInfo_Data FROM GameInfo WHERE GameInfo_Varible = 'Current_Year' LIMIT 1"
            ).fetchone()
            if row is not None:
                current_year = _int(row[0], 0) or None
        except sqlite3.Error:
            current_year = None

        layouts: dict[str, SaveLayoutComponent] = {}
        for row in conn.execute(
            """
            SELECT Name, Engine_Length, Engine_Width, Engine_LayoutPower,
                   Engine_LayoutFuel, Engine_LayoutSmooth, CylinderLengthArrangment,
                   Weight
            FROM LayoutComponents
            """
        ):
            name = str(row["Name"] or "").strip()
            if not name:
                continue
            layouts[name] = SaveLayoutComponent(
                name=name,
                engine_length=_float(row["Engine_Length"], 0.3),
                engine_width=_float(row["Engine_Width"], 0.3),
                layout_power=_float(row["Engine_LayoutPower"], 0.3),
                layout_fuel=_float(row["Engine_LayoutFuel"], 0.3),
                layout_smooth=_float(row["Engine_LayoutSmooth"], 0.3),
                cylinder_length_arrangement=_int(row["CylinderLengthArrangment"], 1),
                layout_weight=_float(row["Weight"], 0.3),
            )

        engine_query = "SELECT * FROM EngineInfo"
        engine_params: tuple[int, ...] = ()
        if company_id is not None:
            engine_query += " WHERE Company_ID = ?"
            engine_params = (company_id,)
        engine_query += " ORDER BY yearbuilt DESC, Engine_ID DESC"

        engines: list[SaveEngineRecord] = []
        for row in conn.execute(engine_query, engine_params):
            cyl_count = _int(row["CylinderNumberForCalculations"], 0)
            if cyl_count <= 0:
                cyl_count = max(_int(row["size_cc"], 0) // 500, 1)
            engines.append(
                SaveEngineRecord(
                    engine_id=_int(row["Engine_ID"]),
                    company_id=_int(row["Company_ID"]),
                    name=str(row["Name"] or ""),
                    year_built=_int(row["yearbuilt"], 1900),
                    layout=str(row["Layout"] or "").strip(),
                    cylinders_label=str(row["Cylinders"] or "").strip(),
                    cylinder_count=cyl_count,
                    fuel_type=str(row["Fueltype"] or "").strip(),
                    induction=str(row["Induction"] or "").strip(),
                    valve=str(row["Valve"] or "").strip(),
                    bore=_float(row["bore"]),
                    stroke=_float(row["stroke"]),
                    displacement_cc=_int(row["size_cc"]),
                    length_in=_float(row["length"]),
                    width_in=_float(row["width"]),
                    weight_lb=_float(row["weight"]),
                    torque_lbft=_float(row["torque"]),
                    horsepower=_float(row["hp"]),
                    rpm=_float(row["rpm"]),
                    fuel_mpg=_float(row["fuelmilage"]),
                    engine_power_rating=_float(row["enginePower"]),
                    engine_fuel_rating=_float(row["engineFuelEco"]),
                    engine_reliability_rating=_float(row["engineReliability"]),
                    overall_rating=_float(row["overallRating"]),
                    slider_displace=_float(row["slider_displace"]),
                    slider_length=_float(row["slider_length"]),
                    slider_width=_float(row["slider_width"]),
                    slider_weight=_float(row["slider_weight"]),
                    slider_rpm=_float(row["slider_rpm"]),
                    slider_torq=_float(row["slider_torq"]),
                    slider_eco=_float(row["slider_eco"]),
                    slider_materials=_float(row["slider_materials"]),
                    slider_techniques=_float(row["slider_techniques"]),
                    slider_tech=_float(row["slider_tech"]),
                    slider_components=_float(row["slider_compoenents"]),
                    slider_design_performance=_float(row["slider_designperformance"]),
                    slider_design_fuel=_float(row["slider_designfueleco"]),
                    slider_design_dependability=_float(row["slider_designdependability"]),
                    design_pace=_float(row["DesignPace"], 0.5),
                    mod_amount=_int(row["ModAmount"]),
                    mod_year=_int(row["ModYear"]),
                    static_engine_power_rating=_float(row["StaticenginePower"]),
                    static_engine_fuel_rating=_float(row["StaticengineFuelEco"]),
                    static_engine_reliability_rating=_float(row["StaticengineReliability"]),
                )
            )

        gearbox_query = "SELECT * FROM GearboxInfo"
        gearbox_params: tuple[int, ...] = ()
        if company_id is not None:
            gearbox_query += " WHERE Company_ID = ?"
            gearbox_params = (company_id,)
        gearbox_query += " ORDER BY YearBuilt DESC, Gearbox_ID DESC"

        gearboxes: list[SaveGearboxRecord] = []
        for row in conn.execute(gearbox_query, gearbox_params):
            gearboxes.append(
                SaveGearboxRecord(
                    gearbox_id=_int(row["Gearbox_ID"]),
                    company_id=_int(row["Company_ID"]),
                    name=str(row["Name"] or ""),
                    year_built=_int(row["YearBuilt"], 1900),
                    gears=_int(row["Gears"], 2),
                    gearbox_type=str(row["GearboxType"] or "").strip(),
                    has_reverse=_bool(row["Reverse"]),
                    has_overdrive=_bool(row["Overdrive"]),
                    has_limited_slip=_bool(row["Limited"]),
                    has_transaxle=_bool(row["Transaxle"]),
                    low_ratio=_float(row["LoRatio"]),
                    high_ratio=_float(row["HiRatio"]),
                    torque_input_ratio=_float(row["TorqueInputRatio"], 0.3),
                    max_torque_input_lbft=_float(row["MaxTorqueInput"]),
                    mod_amount=_int(row["ModAmount"]),
                    weight_lb=_float(row["Weight"]),
                    power_rating=_float(row["PowerRating"]),
                    fuel_rating=_float(row["FuelRating"]),
                    performance_rating=_float(row["PerformanceRating"]),
                    reliability_rating=_float(row["ReliabiltyRating"]),
                    overall_rating=_float(row["OverallRating"]),
                    tech_material=_float(row["Tech_Material"]),
                    tech_parts=_float(row["Tech_Parts"]),
                    tech_techniques=_float(row["Tech_Techniques"]),
                    tech_tech=_float(row["Tech_Tech"]),
                    design_performance=_float(row["de_performance"]),
                    design_fuel=_float(row["de_fuel"]),
                    design_dependability=_float(row["de_depend"]),
                    design_ease=_float(row["de_comfort"]),
                    sub_weight=_float(row["GB_Weight"], 0.3),
                    sub_complexity=_float(row["GB_Complexity"], 0.3),
                    sub_smoothness=_float(row["GB_Smoothness"], 0.3),
                    sub_comfort=_float(row["GB_Comfort"], 0.3),
                    sub_fuel=_float(row["GB_Fuel"], 0.3),
                    sub_performance=_float(row["GB_Performance"], 0.3),
                    design_pace=_float(row["DesignPace"], 0.5),
                )
            )
    finally:
        conn.close()

    return SaveGameSnapshot(
        path=db_path,
        current_year=current_year,
        layouts=layouts,
        engines=engines,
        gearboxes=gearboxes,
    )
