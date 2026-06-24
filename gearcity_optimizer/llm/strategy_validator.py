"""Validate LLM strategies against Components.xml and wiki slider registry."""

from __future__ import annotations

from gearcity_optimizer.core.slider_registry import get_slider, list_sliders
from gearcity_optimizer.importers.component_choices import ComponentChoice
from gearcity_optimizer.llm.config import LLMConfig, LLM_NOT_CONFIGURED_MESSAGE, is_llm_configured
from gearcity_optimizer.llm.strategy_client import (
    llm_backend_label,
    request_llm_repair_strategy,
    request_llm_strategy,
)
from gearcity_optimizer.llm.strategy_context import build_design_strategy_context
from gearcity_optimizer.llm.strategy_repair import build_design_repair_context
from gearcity_optimizer.llm.strategy_models import (
    LLMDesignStrategy,
    LLMSliderGuidance,
    ValidatedComponentChoice,
    ValidatedLLMStrategyResult,
    ValidatedSliderGuidance,
)
from gearcity_optimizer.reports.component_choice_recommender import (
    ComponentChoiceRecommendationResult,
)
from gearcity_optimizer.reports.design_objective import DesignScore
from gearcity_optimizer.reports.design_physical_constraints import (
    assess_physical_fit,
)


def _normalize_name(name: str) -> str:
    return name.lower().replace(".dds", "").replace("_", "").replace(" ", "").strip()


def _match_available_choice(
    proposed: str,
    available: list[ComponentChoice],
    *,
    choice_type: str,
) -> ComponentChoice | None:
    if not proposed:
        return None
    normalized = _normalize_name(proposed)
    typed = [choice for choice in available if choice.choice_type == choice_type]
    for choice in typed:
        if _normalize_name(choice.display_name) == normalized:
            return choice
        if _normalize_name(choice.name) == normalized:
            return choice
    for choice in typed:
        display = _normalize_name(choice.display_name)
        if normalized in display or display in normalized:
            return choice
    return None


def _find_slider_by_label(label: str, section: str | None = None):
    normalized = label.strip().lower()
    for slider in list_sliders():
        if section and slider.section != section.strip().lower():
            continue
        if slider.label.strip().lower() == normalized:
            return slider
    for slider in list_sliders():
        if slider.label.strip().lower() == normalized:
            return slider
    return None


def validate_llm_strategy(
    strategy: LLMDesignStrategy,
    *,
    available_choices: list[ComponentChoice],
) -> tuple[
    tuple[ValidatedComponentChoice, ...],
    dict[str, ComponentChoice],
    tuple[str, ...],
]:
    """Validate LLM component suggestions against available catalog entries."""
    validations: list[ValidatedComponentChoice] = []
    accepted: dict[str, ComponentChoice] = {}
    warnings: list[str] = []

    for item in strategy.component_choices:
        matched = _match_available_choice(
            item.recommended_choice,
            available_choices,
            choice_type=item.choice_type,
        )
        if matched is None:
            status = "rejected"
            reason = (
                f"LLM choice {item.recommended_choice!r} is not available for "
                f"{item.choice_type} in the current year/skill setup."
            )
            warnings.append(reason)
            validations.append(
                ValidatedComponentChoice(
                    choice_type=item.choice_type,
                    section=item.section,
                    llm_choice=item.recommended_choice,
                    validation_status=status,
                    accepted_choice=None,
                    reason=reason,
                    warnings=(reason,),
                )
            )
            continue

        status = "accepted"
        reason = f"Validated against Components.xml: {matched.display_name}."
        accepted[item.choice_type] = matched
        validations.append(
            ValidatedComponentChoice(
                choice_type=item.choice_type,
                section=item.section,
                llm_choice=item.recommended_choice,
                validation_status=status,
                accepted_choice=matched,
                reason=reason,
            )
        )

    return tuple(validations), accepted, tuple(warnings)


