"""Pandas-only residual correction analysis for save calibration datasets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from gearcity_optimizer.importers.wiki_downloader import project_root_from_module


DEFAULT_MIN_SEGMENT_COUNT = 3


def default_save_datasets_dir() -> Path:
    """Default output directory for generated save datasets."""
    return project_root_from_module() / "generated" / "save_datasets"


def year_band(year: object) -> str:
    """Bucket a build year into a decade band for grouped residuals."""
    try:
        value = int(year)
    except (TypeError, ValueError):
        return "unknown"
    if value < 1890:
        return "pre-1890"
    start = (value // 10) * 10
    return f"{start}-{start + 9}"


ENGINE_RESIDUAL_GROUP_COLS = ("metric", "year_band", "layout", "fuel_type")
GEARBOX_RESIDUAL_GROUP_COLS = ("metric", "year_band", "gearbox_type")

CONFIDENCE_LOW_MAX = 9
CONFIDENCE_MEDIUM_MAX = 29
RELIABLE_MEAN_PCT_ERROR = 10.0
WEAK_MEAN_PCT_ERROR = 20.0


def confidence_from_count(count: int | None) -> str | None:
    """Map sample count to correction confidence; None when count is too low."""
    if count is None or count < DEFAULT_MIN_SEGMENT_COUNT:
        return None
    if count <= CONFIDENCE_LOW_MAX:
        return "low"
    if count <= CONFIDENCE_MEDIUM_MAX:
        return "medium"
    return "high"


@dataclass(frozen=True)
class CorrectionLookupResult:
    """Metadata returned by a residual correction lookup."""

    applied: bool
    correction_value: float | None
    matched_group: str | None
    sample_count: int | None
    confidence: str | None
    correction_source: str | None = "residual_lookup"


class ResidualCorrectionStore:
    """Load grouped residual corrections once and answer lookup queries."""

    def __init__(
        self,
        engine_corrections: pd.DataFrame | None = None,
        gearbox_corrections: pd.DataFrame | None = None,
    ) -> None:
        self.engine_corrections = (
            engine_corrections.copy()
            if engine_corrections is not None
            else pd.DataFrame()
        )
        self.gearbox_corrections = (
            gearbox_corrections.copy()
            if gearbox_corrections is not None
            else pd.DataFrame()
        )
        if not self.engine_corrections.empty and "confidence" not in self.engine_corrections.columns:
            self.engine_corrections = annotate_correction_confidence(self.engine_corrections)
        if not self.gearbox_corrections.empty and "confidence" not in self.gearbox_corrections.columns:
            self.gearbox_corrections = annotate_correction_confidence(self.gearbox_corrections)

    @property
    def has_tables(self) -> bool:
        return not self.engine_corrections.empty or not self.gearbox_corrections.empty

    @classmethod
    def from_datasets_dir(cls, datasets_dir: str | Path) -> ResidualCorrectionStore:
        """Load residual correction CSVs when present; otherwise return an empty store."""

        def _read_csv_if_usable(path: Path) -> pd.DataFrame:
            if not path.is_file() or path.stat().st_size == 0:
                return pd.DataFrame()
            try:
                return pd.read_csv(path)
            except pd.errors.EmptyDataError:
                return pd.DataFrame()

        root = Path(datasets_dir)
        engine_df = _read_csv_if_usable(root / "engine_residual_corrections.csv")
        gearbox_df = _read_csv_if_usable(root / "gearbox_residual_corrections.csv")
        return cls(engine_df, gearbox_df)

    def lookup_engine(
        self,
        *,
        metric: str,
        year: object,
        layout: object,
        fuel_type: object,
    ) -> CorrectionLookupResult:
        return _lookup_correction_row(
            self.engine_corrections,
            metric=metric,
            year_band=year_band(year),
            layout=layout,
            fuel_type=fuel_type,
        )

    def lookup_gearbox(
        self,
        *,
        metric: str,
        year: object,
        gearbox_type: object,
    ) -> CorrectionLookupResult:
        return _lookup_correction_row(
            self.gearbox_corrections,
            metric=metric,
            year_band=year_band(year),
            gearbox_type=gearbox_type,
        )

    def apply_engine_torque(
        self,
        predicted_torque: float,
        *,
        year: object,
        layout: object,
        fuel_type: object,
    ) -> tuple[float, CorrectionLookupResult]:
        lookup = self.lookup_engine(
            metric="torque",
            year=year,
            layout=layout,
            fuel_type=fuel_type,
        )
        if not lookup.applied or lookup.correction_value is None:
            return predicted_torque, lookup
        return predicted_torque * lookup.correction_value, lookup

    def apply_gearbox_max_torque(
        self,
        predicted_max_torque: float,
        *,
        year: object,
        gearbox_type: object,
    ) -> tuple[float, CorrectionLookupResult]:
        lookup = self.lookup_gearbox(
            metric="max_torque",
            year=year,
            gearbox_type=gearbox_type,
        )
        if not lookup.applied or lookup.correction_value is None:
            return predicted_max_torque, lookup
        return predicted_max_torque * lookup.correction_value, lookup


def _format_matched_group(row: pd.Series) -> str:
    parts = [f"metric={row.get('metric')}", f"year_band={row.get('year_band')}"]
    if "layout" in row and str(row.get("layout", "")):
        parts.append(f"layout={row.get('layout')}")
    if "fuel_type" in row and str(row.get("fuel_type", "")):
        parts.append(f"fuel_type={row.get('fuel_type')}")
    if "gearbox_type" in row and str(row.get("gearbox_type", "")):
        parts.append(f"gearbox_type={row.get('gearbox_type')}")
    return "|".join(str(part) for part in parts)


def _lookup_correction_row(
    corrections: pd.DataFrame,
    *,
    metric: str,
    year_band: str,
    layout: object | None = None,
    fuel_type: object | None = None,
    gearbox_type: object | None = None,
) -> CorrectionLookupResult:
    if corrections.empty:
        return CorrectionLookupResult(
            applied=False,
            correction_value=None,
            matched_group=None,
            sample_count=None,
            confidence=None,
            correction_source=None,
        )

    frame = corrections[corrections["metric"] == metric]
    frame = frame[frame["year_band"] == year_band]
    if layout is not None and "layout" in frame.columns:
        frame = frame[frame["layout"] == layout]
    if fuel_type is not None and "fuel_type" in frame.columns:
        frame = frame[frame["fuel_type"] == fuel_type]
    if gearbox_type is not None and "gearbox_type" in frame.columns:
        frame = frame[frame["gearbox_type"] == gearbox_type]

    if frame.empty:
        return CorrectionLookupResult(
            applied=False,
            correction_value=None,
            matched_group=None,
            sample_count=None,
            confidence=None,
            correction_source=None,
        )

    row = frame.iloc[0]
    count = int(row.get("count", 0))
    confidence = row.get("confidence")
    if confidence is None or (isinstance(confidence, float) and pd.isna(confidence)):
        confidence = confidence_from_count(count)
    if count < DEFAULT_MIN_SEGMENT_COUNT or confidence is None:
        return CorrectionLookupResult(
            applied=False,
            correction_value=None,
            matched_group=_format_matched_group(row),
            sample_count=count,
            confidence=None,
            correction_source="residual_lookup",
        )

    scale = float(row.get("suggested_scale", 1.0))
    return CorrectionLookupResult(
        applied=True,
        correction_value=scale,
        matched_group=_format_matched_group(row),
        sample_count=count,
        confidence=str(confidence),
        correction_source="residual_lookup",
    )


def annotate_correction_confidence(corrections: pd.DataFrame) -> pd.DataFrame:
    """Add confidence labels to a residual correction table."""
    if corrections.empty:
        return corrections.copy()
    annotated = corrections.copy()
    annotated["confidence"] = annotated["count"].apply(
        lambda value: confidence_from_count(int(value))
    )
    return annotated


@dataclass(frozen=True)
class ResidualCorrectionRow:
    """One grouped mean residual suitable for optional lookup."""

    kind: str
    metric: str
    year_band: str
    layout: str
    fuel_type: str
    gearbox_type: str
    count: int
    mean_signed_pct: float
    mean_abs_pct: float


def metric_replay_columns(prefix: str) -> tuple[str, str, str, str]:
    return (
        f"actual_{prefix}",
        f"predicted_{prefix}",
        f"error_{prefix}",
        f"pct_error_{prefix}",
    )


def engine_replay_metric_names() -> tuple[str, ...]:
    return (
        "length",
        "width",
        "weight",
        "torque",
        "horsepower",
        "power_rating",
        "fuel_rating",
        "reliability_rating",
        "overall_rating",
    )


def gearbox_replay_metric_names() -> tuple[str, ...]:
    return (
        "max_torque",
        "weight",
        "power_rating",
        "fuel_rating",
        "performance_rating",
        "reliability_rating",
        "overall_rating",
    )


def _engine_metric_map() -> dict[str, str]:
    return {
        "length": "length_in",
        "width": "width_in",
        "weight": "weight_lb",
        "torque": "torque_lbft",
        "horsepower": "horsepower",
        "power_rating": "engine_power_rating",
        "fuel_rating": "engine_fuel_rating",
        "reliability_rating": "engine_reliability_rating",
        "overall_rating": "overall_rating",
    }


def _gearbox_metric_map() -> dict[str, str]:
    return {
        "max_torque": "max_torque_lbft",
        "weight": "weight_lb",
        "power_rating": "power_rating",
        "fuel_rating": "fuel_rating",
        "performance_rating": "performance_rating",
        "reliability_rating": "reliability_rating",
        "overall_rating": "overall_rating",
    }


def signed_pct(actual: float, predicted: float) -> float:
    if abs(predicted) <= 1e-9:
        return 0.0
    return (actual - predicted) / abs(predicted) * 100.0


def build_engine_residual_long(engine_df: pd.DataFrame) -> pd.DataFrame:
    """Expand engine replay columns into one row per metric for residual grouping."""
    if engine_df.empty:
        return pd.DataFrame(
            columns=[
                "save",
                "design_id",
                "metric",
                "year_band",
                "layout",
                "fuel_type",
                "signed_pct",
                "abs_pct",
            ]
        )

    rows: list[dict[str, object]] = []
    for _, row in engine_df.iterrows():
        band = year_band(row.get("year"))
        for prefix in engine_replay_metric_names():
            actual_col, predicted_col, _, pct_col = metric_replay_columns(prefix)
            if actual_col not in engine_df.columns or predicted_col not in engine_df.columns:
                continue
            actual = row.get(actual_col)
            predicted = row.get(predicted_col)
            if pd.isna(actual) or pd.isna(predicted):
                continue
            signed = row.get(f"signed_{prefix}_pct")
            if signed is None or pd.isna(signed):
                signed = signed_pct(float(actual), float(predicted))
            abs_pct = row.get(pct_col)
            if abs_pct is None or pd.isna(abs_pct):
                abs_pct = abs(float(signed))
            rows.append(
                {
                    "save": row.get("save"),
                    "design_id": row.get("design_id"),
                    "metric": prefix,
                    "year_band": band,
                    "layout": row.get("layout"),
                    "fuel_type": row.get("fuel_type"),
                    "signed_pct": float(signed),
                    "abs_pct": float(abs_pct),
                }
            )
    return pd.DataFrame(rows)


def build_gearbox_residual_long(gearbox_df: pd.DataFrame) -> pd.DataFrame:
    """Expand gearbox replay columns into one row per metric for residual grouping."""
    if gearbox_df.empty:
        return pd.DataFrame(
            columns=[
                "save",
                "design_id",
                "metric",
                "year_band",
                "gearbox_type",
                "signed_pct",
                "abs_pct",
            ]
        )

    rows: list[dict[str, object]] = []
    for _, row in gearbox_df.iterrows():
        band = year_band(row.get("year"))
        for prefix in gearbox_replay_metric_names():
            actual_col, predicted_col, _, pct_col = metric_replay_columns(prefix)
            if actual_col not in gearbox_df.columns or predicted_col not in gearbox_df.columns:
                continue
            actual = row.get(actual_col)
            predicted = row.get(predicted_col)
            if pd.isna(actual) or pd.isna(predicted):
                continue
            signed = row.get(f"signed_{prefix}_pct")
            if signed is None or pd.isna(signed):
                signed = signed_pct(float(actual), float(predicted))
            abs_pct = row.get(pct_col)
            if abs_pct is None or pd.isna(abs_pct):
                abs_pct = abs(float(signed))
            rows.append(
                {
                    "save": row.get("save"),
                    "design_id": row.get("design_id"),
                    "metric": prefix,
                    "year_band": band,
                    "gearbox_type": row.get("gearbox_type"),
                    "signed_pct": float(signed),
                    "abs_pct": float(abs_pct),
                }
            )
    return pd.DataFrame(rows)


def grouped_residual_corrections(
    long_df: pd.DataFrame,
    *,
    kind: str,
    group_cols: tuple[str, ...],
    min_count: int = DEFAULT_MIN_SEGMENT_COUNT,
    min_abs_signed_pct: float = 3.0,
) -> pd.DataFrame:
    """Compute grouped mean residuals; only keep segments with enough rows."""
    if long_df.empty:
        return pd.DataFrame(
            columns=[
                "kind",
                "metric",
                "year_band",
                "layout",
                "fuel_type",
                "gearbox_type",
                "count",
                "mean_signed_pct",
                "mean_abs_pct",
                "suggested_scale",
            ]
        )

    grouped = (
        long_df.groupby(list(group_cols), dropna=False)
        .agg(
            count=("signed_pct", "count"),
            mean_signed_pct=("signed_pct", "mean"),
            mean_abs_pct=("abs_pct", "mean"),
        )
        .reset_index()
    )
    grouped = grouped[
        (grouped["count"] >= min_count)
        & (grouped["mean_signed_pct"].abs() >= min_abs_signed_pct)
    ].copy()
    grouped["kind"] = kind
    grouped["suggested_scale"] = 1.0 / (1.0 + grouped["mean_signed_pct"] / 100.0)
    grouped["confidence"] = grouped["count"].apply(
        lambda value: confidence_from_count(int(value))
    )
    for col in ("layout", "fuel_type", "gearbox_type"):
        if col not in grouped.columns:
            grouped[col] = ""
    return grouped.sort_values("mean_abs_pct", ascending=False)


def build_residual_correction_tables(
    engine_df: pd.DataFrame,
    gearbox_df: pd.DataFrame,
    *,
    min_count: int = DEFAULT_MIN_SEGMENT_COUNT,
    min_abs_signed_pct: float = 3.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build optional engine and gearbox residual correction lookup tables."""
    engine_long = build_engine_residual_long(engine_df)
    gearbox_long = build_gearbox_residual_long(gearbox_df)
    engine_corr = grouped_residual_corrections(
        engine_long,
        kind="engine",
        group_cols=ENGINE_RESIDUAL_GROUP_COLS,
        min_count=min_count,
        min_abs_signed_pct=min_abs_signed_pct,
    )
    gearbox_corr = grouped_residual_corrections(
        gearbox_long,
        kind="gearbox",
        group_cols=GEARBOX_RESIDUAL_GROUP_COLS,
        min_count=min_count,
        min_abs_signed_pct=min_abs_signed_pct,
    )
    return engine_corr, gearbox_corr


