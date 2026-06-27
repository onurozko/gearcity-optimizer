"""Segment-based calibration corrections fitted from save datasets at scale."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from gearcity_optimizer.importers.save_db import SaveEngineRecord, SaveGearboxRecord
from gearcity_optimizer.reports.save_calibration_features import (
    ENGINE_SEGMENT_COLS,
    GEARBOX_SEGMENT_COLS,
    fuel_family,
    gearbox_ratio_pattern,
    mod_bucket,
    valve_family,
)

SUPPORTED_ENGINE_FUEL_FAMILIES = frozenset({"gasoline", "diesel"})

ENGINE_METRICS = ("torque", "horsepower", "length", "width")
GEARBOX_METRICS = ("max_torque",)

ENGINE_SIGNED_COLS = {
    "torque": "signed_torque_pct",
    "horsepower": "signed_horsepower_pct",
    "length": "signed_length_pct",
    "width": "signed_width_pct",
}

GEARBOX_SIGNED_COLS = {
    "max_torque": "signed_max_torque_pct",
}

ENGINE_SEGMENT_LEVELS: tuple[tuple[str, ...], ...] = (
    ENGINE_SEGMENT_COLS,
    ("fuel_family", "layout", "valve_family"),
    ("fuel_family", "layout"),
    ("fuel_family",),
)

GEARBOX_SEGMENT_LEVELS: tuple[tuple[str, ...], ...] = (
    GEARBOX_SEGMENT_COLS,
    ("mod_bucket", "ratio_pattern"),
    ("mod_bucket",),
)


def engine_formula_supported(record: SaveEngineRecord) -> bool:
    """Return True when the wiki gas engine formula applies to this save row."""
    return fuel_family(record.fuel_type) in SUPPORTED_ENGINE_FUEL_FAMILIES


def engine_segment_key(record: SaveEngineRecord, *, level: int = 0) -> str:
    """Build a pipe-delimited segment key for an engine record."""
    cols = ENGINE_SEGMENT_LEVELS[min(level, len(ENGINE_SEGMENT_LEVELS) - 1)]
    values = {
        "fuel_family": fuel_family(record.fuel_type),
        "layout": record.layout,
        "valve_family": valve_family(record.valve),
        "mod_bucket": mod_bucket(record.mod_amount),
    }
    return "|".join(f"{col}={values[col]}" for col in cols)


def gearbox_segment_key(record: SaveGearboxRecord, *, level: int = 0) -> str:
    """Build a pipe-delimited segment key for a gearbox record."""
    cols = GEARBOX_SEGMENT_LEVELS[min(level, len(GEARBOX_SEGMENT_LEVELS) - 1)]
    values = {
        "mod_bucket": mod_bucket(record.mod_amount),
        "ratio_pattern": gearbox_ratio_pattern(record.low_ratio, record.high_ratio),
        "gears": record.gears,
    }
    return "|".join(f"{col}={values[col]}" for col in cols)


def signed_pct_to_scale(signed_pct: float) -> float:
    """Convert signed pct error to a multiplicative correction scale."""
    return 1.0 / (1.0 + signed_pct / 100.0)


def scale_to_signed_pct(scale: float) -> float:
    """Inverse of signed_pct_to_scale."""
    if abs(scale) <= 1e-9:
        return 0.0
    return (1.0 / scale - 1.0) * 100.0


@dataclass
class SegmentCorrection:
    """Multiplicative scales for one design segment."""

    scales: dict[str, float]
    count: int
    level: int
    mean_signed: dict[str, float] = field(default_factory=dict)


@dataclass
class CalibrationCorrections:
    """Fitted segment corrections for engines and gearboxes."""

    version: int = 1
    engine: dict[str, SegmentCorrection] = field(default_factory=dict)
    gearbox: dict[str, SegmentCorrection] = field(default_factory=dict)

    def lookup_engine(self, record: SaveEngineRecord) -> SegmentCorrection | None:
        for level in range(len(ENGINE_SEGMENT_LEVELS)):
            key = engine_segment_key(record, level=level)
            hit = self.engine.get(key)
            if hit is not None:
                return hit
        return None

    def lookup_gearbox(self, record: SaveGearboxRecord) -> SegmentCorrection | None:
        for level in range(len(GEARBOX_SEGMENT_LEVELS)):
            key = gearbox_segment_key(record, level=level)
            hit = self.gearbox.get(key)
            if hit is not None:
                return hit
        return None

    def apply_engine(self, predicted: object, record: SaveEngineRecord) -> object:
        """Scale predicted engine physical stats using the best matching segment."""
        correction = self.lookup_engine(record)
        if correction is None:
            return predicted
        return replace_engine_prediction(predicted, correction.scales)

    def apply_gearbox_max_torque(self, predicted_max_torque: float, record: SaveGearboxRecord) -> float:
        correction = self.lookup_gearbox(record)
        if correction is None:
            return predicted_max_torque
        scale = correction.scales.get("max_torque", 1.0)
        return predicted_max_torque * scale


def replace_engine_prediction(predicted: object, scales: dict[str, float]) -> object:
    """Return predicted engine outputs with segment scales applied."""
    from dataclasses import replace

    kwargs: dict[str, float] = {}
    if "torque" in scales:
        kwargs["torque"] = predicted.torque * scales["torque"]
    if "horsepower" in scales:
        kwargs["horsepower"] = predicted.horsepower * scales["horsepower"]
    if "length" in scales:
        kwargs["length"] = predicted.length * scales["length"]
    if "width" in scales:
        kwargs["width"] = predicted.width * scales["width"]
    if not kwargs:
        return predicted
    return replace(predicted, **kwargs)


def _fit_segment_table(
    df: pd.DataFrame,
    segment_cols: tuple[str, ...],
    signed_cols: dict[str, str],
    *,
    min_count: int,
    level: int,
) -> dict[str, SegmentCorrection]:
    if df.empty:
        return {}

    grouped: dict[str, SegmentCorrection] = {}
    for keys, frame in df.groupby(list(segment_cols), dropna=False):
        if len(frame) < min_count:
            continue
        if not isinstance(keys, tuple):
            keys = (keys,)
        segment_key = "|".join(f"{col}={value}" for col, value in zip(segment_cols, keys, strict=True))

        scales: dict[str, float] = {}
        mean_signed: dict[str, float] = {}
        for metric, col in signed_cols.items():
            if col not in frame.columns:
                continue
            series = pd.to_numeric(frame[col], errors="coerce").dropna()
            if series.empty:
                continue
            signed = float(series.median())
            scales[metric] = signed_pct_to_scale(signed)
            mean_signed[metric] = signed

        if not scales:
            continue
        grouped[segment_key] = SegmentCorrection(
            scales=scales,
            count=len(frame),
            level=level,
            mean_signed=mean_signed,
        )
    return grouped


def fit_calibration_corrections(
    engine_df: pd.DataFrame,
    gearbox_df: pd.DataFrame,
    *,
    min_count: int = 2,
    min_abs_signed_pct: float = 5.0,
) -> CalibrationCorrections:
    """Fit segment correction scales from calibration dataset frames."""
    corrections = CalibrationCorrections()

    supported = (
        engine_df[engine_df["fuel_family"].isin(SUPPORTED_ENGINE_FUEL_FAMILIES)]
        if not engine_df.empty
        else engine_df
    )
    for level, segment_cols in enumerate(ENGINE_SEGMENT_LEVELS):
        fitted = _fit_segment_table(
            supported,
            segment_cols,
            ENGINE_SIGNED_COLS,
            min_count=min_count,
            level=level,
        )
        for key, value in fitted.items():
            if key in corrections.engine:
                continue
            if not any(abs(v) >= min_abs_signed_pct for v in value.mean_signed.values()):
                continue
            corrections.engine[key] = value

    for level, segment_cols in enumerate(GEARBOX_SEGMENT_LEVELS):
        fitted = _fit_segment_table(
            gearbox_df,
            segment_cols,
            GEARBOX_SIGNED_COLS,
            min_count=min_count,
            level=level,
        )
        for key, value in fitted.items():
            if key in corrections.gearbox:
                continue
            if not any(abs(v) >= min_abs_signed_pct for v in value.mean_signed.values()):
                continue
            corrections.gearbox[key] = value

    return corrections


def corrections_to_dict(corrections: CalibrationCorrections) -> dict[str, Any]:
    """Serialize corrections for JSON export."""
    def _segment_payload(item: SegmentCorrection) -> dict[str, Any]:
        return {
            "scales": item.scales,
            "count": item.count,
            "level": item.level,
            "mean_signed_pct": item.mean_signed,
        }

    return {
        "version": corrections.version,
        "engine": {key: _segment_payload(value) for key, value in corrections.engine.items()},
        "gearbox": {key: _segment_payload(value) for key, value in corrections.gearbox.items()},
    }


def corrections_from_dict(payload: dict[str, Any]) -> CalibrationCorrections:
    """Load corrections from JSON payload."""
    corrections = CalibrationCorrections(version=int(payload.get("version", 1)))

    for kind in ("engine", "gearbox"):
        entries = payload.get(kind, {})
        target = corrections.engine if kind == "engine" else corrections.gearbox
        for key, item in entries.items():
            target[key] = SegmentCorrection(
                scales={str(k): float(v) for k, v in item.get("scales", {}).items()},
                count=int(item.get("count", 0)),
                level=int(item.get("level", 0)),
                mean_signed={
                    str(k): float(v) for k, v in item.get("mean_signed_pct", {}).items()
                },
            )
    return corrections


def save_calibration_corrections(path: str | Path, corrections: CalibrationCorrections) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(corrections_to_dict(corrections), indent=2), encoding="utf-8")
    return out


def load_calibration_corrections(path: str | Path) -> CalibrationCorrections:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return corrections_from_dict(payload)


def mass_quality_summary(
    engine_df: pd.DataFrame,
    gearbox_df: pd.DataFrame,
    *,
    supported_only: bool = True,
) -> dict[str, object]:
    """Summarize pct errors across all rows for batch validation."""
    engines = engine_df
    if supported_only and not engine_df.empty:
        engines = engine_df[engine_df["fuel_family"].isin(SUPPORTED_ENGINE_FUEL_FAMILIES)]

    def _within(frame: pd.DataFrame, col: str, threshold: float) -> tuple[int, int]:
        if frame.empty or col not in frame.columns:
            return 0, 0
        series = pd.to_numeric(frame[col], errors="coerce").dropna()
        if series.empty:
            return 0, 0
        ok = int((series <= threshold).sum())
        return ok, len(series)

    engine_fit_ok, engine_fit_n = _within(engines, "fit_max_pct", 5.0)
    engine_tq_ok, engine_tq_n = _within(engines, "err_torque_pct", 10.0)
    engine_hp_ok, engine_hp_n = _within(engines, "err_horsepower_pct", 10.0)
    gb_ok, gb_n = _within(gearbox_df, "err_max_torque_pct", 10.0)

    return {
        "engine_count": len(engines),
        "gearbox_count": len(gearbox_df),
        "engine_fit_within_5pct": (engine_fit_ok, engine_fit_n),
        "engine_torque_within_10pct": (engine_tq_ok, engine_tq_n),
        "engine_hp_within_10pct": (engine_hp_ok, engine_hp_n),
        "gearbox_max_torque_within_10pct": (gb_ok, gb_n),
        "unsupported_engine_count": int(
            len(engine_df) - len(engines) if not engine_df.empty else 0
        ),
    }


def format_mass_quality_summary(summary: dict[str, object], *, label: str) -> list[str]:
    lines = [label]
    fit_ok, fit_n = summary["engine_fit_within_5pct"]
    tq_ok, tq_n = summary["engine_torque_within_10pct"]
    hp_ok, hp_n = summary["engine_hp_within_10pct"]
    gb_ok, gb_n = summary["gearbox_max_torque_within_10pct"]
    lines.append(
        f"  Supported gasoline/diesel engines: {summary['engine_count']} "
        f"(skipped {summary['unsupported_engine_count']} unsupported families)"
    )
    lines.append(f"  Gearboxes: {summary['gearbox_count']}")
    lines.append(f"  Engine fit <=5%: {fit_ok}/{fit_n}")
    lines.append(f"  Engine torque <=10%: {tq_ok}/{tq_n}")
    lines.append(f"  Engine hp <=10%: {hp_ok}/{hp_n}")
    lines.append(f"  Gearbox max torque <=10%: {gb_ok}/{gb_n}")
    return lines
