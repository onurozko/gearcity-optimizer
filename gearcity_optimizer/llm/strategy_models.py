"""Structured models for LLM design strategy input and validation output."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from gearcity_optimizer.importers.component_choices import ComponentChoice

ValidationStatus = Literal["accepted", "rejected", "modified", "skipped"]


@dataclass(frozen=True)
class LLMComponentChoice:
    """One LLM-proposed component choice."""

    section: str
    choice_type: str
    recommended_choice: str
    alternatives: tuple[str, ...] = ()
    reason: str = ""
    confidence: str = "low"


@dataclass(frozen=True)
class LLMSliderGuidance:
    """High-level slider direction from the LLM (not exact values)."""

    section: str
    slider_label: str
    direction: str
    suggested_range: tuple[float, float] | None = None
    reason: str = ""


@dataclass(frozen=True)
class LLMDesignStrategy:
    """Structured strategy returned by the LLM."""

    component_choices: tuple[LLMComponentChoice, ...]
    slider_guidance: tuple[LLMSliderGuidance, ...]
    expected_tradeoffs: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    explanation: str = ""


@dataclass(frozen=True)
class ValidatedComponentChoice:
    """Validation result for one LLM component suggestion."""

    choice_type: str
    section: str
    llm_choice: str
    validation_status: ValidationStatus
    accepted_choice: ComponentChoice | None
    reason: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidatedSliderGuidance:
    """Validation result for one LLM slider guidance item."""

    section: str
    slider_label: str
    validation_status: ValidationStatus
    direction: str
    suggested_range: tuple[float, float] | None
    slider_key: str | None
    reason: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidatedLLMStrategyResult:
    """Validated LLM strategy ready for deterministic optimization."""

    strategy: LLMDesignStrategy | None
    component_validations: tuple[ValidatedComponentChoice, ...]
    slider_validations: tuple[ValidatedSliderGuidance, ...]
    accepted_choices: dict[str, ComponentChoice]
    accepted_slider_guidance: tuple[LLMSliderGuidance, ...]
    warnings: tuple[str, ...]
    validation_summary: str
    llm_available: bool
    llm_error: str | None = None
    backend_label: str = ""
    model_name: str = ""
