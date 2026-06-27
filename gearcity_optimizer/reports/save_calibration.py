"""Compare wiki formula predictions against GearCity save game designs."""

from __future__ import annotations

from dataclasses import dataclass, replace

from gearcity_optimizer.formulas.engine_formula import EngineFormulaInputs, calculate_engine
from gearcity_optimizer.formulas.gearbox_formula import (
    GearboxFormulaInputs,
    calculate_gearbox,
    normalize_save_gear_ratios,
    save_unset_gear_ratio_torque_bonus,
)
from gearcity_optimizer.importers.save_db import (
    SaveEngineRecord,
    SaveGameSnapshot,
    SaveGearboxRecord,
    SaveLayoutComponent,
    load_save_game,
)
from gearcity_optimizer.importers.save_engine_flags import engine_formula_flags_from_save


@dataclass(frozen=True)
class MetricDelta:
    """One predicted vs in-game comparison."""

    metric: str
    game_value: float
    predicted_value: float
    abs_error: float
    pct_error: float | None


@dataclass(frozen=True)
class EngineCalibrationResult:
    """Formula replay result for one save engine."""

    record: SaveEngineRecord
    layout: SaveLayoutComponent | None
    deltas: tuple[MetricDelta, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True)
class GearboxCalibrationResult:
    """Formula replay result for one save gearbox."""

    record: SaveGearboxRecord
    inferred_torque_max_input_slider: float
    deltas: tuple[MetricDelta, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True)
class SaveCalibrationReport:
    """Aggregate calibration output for a save file."""

    snapshot: SaveGameSnapshot
    engines: tuple[EngineCalibrationResult, ...]
    gearboxes: tuple[GearboxCalibrationResult, ...]
    engine_summary: dict[str, float]
    gearbox_summary: dict[str, float]


def _delta(metric: str, game_value: float, predicted_value: float) -> MetricDelta:
    abs_error = abs(predicted_value - game_value)
    pct_error = None
    if abs(game_value) > 1e-6:
        pct_error = abs_error / abs(game_value) * 100.0
    return MetricDelta(
        metric=metric,
        game_value=game_value,
        predicted_value=predicted_value,
        abs_error=abs_error,
        pct_error=pct_error,
    )


def _infer_gearbox_torque_slider(
    base: GearboxFormulaInputs,
    target_lbft: float,
) -> float:
    if target_lbft <= 0:
        return 0.3
    lo, hi = 0.0, 1.0
    best = 0.3
    best_err = float("inf")
    for _ in range(28):
        mid = (lo + hi) / 2.0
        trial = replace(base, torque_max_input=mid)
        predicted = calculate_gearbox(trial).max_torque_support
        err = abs(predicted - target_lbft)
        if err < best_err:
            best_err = err
            best = mid
        if predicted < target_lbft:
            lo = mid
        else:
            hi = mid
    return best


def engine_formula_inputs_from_save(
    record: SaveEngineRecord,
    layout: SaveLayoutComponent | None,
) -> EngineFormulaInputs:
    """Map a save EngineInfo row onto wiki formula inputs."""
    arrangement = layout.cylinder_length_arrangement if layout is not None else 1
    sub_length = layout.engine_length if layout is not None else 0.42
    sub_width = layout.engine_width if layout is not None else 0.42
    layout_power = layout.layout_power if layout is not None else 0.3

    kwargs: dict[str, object] = {
        "name": record.name,
        "year": max(record.year_built, 1899),
        "cylinders": max(record.cylinder_count, 1),
        "displacement": float(record.displacement_cc) if record.displacement_cc > 0 else 800.0,
        "layout_length": sub_length,
        "layout_width": sub_width,
        "layout_performance": layout_power,
        "layout_weight": record.slider_weight if record.slider_weight > 0 else 0.3,
        "design_performance": record.slider_design_performance,
        "design_fuel_economy": record.slider_design_fuel,
        "design_dependability": record.slider_design_dependability,
        "design_pace": record.design_pace,
        "tech_materials": record.slider_materials,
        "tech_components": record.slider_components,
        "tech_techniques": record.slider_techniques,
        "tech_technology": record.slider_tech,
        "cylinder_bank_arrangement": arrangement,
        "wiki_subcomponent_layout_length": sub_length,
        "wiki_subcomponent_layout_width": sub_width,
        "wiki_slider_layout_length": record.slider_length,
        "wiki_slider_layout_width": record.slider_width,
        "wiki_slider_performance_torque": record.slider_torq,
        "wiki_slider_performance_revolutions": record.slider_rpm,
        "wiki_slider_performance_fuel": record.slider_eco,
        **engine_formula_flags_from_save(
            valve=record.valve,
            induction=record.induction,
            fuel_type=record.fuel_type,
        ),
    }
    if record.bore > 0 and record.stroke > 0:
        kwargs["bore"] = record.bore
        kwargs["stroke"] = record.stroke
    return EngineFormulaInputs(**kwargs)  # type: ignore[arg-type]