def validate_llm_slider_guidance(
    strategy: LLMDesignStrategy,
) -> tuple[tuple[ValidatedSliderGuidance, ...], tuple[LLMSliderGuidance, ...], tuple[str, ...]]:
    """Validate LLM slider guidance against wiki-backed slider registry labels."""
    validations: list[ValidatedSliderGuidance] = []
    accepted: list[LLMSliderGuidance] = []
    warnings: list[str] = []

    for item in strategy.slider_guidance:
        slider = _find_slider_by_label(item.slider_label, item.section)
        if slider is None:
            reason = f"Unknown slider label from LLM: {item.slider_label!r}."
            warnings.append(reason)
            validations.append(
                ValidatedSliderGuidance(
                    section=item.section,
                    slider_label=item.slider_label,
                    validation_status="rejected",
                    direction=item.direction,
                    suggested_range=item.suggested_range,
                    slider_key=None,
                    reason=reason,
                    warnings=(reason,),
                )
            )
            continue

        direction = item.direction if item.direction in {"lower", "neutral", "higher"} else "neutral"
        status = "modified" if direction != item.direction else "accepted"
        reason = f"Validated slider label against wiki registry: {slider.label}."
        guidance = LLMSliderGuidance(
            section=slider.section,
            slider_label=slider.label,
            direction=direction,
            suggested_range=item.suggested_range,
            reason=item.reason,
        )
        accepted.append(guidance)
        validations.append(
            ValidatedSliderGuidance(
                section=slider.section,
                slider_label=slider.label,
                validation_status=status,
                direction=direction,
                suggested_range=item.suggested_range,
                slider_key=slider.key,
                reason=reason,
                warnings=() if status == "accepted" else (f"Adjusted direction to {direction}.",),
            )
        )

    return tuple(validations), tuple(accepted), tuple(warnings)


def run_llm_assisted_strategy(
    *,
    vehicle_type,
    cost_mode: str,
    year: int,
    skills: dict[str, float],
    available_choices: list[ComponentChoice],
    deterministic_result: ComponentChoiceRecommendationResult | None,
    deterministic_warnings: list[str] | None,
    config: LLMConfig,
    strategy: LLMDesignStrategy | None = None,
) -> ValidatedLLMStrategyResult:
    """Request (optional) and validate an LLM strategy."""
    if not is_llm_configured(config):
        return ValidatedLLMStrategyResult(
            strategy=None,
            component_validations=(),
            slider_validations=(),
            accepted_choices={},
            accepted_slider_guidance=(),
            warnings=(LLM_NOT_CONFIGURED_MESSAGE,),
            validation_summary="LLM-assisted mode is not configured.",
            llm_available=False,
            llm_error=LLM_NOT_CONFIGURED_MESSAGE,
        )

    context = build_design_strategy_context(
        vehicle_type=vehicle_type,
        cost_mode=cost_mode,
        year=year,
        skills=skills,
        available_choices=available_choices,
        deterministic_result=deterministic_result,
        deterministic_warnings=deterministic_warnings,
    )

    parsed = strategy
    llm_error: str | None = None
    if parsed is None:
        try:
            parsed = request_llm_strategy(context, config)
        except Exception as exc:  # noqa: BLE001
            llm_error = f"LLM strategy request failed: {exc}"
            return ValidatedLLMStrategyResult(
                strategy=None,
                component_validations=(),
                slider_validations=(),
                accepted_choices={},
                accepted_slider_guidance=(),
                warnings=(llm_error,),
                validation_summary="LLM strategy unavailable; deterministic fallback required.",
                llm_available=False,
                llm_error=llm_error,
                backend_label=llm_backend_label(config),
                model_name=config.model,
            )

    result = _validate_strategy_payload(parsed, available_choices=available_choices)
    return ValidatedLLMStrategyResult(
        strategy=result.strategy,
        component_validations=result.component_validations,
        slider_validations=result.slider_validations,
        accepted_choices=result.accepted_choices,
        accepted_slider_guidance=result.accepted_slider_guidance,
        warnings=result.warnings,
        validation_summary=result.validation_summary,
        llm_available=True,
        llm_error=llm_error,
        backend_label=llm_backend_label(config),
        model_name=config.model,
    )


