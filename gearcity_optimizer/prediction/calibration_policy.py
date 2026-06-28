"""Validation-gated calibration policy for save-backed predictions."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any

import pandas as pd

from gearcity_optimizer.formulas.engine_formula import EngineFormulaResult
from gearcity_optimizer.importers.save_db import SaveEngineRecord, SaveGearboxRecord, SaveLayoutComponent
from gearcity_optimizer.importers.wiki_downloader import project_root_from_module
from gearcity_optimizer.prediction.backend import SaveEnginePrediction, SaveGearboxPrediction, SavePredictionBackend
from gearcity_optimizer.reports.save_calibration_validation import (
    engine_predicted_value,
    gearbox_predicted_value,
)
from gearcity_optimizer.reports.save_dataset_residuals import (
    ResidualCorrectionStore,
    engine_replay_metric_names,
    gearbox_replay_metric_names,
    year_band,
)

DEFAULT_MIN_GROUP_SAMPLES = 3
IMPROVED_STATUS = "improved"


class CalibrationPolicyMode(str, Enum):
    """How save calibration is applied at prediction time."""

    ALWAYS_FORMULA_ONLY = "always_formula_only"
    ALWAYS_SAVE_CALIBRATED = "always_save_calibrated"
    VALIDATION_GATED = "validation_gated"


@dataclass(frozen=True)
class MetricPolicyRow:
    """Policy decision for one kind/metric pair."""

    kind: str
    metric: str
    validation_status: str
    calibration_enabled: bool
    selected_mode: str
    reason: str
    sample_count: int
    improvement_pct: float | None
    formula_only_mae: float | None
    save_calibrated_mae: float | None


@dataclass(frozen=True)
class GroupPolicyRow:
    """Policy decision for one grouped validation segment."""

    kind: str
    metric: str
    year_band: str
    layout: str
    fuel_type: str
    gearbox_type: str
    validation_status: str
    calibration_enabled: bool
    selected_mode: str
    reason: str
    sample_count: int
    improvement_pct: float | None
    formula_only_mae: float | None
    save_calibrated_mae: float | None


@dataclass(frozen=True)
class CalibrationPolicy:
    """Loaded validation-gating rules for save calibration."""

    mode: CalibrationPolicyMode
    validation_dir: Path | None
    min_group_samples: int
    metric_rows: tuple[MetricPolicyRow, ...]
    group_rows: tuple[GroupPolicyRow, ...]
    metric_lookup: dict[tuple[str, str], MetricPolicyRow]
    group_frame: pd.DataFrame

    @classmethod
    def empty(cls, mode: CalibrationPolicyMode = CalibrationPolicyMode.ALWAYS_FORMULA_ONLY) -> CalibrationPolicy:
        return cls(
            mode=mode,
            validation_dir=None,
            min_group_samples=DEFAULT_MIN_GROUP_SAMPLES,
            metric_rows=(),
            group_rows=(),
            metric_lookup={},
            group_frame=pd.DataFrame(),
        )

    @property
    def has_validation(self) -> bool:
        return bool(self.metric_lookup)


@dataclass(frozen=True)
class GatedMetricPrediction:
    """Per-metric gated prediction with explicit decision metadata."""

    metric: str
    selected_mode: str
    reason: str
    validation_status: str
    validation_level: str
    formula_only_prediction: float
    save_calibrated_prediction: float
    final_prediction: float
    sample_count: int | None
    improvement_pct: float | None


@dataclass(frozen=True)
class GatedEnginePrediction:
    """Engine prediction after applying a calibration policy."""

    predicted: EngineFormulaResult
    policy_mode: str
    metric_decisions: tuple[GatedMetricPrediction, ...]


@dataclass(frozen=True)
class GatedGearboxPrediction:
    """Gearbox prediction after applying a calibration policy."""

    predicted: SaveGearboxPrediction
    policy_mode: str
    metric_decisions: tuple[GatedMetricPrediction, ...]


def default_calibration_policy_dir() -> Path:
    return project_root_from_module() / "generated" / "calibration_policy"


def default_validation_dir() -> Path:
    return project_root_from_module() / "generated" / "validation"


def _metric_key(kind: str, metric: str) -> tuple[str, str]:
    return (kind, metric)


def _enabled_for_status(status: str) -> bool:
    return status == IMPROVED_STATUS


def _selected_mode_for_status(status: str) -> str:
    return "save_calibrated" if _enabled_for_status(status) else "formula_only"


def _reason_for_status(status: str, *, level: str) -> str:
    if status == IMPROVED_STATUS:
        return f"Holdout validation {level} status is improved; save calibration enabled."
    if status == "worse":
        return f"Holdout validation {level} status is worse; using formula-only prediction."
    if status == "unchanged":
        return f"Holdout validation {level} status is unchanged; using formula-only prediction."
    if status == "insufficient_data":
        return f"Holdout validation {level} has insufficient data; using formula-only prediction."
    return f"Unknown validation status {status!r}; using formula-only prediction."


def load_validation_metric_comparison(validation_dir: str | Path) -> pd.DataFrame:
    path = Path(validation_dir) / "validation_metric_comparison.csv"
    if not path.is_file():
        return pd.DataFrame()
    return pd.read_csv(path)


def load_validation_group_comparison(validation_dir: str | Path) -> pd.DataFrame:
    path = Path(validation_dir) / "validation_group_comparison.csv"
    if not path.is_file():
        return pd.DataFrame()
    return pd.read_csv(path)


def metric_policy_rows(metric_df: pd.DataFrame) -> list[MetricPolicyRow]:
    rows: list[MetricPolicyRow] = []
    if metric_df.empty:
        return rows
    for _, row in metric_df.iterrows():
        status = str(row.get("status", "insufficient_data"))
        rows.append(
            MetricPolicyRow(
                kind=str(row["kind"]),
                metric=str(row["metric"]),
                validation_status=status,
                calibration_enabled=_enabled_for_status(status),
                selected_mode=_selected_mode_for_status(status),
                reason=_reason_for_status(status, level="metric"),
                sample_count=int(row.get("sample_count", 0) or 0),
                improvement_pct=_float_or_none(row.get("improvement_pct")),
                formula_only_mae=_float_or_none(row.get("formula_only_mae")),
                save_calibrated_mae=_float_or_none(row.get("save_calibrated_mae")),
            )
        )
    return rows


def group_policy_rows(group_df: pd.DataFrame) -> list[GroupPolicyRow]:
    rows: list[GroupPolicyRow] = []
    if group_df.empty:
        return rows
    for _, row in group_df.iterrows():
        status = str(row.get("status", "insufficient_data"))
        formula_mae = _float_or_none(row.get("formula_only_mae"))
        abs_imp = _float_or_none(row.get("absolute_improvement"))
        improvement_pct = (
            (abs_imp / formula_mae * 100.0)
            if formula_mae and abs_imp is not None and formula_mae > 0
            else None
        )
        rows.append(
            GroupPolicyRow(
                kind=str(row["kind"]),
                metric=str(row["metric"]),
                year_band=str(row.get("year_band", "")),
                layout=_str_cell(row.get("layout", "")),
                fuel_type=_str_cell(row.get("fuel_type", "")),
                gearbox_type=_str_cell(row.get("gearbox_type", "")),
                validation_status=status,
                calibration_enabled=_enabled_for_status(status),
                selected_mode=_selected_mode_for_status(status),
                reason=_reason_for_status(status, level="group"),
                sample_count=int(row.get("sample_count", 0) or 0),
                improvement_pct=improvement_pct,
                formula_only_mae=formula_mae,
                save_calibrated_mae=_float_or_none(row.get("save_calibrated_mae")),
            )
        )
    return rows


def _float_or_none(value: object) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _str_cell(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _normalize_group_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    normalized = frame.copy()
    for col in ("year_band", "layout", "fuel_type", "gearbox_type"):
        if col in normalized.columns:
            normalized[col] = normalized[col].map(_str_cell)
    if "status" not in normalized.columns and "validation_status" in normalized.columns:
        normalized["status"] = normalized["validation_status"]
    return normalized


def build_calibration_policy(
    validation_dir: str | Path | None,
    *,
    mode: CalibrationPolicyMode | str = CalibrationPolicyMode.VALIDATION_GATED,
    min_group_samples: int = DEFAULT_MIN_GROUP_SAMPLES,
) -> CalibrationPolicy:
    """Build a calibration policy from holdout validation artifacts."""
    if isinstance(mode, str):
        mode = CalibrationPolicyMode(mode)

    if mode == CalibrationPolicyMode.ALWAYS_FORMULA_ONLY:
        return CalibrationPolicy.empty(mode=mode)

    if mode == CalibrationPolicyMode.ALWAYS_SAVE_CALIBRATED:
        return CalibrationPolicy(
            mode=mode,
            validation_dir=Path(validation_dir) if validation_dir is not None else None,
            min_group_samples=min_group_samples,
            metric_rows=(),
            group_rows=(),
            metric_lookup={},
            group_frame=pd.DataFrame(),
        )

    root = Path(validation_dir) if validation_dir is not None else default_validation_dir()
    metric_df = load_validation_metric_comparison(root)
    group_df = _normalize_group_frame(load_validation_group_comparison(root))
    metric_rows = metric_policy_rows(metric_df)
    group_rows = group_policy_rows(group_df)
    lookup = {_metric_key(row.kind, row.metric): row for row in metric_rows}
    return CalibrationPolicy(
        mode=mode,
        validation_dir=root if root.is_dir() else None,
        min_group_samples=min_group_samples,
        metric_rows=tuple(metric_rows),
        group_rows=tuple(group_rows),
        metric_lookup=lookup,
        group_frame=group_df,
    )


def load_calibration_policy(path: str | Path) -> CalibrationPolicy:
    """Load a serialized calibration policy JSON file."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    mode = CalibrationPolicyMode(payload.get("policy_mode", CalibrationPolicyMode.VALIDATION_GATED.value))
    min_group_samples = int(payload.get("min_group_samples", DEFAULT_MIN_GROUP_SAMPLES))
    validation_dir = payload.get("validation_dir")
    metric_rows = [
        MetricPolicyRow(
            kind=item["kind"],
            metric=item["metric"],
            validation_status=item["validation_status"],
            calibration_enabled=bool(item["calibration_enabled"]),
            selected_mode=item["selected_mode"],
            reason=item["reason"],
            sample_count=int(item.get("sample_count", 0)),
            improvement_pct=_float_or_none(item.get("improvement_pct")),
            formula_only_mae=_float_or_none(item.get("formula_only_mae")),
            save_calibrated_mae=_float_or_none(item.get("save_calibrated_mae")),
        )
        for item in payload.get("metrics", [])
    ]
    group_rows = [
        GroupPolicyRow(
            kind=item["kind"],
            metric=item["metric"],
            year_band=item.get("year_band", ""),
            layout=item.get("layout", ""),
            fuel_type=item.get("fuel_type", ""),
            gearbox_type=item.get("gearbox_type", ""),
            validation_status=item["validation_status"],
            calibration_enabled=bool(item["calibration_enabled"]),
            selected_mode=item["selected_mode"],
            reason=item["reason"],
            sample_count=int(item.get("sample_count", 0)),
            improvement_pct=_float_or_none(item.get("improvement_pct")),
            formula_only_mae=_float_or_none(item.get("formula_only_mae")),
            save_calibrated_mae=_float_or_none(item.get("save_calibrated_mae")),
        )
        for item in payload.get("groups", [])
    ]
    group_df = _normalize_group_frame(
        pd.DataFrame([row.__dict__ for row in group_rows]) if group_rows else pd.DataFrame()
    )
    return CalibrationPolicy(
        mode=mode,
        validation_dir=Path(validation_dir) if validation_dir else None,
        min_group_samples=min_group_samples,
        metric_rows=tuple(metric_rows),
        group_rows=tuple(group_rows),
        metric_lookup={_metric_key(row.kind, row.metric): row for row in metric_rows},
        group_frame=group_df,
    )