def gearbox_formula_inputs_from_save(
    record: SaveGearboxRecord,
    *,
    torque_max_input: float,
) -> GearboxFormulaInputs:
    """Map a save GearboxInfo row onto wiki formula inputs."""
    low_ratio, high_ratio = normalize_save_gear_ratios(
        record.low_ratio,
        record.high_ratio,
    )
    return GearboxFormulaInputs(
        name=record.name,
        year=max(record.year_built, 1899),
        number_of_gears=max(record.gears, 1),
        has_reverse=record.has_reverse,
        has_overdrive=record.has_overdrive,
        has_limited_slip=record.has_limited_slip,
        has_transaxle=record.has_transaxle,
        low_gear_ratio=low_ratio,
        high_gear_ratio=high_ratio,
        torque_max_input=torque_max_input,
        tech_material=record.tech_material,
        tech_components=record.tech_parts,
        tech_technology=record.tech_tech,
        tech_techniques=record.tech_techniques,
        design_ease=record.design_ease,
        design_performance=record.design_performance,
        design_fuel_economy=record.design_fuel,
        design_dependability=record.design_dependability,
        subcomponent_weight=record.sub_weight,
        subcomponent_complexity=record.sub_complexity,
        subcomponent_smoothness=record.sub_smoothness,
        subcomponent_ease=record.sub_comfort,
        subcomponent_fuel_rating=record.sub_fuel,
        subcomponent_performance_rating=record.sub_performance,
    )


def calibrate_engine_record(
    record: SaveEngineRecord,
    layout: SaveLayoutComponent | None,
) -> EngineCalibrationResult:
    """Replay one engine through wiki formulas and compare to save stats."""
    notes: list[str] = []
    if layout is None:
        notes.append(f"Layout '{record.layout}' not found in LayoutComponents table.")

    predicted = calculate_engine(engine_formula_inputs_from_save(record, layout))
    deltas = (
        _delta("length_in", record.length_in, predicted.length),
        _delta("width_in", record.width_in, predicted.width),
        _delta("torque_lbft", record.torque_lbft, predicted.torque),
        _delta("horsepower", record.horsepower, predicted.horsepower),
        _delta("weight_lb", record.weight_lb, predicted.weight),
        _delta("engine_power_rating", record.engine_power_rating, predicted.performance_rating),
        _delta("engine_fuel_rating", record.engine_fuel_rating, predicted.fuel_economy),
        _delta(
            "engine_reliability_rating",
            record.engine_reliability_rating,
            predicted.reliability_rating,
        ),
        _delta("overall_rating", record.overall_rating, predicted.overall_rating),
    )
    return EngineCalibrationResult(
        record=record,
        layout=layout,
        deltas=deltas,
        notes=tuple(notes),
    )


