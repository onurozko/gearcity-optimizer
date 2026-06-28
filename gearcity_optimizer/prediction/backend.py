"""Deterministic prediction backend for formula-only and save-calibrated replay."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal

from gearcity_optimizer.formulas.engine_formula import EngineFormulaResult, calculate_engine
from gearcity_optimizer.formulas.gearbox_formula import (
    GearboxFormulaInputs,
    GearboxFormulaResult,
    calculate_gearbox,
    normalize_save_gear_ratios,
    save_unset_gear_ratio_torque_bonus,
)
from gearcity_optimizer.importers.save_db import (
    SaveEngineRecord,
    SaveGearboxRecord,
    SaveLayoutComponent,
)
from gearcity_optimizer.reports.calibration_defaults import load_default_calibration_corrections
from gearcity_optimizer.reports.save_calibration import (
    _infer_gearbox_torque_slider,
    engine_formula_inputs_from_save,
    gearbox_formula_inputs_from_save,
)
from gearcity_optimizer.reports.save_calibration_corrections import (
    CalibrationCorrections,
    engine_segment_key,
    gearbox_segment_key,
)
from gearcity_optimizer.reports.save_dataset_residuals import (
    ResidualCorrectionStore,
    confidence_from_count,
    default_save_datasets_dir,
)


class PredictionMode(str, Enum):
    """Supported deterministic prediction modes."""

    FORMULA_ONLY = "formula_only"
    SAVE_CALIBRATED = "save_calibrated"


@dataclass(frozen=True)
class SaveEnginePrediction:
    """Engine formula replay with explicit calibration metadata."""

    predicted: EngineFormulaResult
    mode: str
    corrections_applied: bool
    matched_segment: str | None
    sample_count: int | None
    confidence: str | None
    correction_source: str | None


@dataclass(frozen=True)
class SaveGearboxPrediction:
    """Gearbox formula replay with explicit calibration metadata."""

    predicted: GearboxFormulaResult
    max_torque_support: float
    mode: str
    corrections_applied: bool
    matched_segment: str | None
    sample_count: int | None
    confidence: str | None
    correction_source: str | None
    inferred_torque_slider: float


class SavePredictionBackend:
    """Route save-design replay through formula-only or save-calibrated paths."""

    def __init__(
        self,
        mode: PredictionMode | Literal["formula_only", "save_calibrated"],
        *,
        corrections: CalibrationCorrections | None = None,
        residual_store: ResidualCorrectionStore | None = None,
    ) -> None:
        if isinstance(mode, str):
            mode = PredictionMode(mode)
        self.mode = mode
        self._corrections = corrections
        self._residual_store = residual_store

    @classmethod
    def formula_only(cls) -> SavePredictionBackend:
        """Replay wiki formulas without segment corrections."""
        return cls(PredictionMode.FORMULA_ONLY)

    @classmethod
    def save_calibrated(
        cls,
        *,
        corrections: CalibrationCorrections | None = None,
        datasets_dir: str | Path | None = None,
    ) -> SavePredictionBackend:
        """Replay with bundled segment corrections and optional residual lookup."""
        resolved = corrections if corrections is not None else load_default_calibration_corrections()
        residual_store = ResidualCorrectionStore.from_datasets_dir(
            datasets_dir if datasets_dir is not None else default_save_datasets_dir()
        )
        return cls(
            PredictionMode.SAVE_CALIBRATED,
            corrections=resolved,
            residual_store=residual_store,
        )

    @classmethod
    def holdout_calibrated(
        cls,
        *,
        residual_store: ResidualCorrectionStore,
    ) -> SavePredictionBackend:
        """Replay with train-only residual corrections and no bundled segment tables."""
        return cls(
            PredictionMode.SAVE_CALIBRATED,
            corrections=None,
            residual_store=residual_store,
        )

    @property
    def mode_label(self) -> str:
        return self.mode.value

    def predict_engine(
        self,
        record: SaveEngineRecord,
        layout: SaveLayoutComponent | None,
    ) -> SaveEnginePrediction:
        """Predict engine stats from save features without using actual targets."""
        from gearcity_optimizer.reports.save_formula_bridge import (
            apply_save_engine_physical_adjustments,
        )

        predicted = calculate_engine(engine_formula_inputs_from_save(record, layout))
        predicted = apply_save_engine_physical_adjustments(predicted, record)

        corrections_applied = False
        matched_segment: str | None = None
        sample_count: int | None = None
        confidence: str | None = None
        correction_source: str | None = None

        if self.mode == PredictionMode.SAVE_CALIBRATED and self._corrections is not None:
            correction = self._corrections.lookup_engine(record)
            if correction is not None:
                predicted = self._corrections.apply_engine(predicted, record)
                corrections_applied = True
                matched_segment = engine_segment_key(record, level=correction.level)
                sample_count = correction.count
                confidence = confidence_from_count(correction.count)
                correction_source = "bundled_segment"

        if (
            self.mode == PredictionMode.SAVE_CALIBRATED
            and self._residual_store is not None
            and self._residual_store.has_tables
        ):
            adjusted, lookup = self._residual_store.apply_engine_torque(
                predicted.torque,
                year=record.year_built,
                layout=record.layout,
                fuel_type=record.fuel_type,
            )
            if lookup.applied:
                from dataclasses import replace

                predicted = replace(predicted, torque=adjusted)
                corrections_applied = True
                matched_segment = lookup.matched_group or matched_segment
                sample_count = lookup.sample_count or sample_count
                confidence = lookup.confidence or confidence
                correction_source = lookup.correction_source or correction_source

        return SaveEnginePrediction(
            predicted=predicted,
            mode=self.mode_label,
            corrections_applied=corrections_applied,
            matched_segment=matched_segment,
            sample_count=sample_count,
            confidence=confidence,
            correction_source=correction_source,
        )

    def predict_gearbox(self, record: SaveGearboxRecord) -> SaveGearboxPrediction:
        """Predict gearbox stats from save features without using actual targets."""
        from dataclasses import replace

        from gearcity_optimizer.reports.save_formula_bridge import (
            save_gearbox_max_torque_multiplier,
        )

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
        else:
            inferred = _infer_gearbox_torque_slider(base, record.max_torque_input_lbft)

        predicted = calculate_gearbox(
            gearbox_formula_inputs_from_save(record, torque_max_input=inferred)
        )
        max_torque = predicted.max_torque_support + save_unset_gear_ratio_torque_bonus(
            record.low_ratio,
            record.high_ratio,
            record.year_built,
        )
        max_torque *= save_gearbox_max_torque_multiplier(record)

        corrections_applied = False
        matched_segment: str | None = None
        sample_count: int | None = None
        confidence: str | None = None
        correction_source: str | None = None

        if self.mode == PredictionMode.SAVE_CALIBRATED and self._corrections is not None:
            correction = self._corrections.lookup_gearbox(record)
            if correction is not None:
                max_torque = self._corrections.apply_gearbox_max_torque(max_torque, record)
                corrections_applied = True
                matched_segment = gearbox_segment_key(record, level=correction.level)
                sample_count = correction.count
                confidence = confidence_from_count(correction.count)
                correction_source = "bundled_segment"

        if (
            self.mode == PredictionMode.SAVE_CALIBRATED
            and self._residual_store is not None
            and self._residual_store.has_tables
        ):
            adjusted, lookup = self._residual_store.apply_gearbox_max_torque(
                max_torque,
                year=record.year_built,
                gearbox_type=record.gearbox_type,
            )
            if lookup.applied:
                max_torque = adjusted
                corrections_applied = True
                matched_segment = lookup.matched_group or matched_segment
                sample_count = lookup.sample_count or sample_count
                confidence = lookup.confidence or confidence
                correction_source = lookup.correction_source or correction_source

        return SaveGearboxPrediction(
            predicted=predicted,
            max_torque_support=max_torque,
            mode=self.mode_label,
            corrections_applied=corrections_applied,
            matched_segment=matched_segment,
            sample_count=sample_count,
            confidence=confidence,
            correction_source=correction_source,
            inferred_torque_slider=inferred,
        )