def export_calibration_policy(
    policy: CalibrationPolicy,
    output_dir: str | Path,
) -> dict[str, Path]:
    """Write calibration policy artifacts to disk."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    metrics_df = pd.DataFrame([row.__dict__ for row in policy.metric_rows])
    groups_df = pd.DataFrame([row.__dict__ for row in policy.group_rows])
    payload = {
        "version": 1,
        "policy_mode": policy.mode.value,
        "validation_dir": str(policy.validation_dir) if policy.validation_dir else None,
        "min_group_samples": policy.min_group_samples,
        "metrics_enabled": sum(1 for row in policy.metric_rows if row.calibration_enabled),
        "metrics_disabled": sum(1 for row in policy.metric_rows if not row.calibration_enabled),
        "metrics": [row.__dict__ for row in policy.metric_rows],
        "groups": [row.__dict__ for row in policy.group_rows],
    }
    paths = {
        "calibration_policy": out / "calibration_policy.json",
        "calibration_policy_metrics": out / "calibration_policy_metrics.csv",
    }
    paths["calibration_policy"].write_text(json.dumps(payload, indent=2), encoding="utf-8")
    metrics_df.to_csv(paths["calibration_policy_metrics"], index=False)
    if not groups_df.empty:
        group_path = out / "calibration_policy_groups.csv"
        groups_df.to_csv(group_path, index=False)
        paths["calibration_policy_groups"] = group_path
    return paths


def format_calibration_policy_summary(policy: CalibrationPolicy) -> list[str]:
    lines = [
        "Calibration policy",
        "=" * 72,
        f"Mode: {policy.mode.value}",
        f"Validation dir: {policy.validation_dir or '(none)'}",
        f"Metric rules: {len(policy.metric_rows)}",
        f"Group rules: {len(policy.group_rows)}",
        "",
        "Enabled metrics:",
    ]
    enabled = [row for row in policy.metric_rows if row.calibration_enabled]
    disabled = [row for row in policy.metric_rows if not row.calibration_enabled]
    if not enabled:
        lines.append("  (none)")
    else:
        for row in enabled:
            lines.append(
                f"  {row.kind} {row.metric}: {row.validation_status} "
                f"(n={row.sample_count}, improvement_pct={row.improvement_pct})"
            )
    lines.extend(["", "Formula-only metrics:"])
    if not disabled:
        lines.append("  (none)")
    else:
        for row in disabled:
            lines.append(f"  {row.kind} {row.metric}: {row.validation_status}")
    return lines


def _lookup_group_status(
    policy: CalibrationPolicy,
    *,
    kind: str,
    metric: str,
    year: object,
    layout: object,
    fuel_type: object,
    gearbox_type: object,
) -> tuple[str, str, int | None, float | None] | None:
    if policy.group_frame.empty:
        return None

    band = year_band(year)
    filters: list[dict[str, object]] = []
    if kind == "engine":
        filters.extend(
            [
                {
                    "year_band": band,
                    "layout": layout,
                    "fuel_type": fuel_type,
                    "gearbox_type": "",
                },
                {"year_band": band, "layout": layout, "fuel_type": "", "gearbox_type": ""},
                {"year_band": band, "layout": "", "fuel_type": "", "gearbox_type": ""},
            ]
        )
    else:
        filters.extend(
            [
                {"year_band": band, "layout": "", "fuel_type": "", "gearbox_type": gearbox_type},
                {"year_band": band, "layout": "", "fuel_type": "", "gearbox_type": ""},
            ]
        )

    for match in filters:
        frame = policy.group_frame
        frame = frame[(frame["kind"] == kind) & (frame["metric"] == metric)]
        frame = frame[frame["year_band"] == match["year_band"]]
        if match["layout"] != "":
            frame = frame[frame["layout"] == match["layout"]]
        else:
            frame = frame[frame["layout"].fillna("") == ""]
        if match["fuel_type"] != "":
            frame = frame[frame["fuel_type"] == match["fuel_type"]]
        else:
            frame = frame[frame["fuel_type"].fillna("") == ""]
        if match["gearbox_type"] != "":
            frame = frame[frame["gearbox_type"] == match["gearbox_type"]]
        else:
            frame = frame[frame["gearbox_type"].fillna("") == ""]

        if frame.empty:
            continue
        row = frame.iloc[0]
        sample_count = int(row.get("sample_count", 0) or 0)
        if sample_count < policy.min_group_samples:
            continue
        status = str(row.get("status", row.get("validation_status", "insufficient_data")))
        if "improvement_pct" in row and pd.notna(row.get("improvement_pct")):
            improvement_pct = _float_or_none(row.get("improvement_pct"))
        else:
            improvement = _float_or_none(row.get("absolute_improvement"))
            if improvement is not None and row.get("formula_only_mae"):
                formula_mae = float(row["formula_only_mae"])
                improvement_pct = (improvement / formula_mae * 100.0) if formula_mae > 0 else None
            else:
                improvement_pct = None
        return status, "group", sample_count, improvement_pct
    return None


def select_metric_prediction(
    policy: CalibrationPolicy,
    *,
    kind: str,
    metric: str,
    formula_only_value: float,
    save_calibrated_value: float,
    year: object | None = None,
    layout: object | None = None,
    fuel_type: object | None = None,
    gearbox_type: object | None = None,
) -> GatedMetricPrediction:
    """Choose formula-only or save-calibrated value for one metric."""
    if policy.mode == CalibrationPolicyMode.ALWAYS_FORMULA_ONLY:
        return GatedMetricPrediction(
            metric=metric,
            selected_mode="formula_only",
            reason="Policy mode is always_formula_only.",
            validation_status="n/a",
            validation_level="policy",
            formula_only_prediction=formula_only_value,
            save_calibrated_prediction=save_calibrated_value,
            final_prediction=formula_only_value,
            sample_count=None,
            improvement_pct=None,
        )

    if policy.mode == CalibrationPolicyMode.ALWAYS_SAVE_CALIBRATED:
        return GatedMetricPrediction(
            metric=metric,
            selected_mode="save_calibrated",
            reason="Policy mode is always_save_calibrated.",
            validation_status="n/a",
            validation_level="policy",
            formula_only_prediction=formula_only_value,
            save_calibrated_prediction=save_calibrated_value,
            final_prediction=save_calibrated_value,
            sample_count=None,
            improvement_pct=None,
        )

    status = "insufficient_data"
    level = "metric"
    sample_count: int | None = None
    improvement_pct: float | None = None
    reason = "Missing validation artifacts; defaulting to formula-only prediction."

    group_hit = None
    if year is not None:
        group_hit = _lookup_group_status(
            policy,
            kind=kind,
            metric=metric,
            year=year,
            layout=layout or "",
            fuel_type=fuel_type or "",
            gearbox_type=gearbox_type or "",
        )
    if group_hit is not None:
        status, level, sample_count, improvement_pct = group_hit
        reason = _reason_for_status(status, level=level)
    else:
        metric_row = policy.metric_lookup.get(_metric_key(kind, metric))
        if metric_row is not None:
            status = metric_row.validation_status
            sample_count = metric_row.sample_count
            improvement_pct = metric_row.improvement_pct
            reason = metric_row.reason
        elif not policy.has_validation:
            reason = "Missing validation artifacts; defaulting to formula-only prediction."

    use_calibrated = _enabled_for_status(status)
    return GatedMetricPrediction(
        metric=metric,
        selected_mode=_selected_mode_for_status(status),
        reason=reason,
        validation_status=status,
        validation_level=level,
        formula_only_prediction=formula_only_value,
        save_calibrated_prediction=save_calibrated_value,
        final_prediction=save_calibrated_value if use_calibrated else formula_only_value,
        sample_count=sample_count,
        improvement_pct=improvement_pct,
    )


def _engine_metric_fields(values: dict[str, float]) -> dict[str, float]:
    return {
        "length": values["length"],
        "width": values["width"],
        "weight": values["weight"],
        "torque": values["torque"],
        "horsepower": values["horsepower"],
        "performance_rating": values["power_rating"],
        "fuel_economy": values["fuel_rating"],
        "reliability_rating": values["reliability_rating"],
        "overall_rating": values["overall_rating"],
    }


def _gearbox_metric_fields(
    gearbox_prediction: SaveGearboxPrediction,
    values: dict[str, float],
) -> SaveGearboxPrediction:
    predicted = replace(
        gearbox_prediction.predicted,
        weight=values["weight"],
        power_rating=values["power_rating"],
        fuel_economy_rating=values["fuel_rating"],
        performance_rating=values["performance_rating"],
        reliability_rating=values["reliability_rating"],
        overall_rating=values["overall_rating"],
    )
    return replace(
        gearbox_prediction,
        predicted=predicted,
        max_torque_support=values["max_torque"],
    )


class GatedPredictionService:
    """Apply a calibration policy on top of deterministic prediction backends."""

    def __init__(
        self,
        policy: CalibrationPolicy,
        *,
        formula_backend: SavePredictionBackend | None = None,
        calibrated_backend: SavePredictionBackend | None = None,
    ) -> None:
        self.policy = policy
        self.formula_backend = formula_backend or SavePredictionBackend.formula_only()
        self.calibrated_backend = calibrated_backend or SavePredictionBackend.formula_only()

    @classmethod
    def from_policy(
        cls,
        policy: CalibrationPolicy,
        *,
        residual_store: ResidualCorrectionStore | None = None,
    ) -> GatedPredictionService:
        calibrated = SavePredictionBackend.holdout_calibrated(
            residual_store=residual_store or ResidualCorrectionStore()
        )
        if policy.mode == CalibrationPolicyMode.ALWAYS_SAVE_CALIBRATED:
            calibrated = SavePredictionBackend.save_calibrated()
        return cls(
            policy=policy,
            formula_backend=SavePredictionBackend.formula_only(),
            calibrated_backend=calibrated,
        )

    def predict_engine(
        self,
        record: SaveEngineRecord,
        layout: SaveLayoutComponent | None,
    ) -> GatedEnginePrediction:
        formula_pred = self.formula_backend.predict_engine(record, layout)
        calibrated_pred = self.calibrated_backend.predict_engine(record, layout)
        decisions: list[GatedMetricPrediction] = []
        values: dict[str, float] = {}
        for metric in engine_replay_metric_names():
            decision = select_metric_prediction(
                self.policy,
                kind="engine",
                metric=metric,
                formula_only_value=engine_predicted_value(formula_pred, metric),
                save_calibrated_value=engine_predicted_value(calibrated_pred, metric),
                year=record.year_built,
                layout=record.layout,
                fuel_type=record.fuel_type,
            )
            decisions.append(decision)
            values[metric] = decision.final_prediction
        predicted = replace(formula_pred.predicted, **_engine_metric_fields(values))
        return GatedEnginePrediction(
            predicted=predicted,
            policy_mode=self.policy.mode.value,
            metric_decisions=tuple(decisions),
        )

    def predict_gearbox(self, record: SaveGearboxRecord) -> GatedGearboxPrediction:
        formula_pred = self.formula_backend.predict_gearbox(record)
        calibrated_pred = self.calibrated_backend.predict_gearbox(record)
        decisions: list[GatedMetricPrediction] = []
        values: dict[str, float] = {}
        for metric in gearbox_replay_metric_names():
            decision = select_metric_prediction(
                self.policy,
                kind="gearbox",
                metric=metric,
                formula_only_value=gearbox_predicted_value(formula_pred, metric),
                save_calibrated_value=gearbox_predicted_value(calibrated_pred, metric),
                year=record.year_built,
                gearbox_type=record.gearbox_type,
            )
            decisions.append(decision)
            values[metric] = decision.final_prediction
        gated_gearbox = _gearbox_metric_fields(calibrated_pred, values)
        return GatedGearboxPrediction(
            predicted=gated_gearbox,
            policy_mode=self.policy.mode.value,
            metric_decisions=tuple(decisions),
        )