def calibrate_gearbox_record(record: SaveGearboxRecord) -> GearboxCalibrationResult:
    """Replay one gearbox through wiki formulas and compare to save stats."""
    notes: list[str] = []
    low_ratio, high_ratio = normalize_save_gear_ratios(
        record.low_ratio,
        record.high_ratio,
    )
    base = replace(
        gearbox_formula_inputs_from_save(record, torque_max_input=0.3),
        low_gear_ratio=low_ratio,
        high_gear_ratio=high_ratio,
    )

    if record.torque_input_ratio >= 0.0:
        inferred = record.torque_input_ratio
        if abs(inferred - 0.3) > 0.05:
            notes.append(
                f"Using save TorqueInputRatio slider {inferred:.3f}."
            )
    else:
        inferred = _infer_gearbox_torque_slider(base, record.max_torque_input_lbft)
        notes.append(
            f"Inferred Torque Max Input slider {inferred:.3f} from save MaxTorqueInput "
            f"{record.max_torque_input_lbft:.1f} lb-ft."
        )

    if record.mod_amount > 0:
        notes.append(
            f"Gearbox has ModAmount={record.mod_amount}; save MaxTorqueInput may include "
            "post-design modification uplift not in the wiki formula."
        )

    if record.low_ratio == 0.0 and record.high_ratio == 0.0:
        notes.append(
            "Save LoRatio/HiRatio are both zero (unset sliders); applying save-game "
            "max-torque bonus on top of wiki formula."
        )
    elif record.high_ratio >= 0.999 and record.low_ratio < 0.999:
        notes.append(
            "Save HiRatio is 1.0 (max slider); mapped to wiki high-end ratio 0.0 for torque."
        )

    predicted = calculate_gearbox(
        gearbox_formula_inputs_from_save(record, torque_max_input=inferred)
    )
    max_torque_pred = predicted.max_torque_support + save_unset_gear_ratio_torque_bonus(
        record.low_ratio,
        record.high_ratio,
        record.year_built,
    )

    if predicted.power_rating > record.power_rating * 2.0 and record.power_rating > 0:
        notes.append(
            "Stored power/performance ratings look much lower than formula replay; "
            "they may be stale relative to current MaxTorqueInput and tech sliders."
        )

    deltas = (
        _delta(
            "max_torque_lbft",
            record.max_torque_input_lbft,
            max_torque_pred,
        ),
        _delta("weight_lb", record.weight_lb, predicted.weight),
        _delta("power_rating", record.power_rating, predicted.power_rating),
        _delta("fuel_rating", record.fuel_rating, predicted.fuel_economy_rating),
        _delta("performance_rating", record.performance_rating, predicted.performance_rating),
        _delta(
            "reliability_rating",
            record.reliability_rating,
            predicted.reliability_rating,
        ),
        _delta("overall_rating", record.overall_rating, predicted.overall_rating),
    )
    return GearboxCalibrationResult(
        record=record,
        inferred_torque_max_input_slider=inferred,
        deltas=deltas,
        notes=tuple(notes),
    )


def _summary_for_deltas(
    results: list[tuple[MetricDelta, ...]],
    metrics: tuple[str, ...],
) -> dict[str, float]:
    summary: dict[str, float] = {}
    for metric in metrics:
        errors = [
            delta.abs_error
            for deltas in results
            for delta in deltas
            if delta.metric == metric
        ]
        if not errors:
            continue
        summary[f"{metric}_mean_abs_error"] = sum(errors) / len(errors)
        pct_values = [
            delta.pct_error
            for deltas in results
            for delta in deltas
            if delta.metric == metric and delta.pct_error is not None
        ]
        if pct_values:
            summary[f"{metric}_mean_pct_error"] = sum(pct_values) / len(pct_values)
    return summary