def lookup_engine_correction_scale(
    corrections: pd.DataFrame,
    *,
    metric: str,
    year: object,
    layout: object,
    fuel_type: object,
) -> float | None:
    """Return a multiplicative scale when a segment has enough residual evidence."""
    lookup = ResidualCorrectionStore(engine_corrections=corrections).lookup_engine(
        metric=metric,
        year=year,
        layout=layout,
        fuel_type=fuel_type,
    )
    return lookup.correction_value if lookup.applied else None


def lookup_gearbox_correction_scale(
    corrections: pd.DataFrame,
    *,
    metric: str,
    year: object,
    gearbox_type: object,
) -> float | None:
    """Return a multiplicative scale when a segment has enough residual evidence."""
    lookup = ResidualCorrectionStore(gearbox_corrections=corrections).lookup_gearbox(
        metric=metric,
        year=year,
        gearbox_type=gearbox_type,
    )
    return lookup.correction_value if lookup.applied else None


def export_residual_corrections(
    engine_corr: pd.DataFrame,
    gearbox_corr: pd.DataFrame,
    output_dir: str | Path,
) -> dict[str, Path]:
    """Write residual correction tables to CSV."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "engine_residual_corrections": out / "engine_residual_corrections.csv",
        "gearbox_residual_corrections": out / "gearbox_residual_corrections.csv",
    }
    engine_corr.to_csv(paths["engine_residual_corrections"], index=False)
    gearbox_corr.to_csv(paths["gearbox_residual_corrections"], index=False)
    return paths


def build_actual_vs_predicted_chart_data(
    engine_df: pd.DataFrame,
    gearbox_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build CSV-friendly actual-vs-predicted rows for charting."""
    rows: list[dict[str, object]] = []

    def _append_rows(df: pd.DataFrame, kind: str, metrics: tuple[str, ...]) -> None:
        if df.empty:
            return
        for _, row in df.iterrows():
            band = year_band(row.get("year"))
            for prefix in metrics:
                actual_col, predicted_col, error_col, pct_col = metric_replay_columns(prefix)
                if actual_col not in df.columns or predicted_col not in df.columns:
                    continue
                actual = row.get(actual_col)
                predicted = row.get(predicted_col)
                if pd.isna(actual) or pd.isna(predicted):
                    continue
                group_labels = {
                    "year_band": band,
                    "layout": row.get("layout", ""),
                    "fuel_type": row.get("fuel_type", ""),
                    "gearbox_type": row.get("gearbox_type", ""),
                }
                rows.append(
                    {
                        "save": row.get("save"),
                        "kind": kind,
                        "design_id": row.get("design_id"),
                        "name": row.get("name"),
                        "metric": prefix,
                        "actual": float(actual),
                        "predicted": float(predicted),
                        "error": float(row.get(error_col, abs(float(actual) - float(predicted)))),
                        "pct_error": float(row.get(pct_col, 0.0)),
                        "year_band": band,
                        "layout": group_labels["layout"],
                        "fuel_type": group_labels["fuel_type"],
                        "gearbox_type": group_labels["gearbox_type"],
                        "group_label": "|".join(
                            f"{key}={value}"
                            for key, value in group_labels.items()
                            if value not in (None, "", "nan")
                        ),
                    }
                )

    _append_rows(engine_df, "engine", engine_replay_metric_names())
    _append_rows(gearbox_df, "gearbox", gearbox_replay_metric_names())

    if not rows:
        return pd.DataFrame(
            columns=[
                "save",
                "kind",
                "design_id",
                "name",
                "metric",
                "actual",
                "predicted",
                "error",
                "pct_error",
                "year_band",
                "layout",
                "fuel_type",
                "gearbox_type",
                "group_label",
            ]
        )
    return pd.DataFrame(rows)