def _validate_strategy_payload(
    parsed: LLMDesignStrategy,
    *,
    available_choices: list[ComponentChoice],
) -> ValidatedLLMStrategyResult:
    """Validate a parsed LLM strategy (shared by initial and repair passes)."""
    component_validations, accepted_choices, component_warnings = validate_llm_strategy(
        parsed,
        available_choices=available_choices,
    )
    slider_validations, accepted_guidance, slider_warnings = validate_llm_slider_guidance(parsed)
    warnings = list(component_warnings) + list(slider_warnings)
    accepted_count = sum(1 for item in component_validations if item.validation_status == "accepted")
    rejected_count = sum(1 for item in component_validations if item.validation_status == "rejected")
    summary = (
        "LLM suggested strategy. Deterministic validator "
        f"accepted {accepted_count} component choice(s), rejected {rejected_count}, "
        f"and validated {len(accepted_guidance)} slider guidance item(s)."
    )
    return ValidatedLLMStrategyResult(
        strategy=parsed,
        component_validations=component_validations,
        slider_validations=slider_validations,
        accepted_choices=accepted_choices,
        accepted_slider_guidance=accepted_guidance,
        warnings=tuple(warnings),
        validation_summary=summary,
        llm_available=True,
        llm_error=None,
        backend_label="",
        model_name="",
    )


def run_llm_design_repair(
    *,
    vehicle_type,
    cost_mode: str,
    year: int,
    skills: dict[str, float],
    available_choices: list[ComponentChoice],
    selected_choices: dict[str, ComponentChoice],
    design_score: DesignScore,
    config: LLMConfig,
    repair_attempt: int,
    max_attempts: int,
) -> ValidatedLLMStrategyResult:
    """Ask the LLM to revise a failed design strategy."""
    if not is_llm_configured(config):
        return ValidatedLLMStrategyResult(
            strategy=None,
            component_validations=(),
            slider_validations=(),
            accepted_choices={},
            accepted_slider_guidance=(),
            warnings=(LLM_NOT_CONFIGURED_MESSAGE,),
            validation_summary="LLM repair unavailable (not configured).",
            llm_available=False,
            llm_error=LLM_NOT_CONFIGURED_MESSAGE,
        )

    physical_fit = design_score.physical_fit or assess_physical_fit()
    context = build_design_repair_context(
        vehicle_type=vehicle_type,
        cost_mode=cost_mode,
        year=year,
        skills=skills,
        available_choices=available_choices,
        selected_choices=selected_choices,
        design_score=design_score,
        physical_fit=physical_fit,
        repair_attempt=repair_attempt,
        max_attempts=max_attempts,
    )

    try:
        parsed = request_llm_repair_strategy(context, config)
    except Exception as exc:  # noqa: BLE001
        message = f"LLM repair request failed: {exc}"
        return ValidatedLLMStrategyResult(
            strategy=None,
            component_validations=(),
            slider_validations=(),
            accepted_choices={},
            accepted_slider_guidance=(),
            warnings=(message,),
            validation_summary="LLM repair unavailable.",
            llm_available=False,
            llm_error=message,
            backend_label=llm_backend_label(config),
            model_name=config.model,
        )

    result = _validate_strategy_payload(parsed, available_choices=available_choices)
    repair_summary = (
        f"LLM repair attempt {repair_attempt}/{max_attempts}: "
        f"{len(result.accepted_choices)} component change(s), "
        f"{len(result.accepted_slider_guidance)} slider guidance item(s)."
    )
    return ValidatedLLMStrategyResult(
        strategy=result.strategy,
        component_validations=result.component_validations,
        slider_validations=result.slider_validations,
        accepted_choices=result.accepted_choices,
        accepted_slider_guidance=result.accepted_slider_guidance,
        warnings=result.warnings,
        validation_summary=repair_summary,
        llm_available=True,
        llm_error=None,
        backend_label=llm_backend_label(config),
        model_name=config.model,
    )