def calibrate_save_game(
    path: str,
    *,
    company_id: int | None = 0,
    engine_limit: int | None = 25,
    gearbox_limit: int | None = 25,
    engine_ids: set[int] | None = None,
    gearbox_ids: set[int] | None = None,
) -> SaveCalibrationReport:
    """Load a save and compare formula outputs to in-game EngineInfo/GearboxInfo rows."""
    snapshot = load_save_game(path, company_id=company_id)

    engine_rows = snapshot.engines
    if engine_ids:
        engine_rows = [row for row in engine_rows if row.engine_id in engine_ids]
    if engine_limit is not None:
        engine_rows = engine_rows[:engine_limit]

    gearbox_rows = snapshot.gearboxes
    if gearbox_ids:
        gearbox_rows = [row for row in gearbox_rows if row.gearbox_id in gearbox_ids]
    if gearbox_limit is not None:
        gearbox_rows = gearbox_rows[:gearbox_limit]

    engine_results = tuple(
        calibrate_engine_record(row, snapshot.layouts.get(row.layout))
        for row in engine_rows
    )
    gearbox_results = tuple(calibrate_gearbox_record(row) for row in gearbox_rows)

    engine_metrics = (
        "length_in",
        "width_in",
        "torque_lbft",
        "horsepower",
        "engine_power_rating",
        "engine_fuel_rating",
    )
    gearbox_metrics = ("max_torque_lbft", "weight_lb", "power_rating", "overall_rating")

    return SaveCalibrationReport(
        snapshot=snapshot,
        engines=engine_results,
        gearboxes=gearbox_results,
        engine_summary=_summary_for_deltas(
            [item.deltas for item in engine_results],
            engine_metrics,
        ),
        gearbox_summary=_summary_for_deltas(
            [item.deltas for item in gearbox_results],
            gearbox_metrics,
        ),
    )


def format_engine_calibration_lines(result: EngineCalibrationResult) -> list[str]:
    """Human-readable lines for one engine comparison."""
    record = result.record
    lines = [
        f"Engine {record.engine_id} {record.name} ({record.year_built}) "
        f"layout={record.layout} cyl={record.cylinder_count} "
        f"bore={record.bore:.1f} stroke={record.stroke:.1f}",
    ]
    for note in result.notes:
        lines.append(f"  NOTE: {note}")
    for delta in result.deltas:
        pct = f" ({delta.pct_error:.1f}%)" if delta.pct_error is not None else ""
        lines.append(
            f"  {delta.metric}: game={delta.game_value:.2f} "
            f"predicted={delta.predicted_value:.2f} err={delta.abs_error:.2f}{pct}"
        )
    return lines


def format_gearbox_calibration_lines(result: GearboxCalibrationResult) -> list[str]:
    """Human-readable lines for one gearbox comparison."""
    record = result.record
    lines = [
        f"Gearbox {record.gearbox_id} {record.name} ({record.year_built}) "
        f"{record.gears} gears {record.gearbox_type}",
    ]
    for note in result.notes:
        lines.append(f"  NOTE: {note}")
    for delta in result.deltas:
        pct = f" ({delta.pct_error:.1f}%)" if delta.pct_error is not None else ""
        lines.append(
            f"  {delta.metric}: game={delta.game_value:.2f} "
            f"predicted={delta.predicted_value:.2f} err={delta.abs_error:.2f}{pct}"
        )
    return lines


def report_to_csv_rows(report: SaveCalibrationReport) -> list[dict[str, object]]:
    """Flatten calibration results for CSV export."""
    rows: list[dict[str, object]] = []
    for item in report.engines:
        base = {
            "kind": "engine",
            "id": item.record.engine_id,
            "name": item.record.name,
            "year": item.record.year_built,
            "layout": item.record.layout,
            "cylinders": item.record.cylinder_count,
            "bore_mm": item.record.bore,
            "stroke_mm": item.record.stroke,
        }
        for delta in item.deltas:
            rows.append(
                {
                    **base,
                    "metric": delta.metric,
                    "game_value": delta.game_value,
                    "predicted_value": delta.predicted_value,
                    "abs_error": delta.abs_error,
                    "pct_error": delta.pct_error,
                }
            )
    for item in report.gearboxes:
        base = {
            "kind": "gearbox",
            "id": item.record.gearbox_id,
            "name": item.record.name,
            "year": item.record.year_built,
            "gears": item.record.gears,
            "gearbox_type": item.record.gearbox_type,
            "inferred_torque_slider": item.inferred_torque_max_input_slider,
        }
        for delta in item.deltas:
            rows.append(
                {
                    **base,
                    "metric": delta.metric,
                    "game_value": delta.game_value,
                    "predicted_value": delta.predicted_value,
                    "abs_error": delta.abs_error,
                    "pct_error": delta.pct_error,
                }
            )
    return rows
