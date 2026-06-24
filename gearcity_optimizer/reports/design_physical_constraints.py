"""Hard physical fit checks for complete design scoring (torque, engine bay)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from gearcity_optimizer.formulas.chassis_formula import ChassisFormulaResult
from gearcity_optimizer.formulas.engine_formula import EngineFormulaResult
from gearcity_optimizer.formulas.gearbox_formula import GearboxFormulaResult


class _OutputLike(Protocol):
    output_key: str
    value: float


@dataclass(frozen=True)
class PhysicalFitAssessment:
    """Torque and engine-bay fit from wiki formula outputs."""

    engine_torque_lbft: float | None = None
    gearbox_max_torque_lbft: float | None = None
    torque_margin_ratio: float | None = None
    torque_ok: bool | None = None
    engine_length_in: float | None = None
    engine_width_in: float | None = None
    chassis_max_length_in: float | None = None
    chassis_max_width_in: float | None = None
    length_margin_ratio: float | None = None
    width_margin_ratio: float | None = None
    engine_bay_ok: bool | None = None
    violations: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    penalty: float = 0.0

    @property
    def has_violations(self) -> bool:
        return bool(self.violations)


def _output_value(
    predicted_outputs: Sequence[_OutputLike],
    *keys: str,
) -> float | None:
    normalized = {item.output_key: item.value for item in predicted_outputs}
    for key in keys:
        if key in normalized:
            return normalized[key]
    return None


def assess_physical_fit(
    *,
    engine: EngineFormulaResult | None = None,
    chassis: ChassisFormulaResult | None = None,
    gearbox: GearboxFormulaResult | None = None,
    predicted_outputs: Sequence[_OutputLike] | None = None,
) -> PhysicalFitAssessment:
    """Assess gearbox torque headroom and engine bay fit from formula results."""
    engine_torque = engine.torque if engine is not None else None
    gearbox_torque = gearbox.max_torque_support if gearbox is not None else None
    engine_length = engine.length if engine is not None else None
    engine_width = engine.width if engine is not None else None
    max_length = chassis.max_engine_length if chassis is not None else None
    max_width = chassis.max_engine_width if chassis is not None else None

    if predicted_outputs:
        engine_torque = engine_torque if engine_torque is not None else _output_value(
            predicted_outputs, "torque", "engine_torque_lbft"
        )
        gearbox_torque = gearbox_torque if gearbox_torque is not None else _output_value(
            predicted_outputs, "gearbox_torque_support", "gearbox_max_torque_lbft"
        )
        engine_length = engine_length if engine_length is not None else _output_value(
            predicted_outputs, "engine_length_in"
        )
        engine_width = engine_width if engine_width is not None else _output_value(
            predicted_outputs, "engine_width_in"
        )
        max_length = max_length if max_length is not None else _output_value(
            predicted_outputs, "chassis_max_engine_length_in"
        )
        max_width = max_width if max_width is not None else _output_value(
            predicted_outputs, "chassis_max_engine_width_in"
        )

    violations: list[str] = []
    warnings: list[str] = []
    penalty = 0.0

    torque_margin: float | None = None
    torque_ok: bool | None = None
    if engine_torque is not None and gearbox_torque is not None and engine_torque > 0:
        torque_margin = gearbox_torque / engine_torque
        torque_ok = torque_margin >= 1.0
        if not torque_ok:
            violations.append(
                f"Gearbox max torque support ({gearbox_torque:.0f} lb-ft) is below "
                f"predicted engine torque ({engine_torque:.0f} lb-ft)."
            )
            shortfall = 1.0 - torque_margin
            penalty += 20.0 + shortfall * 35.0
            if torque_margin < 0.5:
                penalty += 15.0
            if torque_margin < 0.25:
                penalty += 20.0
        elif torque_margin < 1.1:
            warnings.append(
                f"Gearbox torque margin is tight ({torque_margin:.0%} of engine torque)."
            )
            penalty += 2.0

    length_margin: float | None = None
    width_margin: float | None = None
    bay_ok: bool | None = None
    bay_known = False

    if engine_length is not None and max_length is not None and max_length > 0:
        bay_known = True
        length_margin = max_length / engine_length
        if engine_length > max_length:
            violations.append(
                f"Engine length ({engine_length:.1f} in) exceeds chassis bay "
                f"({max_length:.1f} in)."
            )
            penalty += 25.0 + min(20.0, (engine_length / max_length - 1.0) * 40.0)
        elif length_margin < 1.05:
            warnings.append(
                f"Engine length ({engine_length:.1f} in) is close to bay limit "
                f"({max_length:.1f} in)."
            )
            penalty += 3.0

    if engine_width is not None and max_width is not None and max_width > 0:
        bay_known = True
        width_margin = max_width / engine_width
        if engine_width > max_width:
            violations.append(
                f"Engine width ({engine_width:.1f} in) exceeds chassis bay "
                f"({max_width:.1f} in)."
            )
            penalty += 25.0 + min(20.0, (engine_width / max_width - 1.0) * 40.0)
        elif width_margin < 1.05:
            warnings.append(
                f"Engine width ({engine_width:.1f} in) is close to bay limit "
                f"({max_width:.1f} in)."
            )
            penalty += 3.0

    if bay_known:
        bay_ok = not any(
            "Engine length" in item or "Engine width" in item for item in violations
        )

    return PhysicalFitAssessment(
        engine_torque_lbft=engine_torque,
        gearbox_max_torque_lbft=gearbox_torque,
        torque_margin_ratio=torque_margin,
        torque_ok=torque_ok,
        engine_length_in=engine_length,
        engine_width_in=engine_width,
        chassis_max_length_in=max_length,
        chassis_max_width_in=max_width,
        length_margin_ratio=length_margin,
        width_margin_ratio=width_margin,
        engine_bay_ok=bay_ok,
        violations=tuple(violations),
        warnings=tuple(warnings),
        penalty=round(penalty, 2),
    )


def physical_fit_summary_lines(assessment: PhysicalFitAssessment) -> list[str]:
    """Human-readable lines for diagnostics UI."""
    lines: list[str] = []
    if assessment.engine_torque_lbft is not None and assessment.gearbox_max_torque_lbft is not None:
        margin_pct = (
            f"{assessment.torque_margin_ratio:.0%}"
            if assessment.torque_margin_ratio is not None
            else "n/a"
        )
        status = "OK" if assessment.torque_ok else "FAIL"
        lines.append(
            f"Torque margin: {margin_pct} "
            f"({assessment.gearbox_max_torque_lbft:.0f} / {assessment.engine_torque_lbft:.0f} lb-ft) [{status}]"
        )
    if assessment.engine_length_in is not None and assessment.chassis_max_length_in is not None:
        status = "OK" if (assessment.length_margin_ratio or 0) >= 1.0 else "FAIL"
        lines.append(
            f"Engine bay length: {assessment.engine_length_in:.1f} in engine vs "
            f"{assessment.chassis_max_length_in:.1f} in bay [{status}]"
        )
    if assessment.engine_width_in is not None and assessment.chassis_max_width_in is not None:
        status = "OK" if (assessment.width_margin_ratio or 0) >= 1.0 else "FAIL"
        lines.append(
            f"Engine bay width: {assessment.engine_width_in:.1f} in engine vs "
            f"{assessment.chassis_max_width_in:.1f} in bay [{status}]"
        )
    for warning in assessment.warnings:
        lines.append(f"NOTE: {warning}")
    for violation in assessment.violations:
        lines.append(f"ISSUE: {violation}")
    return lines
