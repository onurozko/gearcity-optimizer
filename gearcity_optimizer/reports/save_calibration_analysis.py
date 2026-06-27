"""Aggregate save calibration results by design family and error pattern."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from gearcity_optimizer.reports.save_calibration import (
    EngineCalibrationResult,
    GearboxCalibrationResult,
    SaveCalibrationReport,
)


@dataclass(frozen=True)
class MetricGroupStats:
    """Mean errors for one grouped bucket."""

    label: str
    count: int
    fit_max_pct: float | None
    torque_pct: float | None
    horsepower_pct: float | None
    weight_pct: float | None
    max_torque_pct: float | None
    power_rating_pct: float | None


def _delta_map(deltas: tuple) -> dict[str, float | None]:
    return {delta.metric: delta.pct_error for delta in deltas}


def _engine_fit_max_pct(result: EngineCalibrationResult) -> float:
    deltas = _delta_map(result.deltas)
    return max(
        deltas.get("length_in") or 0.0,
        deltas.get("width_in") or 0.0,
        deltas.get("torque_lbft") or 0.0,
    )


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _mod_bucket(mod_amount: int) -> str:
    if mod_amount <= 0:
        return "mod=0"
    if mod_amount <= 2:
        return "mod=1-2"
    return "mod=3+"


def _gearbox_ratio_pattern(low_ratio: float, high_ratio: float) -> str:
    if low_ratio == 0.0 and high_ratio == 0.0:
        return "lo0_hi0"
    if high_ratio >= 0.999:
        return "hi_max"
    if low_ratio >= 0.999 and high_ratio >= 0.999:
        return "lo1_hi1"
    return "mid"


def _fuel_family(fuel_type: str) -> str:
    text = fuel_type.lower()
    if "electric" in text or "hybrid" in text:
        return "electric/hybrid"
    if "steam" in text:
        return "steam"
    if "diesel" in text:
        return "diesel"
    if "gas" in text:
        return "gasoline"
    return fuel_type or "unknown"


def _valve_family(valve: str) -> str:
    text = valve.lower()
    if "dohc" in text:
        return "DOHC"
    if "sohc" in text:
        return "SOHC"
    if "f head" in text or "flat" in text:
        return "F Head"
    if "ohv" in text:
        return "OHV"
    return valve or "unknown"


def _append_engine_stats(
    buckets: dict[str, list[EngineCalibrationResult]],
    key: str,
    result: EngineCalibrationResult,
) -> None:
    buckets[key].append(result)


def analyze_engine_groups(report: SaveCalibrationReport) -> list[MetricGroupStats]:
    """Group engine calibration rows by fuel, layout, valve, and mod amount."""
    by_fuel: dict[str, list[EngineCalibrationResult]] = defaultdict(list)
    by_layout: dict[str, list[EngineCalibrationResult]] = defaultdict(list)
    by_valve: dict[str, list[EngineCalibrationResult]] = defaultdict(list)
    by_mod: dict[str, list[EngineCalibrationResult]] = defaultdict(list)

    for result in report.engines:
        record = result.record
        _append_engine_stats(by_fuel, _fuel_family(record.fuel_type), result)
        _append_engine_stats(by_layout, record.layout or "?", result)
        _append_engine_stats(by_valve, _valve_family(record.valve), result)
        _append_engine_stats(by_mod, _mod_bucket(record.mod_amount), result)

    groups: list[MetricGroupStats] = []
    for prefix, bucket in (
        ("fuel", by_fuel),
        ("layout", by_layout),
        ("valve", by_valve),
        ("mod", by_mod),
    ):
        for key, rows in sorted(bucket.items()):
            groups.append(_engine_group_stats(f"{prefix}:{key}", rows))
    return groups


def _engine_group_stats(label: str, rows: list[EngineCalibrationResult]) -> MetricGroupStats:
    deltas = [_delta_map(row.deltas) for row in rows]
    return MetricGroupStats(
        label=label,
        count=len(rows),
        fit_max_pct=_mean([_engine_fit_max_pct(row) for row in rows]),
        torque_pct=_mean([item.get("torque_lbft") or 0.0 for item in deltas]),
        horsepower_pct=_mean([item.get("horsepower") or 0.0 for item in deltas]),
        weight_pct=_mean([item.get("weight_lb") or 0.0 for item in deltas]),
        max_torque_pct=None,
        power_rating_pct=_mean([item.get("engine_power_rating") or 0.0 for item in deltas]),
    )


def analyze_gearbox_groups(report: SaveCalibrationReport) -> list[MetricGroupStats]:
    """Group gearbox calibration rows by mod amount and save ratio pattern."""
    by_mod: dict[str, list[GearboxCalibrationResult]] = defaultdict(list)
    by_ratio: dict[str, list[GearboxCalibrationResult]] = defaultdict(list)

    for result in report.gearboxes:
        record = result.record
        by_mod[_mod_bucket(record.mod_amount)].append(result)
        by_ratio[_gearbox_ratio_pattern(record.low_ratio, record.high_ratio)].append(result)

    groups: list[MetricGroupStats] = []
    for prefix, bucket in (("mod", by_mod), ("ratio", by_ratio)):
        for key, rows in sorted(bucket.items()):
            groups.append(_gearbox_group_stats(f"{prefix}:{key}", rows))
    return groups


def _gearbox_group_stats(label: str, rows: list[GearboxCalibrationResult]) -> MetricGroupStats:
    deltas = [_delta_map(row.deltas) for row in rows]
    return MetricGroupStats(
        label=label,
        count=len(rows),
        fit_max_pct=None,
        torque_pct=None,
        horsepower_pct=None,
        weight_pct=_mean([item.get("weight_lb") or 0.0 for item in deltas]),
        max_torque_pct=_mean([item.get("max_torque_lbft") or 0.0 for item in deltas]),
        power_rating_pct=_mean([item.get("power_rating") or 0.0 for item in deltas]),
    )


def _count_passing(
    report: SaveCalibrationReport,
    *,
    fit_threshold: float = 5.0,
    hp_threshold: float = 10.0,
    torque_threshold: float = 10.0,
) -> tuple[int, int, int, int]:
    gas_engines = [
        result
        for result in report.engines
        if _fuel_family(result.record.fuel_type) == "gasoline"
    ]
    fit_ok = sum(1 for row in gas_engines if _engine_fit_max_pct(row) <= fit_threshold)
    hp_ok = sum(
        1
        for row in gas_engines
        if (_delta_map(row.deltas).get("horsepower") or 999.0) <= hp_threshold
    )
    torque_ok = sum(
        1
        for row in gas_engines
        if (_delta_map(row.deltas).get("torque_lbft") or 999.0) <= torque_threshold
    )
    gb_ok = sum(
        1
        for row in report.gearboxes
        if (_delta_map(row.deltas).get("max_torque_lbft") or 999.0) <= 10.0
    )
    return fit_ok, hp_ok, torque_ok, gb_ok


def format_calibration_analysis(report: SaveCalibrationReport) -> list[str]:
    """Render a save-wide analysis summary grouped by design family."""
    lines: list[str] = []
    lines.append("Save-wide analysis (grouped by design family)")
    lines.append("")

    fit_ok, hp_ok, torque_ok, gb_ok = _count_passing(report)
    gas_count = sum(
        1 for row in report.engines if _fuel_family(row.record.fuel_type) == "gasoline"
    )
    lines.append(
        f"Gasoline engines within thresholds: "
        f"fit<=5% {fit_ok}/{gas_count}, "
        f"torque<=10% {torque_ok}/{gas_count}, "
        f"hp<=10% {hp_ok}/{gas_count}"
    )
    lines.append(
        f"Gearboxes max_torque<=10%: {gb_ok}/{len(report.gearboxes)}"
    )
    lines.append("")

    lines.append("Engine groups (mean pct error):")
    for group in analyze_engine_groups(report):
        lines.append(
            f"  {group.label:24s} n={group.count:2d} | "
            f"fit {group.fit_max_pct:5.1f}% | "
            f"tq {group.torque_pct:5.1f}% | "
            f"hp {group.horsepower_pct:5.1f}% | "
            f"wt {group.weight_pct:5.1f}%"
        )
    lines.append("")

    lines.append("Gearbox groups (mean pct error):")
    for group in analyze_gearbox_groups(report):
        lines.append(
            f"  {group.label:24s} n={group.count:2d} | "
            f"max_tq {group.max_torque_pct:5.1f}% | "
            f"wt {group.weight_pct:5.1f}% | "
            f"pwr {group.power_rating_pct:5.1f}%"
        )
    lines.append("")

    lines.append("Worst gasoline engine fit (top 5):")
    gas_rows = sorted(
        (
            result
            for result in report.engines
            if _fuel_family(result.record.fuel_type) == "gasoline"
        ),
        key=_engine_fit_max_pct,
        reverse=True,
    )[:5]
    for result in gas_rows:
        record = result.record
        deltas = _delta_map(result.deltas)
        lines.append(
            f"  id={record.engine_id} {record.layout}/{_valve_family(record.valve)} "
            f"mod={record.mod_amount} fit={_engine_fit_max_pct(result):.1f}% "
            f"tq={deltas.get('torque_lbft') or 0:.1f}% hp={deltas.get('horsepower') or 0:.1f}%"
        )
    lines.append("")

    lines.append("Worst gearbox max_torque (top 5):")
    gb_rows = sorted(
        report.gearboxes,
        key=lambda row: _delta_map(row.deltas).get("max_torque_lbft") or 0.0,
        reverse=True,
    )[:5]
    for result in gb_rows:
        record = result.record
        deltas = _delta_map(result.deltas)
        pattern = _gearbox_ratio_pattern(record.low_ratio, record.high_ratio)
        lines.append(
            f"  id={record.gearbox_id} {record.gears}g mod={record.mod_amount} "
            f"{pattern} max_tq={deltas.get('max_torque_lbft') or 0:.1f}% "
            f"pwr={deltas.get('power_rating') or 0:.1f}%"
        )
    lines.append("")

    lines.append("Systematic patterns:")
    electric = [r for r in report.engines if _fuel_family(r.record.fuel_type) == "electric/hybrid"]
    steam = [r for r in report.engines if _fuel_family(r.record.fuel_type) == "steam"]
    stale_gb = [
        r
        for r in report.gearboxes
        if (_delta_map(r.deltas).get("power_rating") or 0.0) > 100.0
        and r.record.power_rating > 0
    ]
    mod_gb_bad = [
        r
        for r in report.gearboxes
        if r.record.mod_amount >= 3
        and (_delta_map(r.deltas).get("max_torque_lbft") or 0.0) > 15.0
    ]
    lines.append(
        f"  Unsupported fuel families: electric/hybrid={len(electric)}, steam={len(steam)} "
        "(wiki gas formula; expect large HP/torque gaps)"
    )
    lines.append(
        f"  Gearboxes with stale power ratings (>100% err): {len(stale_gb)}/{len(report.gearboxes)}"
    )
    lines.append(
        f"  Mod=3+ gearboxes with max_torque>15% err: {len(mod_gb_bad)}"
    )
    return lines