def worst_prediction_gaps(
    engine_df: pd.DataFrame,
    gearbox_df: pd.DataFrame,
    *,
    top_n: int = 10,
) -> pd.DataFrame:
    """Return the largest pct-error replay metrics across engines and gearboxes."""
    parts: list[pd.DataFrame] = []
    for df, kind in ((engine_df, "engine"), (gearbox_df, "gearbox")):
        if df.empty:
            continue
        metrics = (
            engine_replay_metric_names()
            if kind == "engine"
            else gearbox_replay_metric_names()
        )
        for prefix in metrics:
            pct_col = f"pct_error_{prefix}"
            if pct_col not in df.columns:
                continue
            subset = df[["save", "design_id", "name", "year", pct_col]].copy()
            subset = subset.rename(columns={pct_col: "pct_error"})
            subset["kind"] = kind
            subset["metric"] = prefix
            parts.append(subset)
    if not parts:
        return pd.DataFrame(
            columns=["save", "design_id", "name", "year", "kind", "metric", "pct_error"]
        )
    merged = pd.concat(parts, ignore_index=True)
    merged["pct_error"] = pd.to_numeric(merged["pct_error"], errors="coerce")
    merged = merged.dropna(subset=["pct_error"])
    return merged.sort_values("pct_error", ascending=False).head(top_n)


def formula_error_summary(
    engine_df: pd.DataFrame,
    gearbox_df: pd.DataFrame,
) -> pd.DataFrame:
    """Summarize mean pct error per replay metric."""
    rows: list[dict[str, Any]] = []
    for df, kind, metrics in (
        (engine_df, "engine", engine_replay_metric_names()),
        (gearbox_df, "gearbox", gearbox_replay_metric_names()),
    ):
        if df.empty:
            continue
        for prefix in metrics:
            pct_col = f"pct_error_{prefix}"
            if pct_col not in df.columns:
                continue
            series = pd.to_numeric(df[pct_col], errors="coerce").dropna()
            if series.empty:
                continue
            rows.append(
                {
                    "kind": kind,
                    "metric": prefix,
                    "count": int(series.count()),
                    "mean_pct_error": float(series.mean()),
                    "median_pct_error": float(series.median()),
                    "max_pct_error": float(series.max()),
                }
            )
    return pd.DataFrame(rows)
