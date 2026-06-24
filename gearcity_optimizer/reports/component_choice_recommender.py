"""Recommend discrete component/dropdown choices from Components.xml."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from gearcity_optimizer.core.component_priorities import get_adjusted_vehicle_weights
from gearcity_optimizer.core.component_vehicle_groups import (
    LUXURY_LAYOUT_TOKENS,
    PASSENGER_GROUPS,
    PERFORMANCE_LAYOUT_TOKENS,
    classify_vehicle_group,
    is_mainstream_layout,
    is_primitive_layout,
    is_primitive_valvetrain,
    is_specialty_layout,
)
from gearcity_optimizer.core.cost_mode import CostMode, parse_cost_mode
from gearcity_optimizer.core.models import VehicleType
from gearcity_optimizer.importers.component_choices import (
    ComponentChoice,
    choice_type_label,
)
from gearcity_optimizer.core.wiki_component_compatibility import (
    is_valid_partial_choices,
    validate_component_choices,
)
from gearcity_optimizer.reports.part_recommender import is_work_or_utility_focused

ComponentChoiceMode = Literal["auto", "manual"]

ENGINE_CHOICE_TYPES = (
    "engine_layout",
    "cylinder_count",
    "fuel_type",
    "valvetrain",
    "forced_induction",
    "transverse_engine",
)
CHASSIS_CHOICE_TYPES = (
    "frame",
    "suspension_front",
    "suspension_rear",
    "suspension",
    "drivetrain",
)
GEARBOX_CHOICE_TYPES = ("gearbox_type", "gear_count", "overdrive")

STAT_WEIGHTS: dict[str, tuple[str, float]] = {
    "performance": ("performance", 1.0),
    "performancerating": ("performance", 1.0),
    "reliability": ("dependability", 1.0),
    "reliabilityrating": ("dependability", 1.0),
    "smoothness": ("luxury", 0.9),
    "smoothnessrating": ("luxury", 0.9),
    "comfort": ("luxury", 0.8),
    "comfortrating": ("luxury", 0.8),
    "fueleconomy": ("fuel", 1.0),
    "fueleconomyrating": ("fuel", 1.0),
    "fuel": ("fuel", 0.8),
    "power": ("power", 1.0),
    "torque": ("power", 0.9),
    "weight": ("fuel", -0.35),
    "cost": ("dependability", -0.25),
    "complexity": ("dependability", -0.35),
    "manufacturing": ("dependability", -0.2),
    "design": ("performance", 0.15),
}

AUTO_PICK_MIN_SCORE = 58.0
AUTO_PICK_MIN_GAP = 10.0
AUTO_PICK_RECOMMENDED_MIN_SCORE = 70.0
AUTO_PICK_USABLE_MIN_SCORE = 50.0
AUTO_PICK_NOT_RECOMMENDED_MAX_SCORE = 35.0

AutoPickStatus = Literal[
    "recommended",
    "usable_candidate",
    "low_confidence_candidate",
    "not_recommended",
    "manual",
    "none",
]

EXPERIMENTAL_DISCLAIMER = (
    "Experimental: automatic component choice scoring is still being validated. "
    "Review alternatives before copying the setup into GearCity."
)
NO_RELIABLE_AUTO_PICK_WARNING = (
    "No reliable auto-pick found for this choice type. Select manually or inspect alternatives."
)
LOW_CONFIDENCE_PAGE_WARNING = (
    "Some automatic component choices are low-confidence. Review alternatives or switch to "
    "Manual component selection."
)

AUTO_PICK_STATUS_LABELS: dict[str, str] = {
    "recommended": "Recommended",
    "usable_candidate": "Usable candidate",
    "low_confidence_candidate": "No reliable recommendation",
    "not_recommended": "No reliable recommendation",
    "manual": "Manual selection",
    "none": "No candidate",
}


@dataclass(frozen=True)
class ComponentSuitabilityScore:
    """Suitability breakdown for one component candidate."""

    component_name: str
    section: str
    choice_type: str
    total_score: float
    availability_score: float
    vehicle_fit_score: float
    cost_mode_score: float
    era_score: float
    stat_score: float
    penalties: list[str]
    reasons: list[str]
    confidence: str
    choice: ComponentChoice


@dataclass(frozen=True)
class ChoiceRecommendation:
    """Ranked component candidates for one choice type."""

    section: str
    choice_type: str
    recommended_choice: ComponentChoice | None
    alternatives: list[ComponentChoice]
    candidates: list[ComponentSuitabilityScore]
    reason: str
    confidence: str
    auto_pick_enabled: bool = False
    auto_pick_status: AutoPickStatus = "none"
    top_candidate: ComponentChoice | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ComponentChoiceRecommendationResult:
    """All component choice candidates for a design setup."""

    vehicle_type_name: str
    year: int
    cost_mode: str
    choices: list[ChoiceRecommendation]
    auto_pick_validated: bool = False
    warnings: list[str] = field(default_factory=list)


def _stat_score(
    choice: ComponentChoice,
    *,
    vehicle_type: VehicleType,
) -> tuple[float, bool]:
    weights = get_adjusted_vehicle_weights(vehicle_type)
    if not choice.stats:
        return 0.0, False

    score = 0.0
    used = 0
    for stat_key, stat_value in choice.stats.items():
        mapping = STAT_WEIGHTS.get(stat_key)
        if mapping is None:
            continue
        weight_key, multiplier = mapping
        vehicle_weight = weights.get(weight_key, 0.0)
        if vehicle_weight <= 0.0:
            continue
        score += stat_value * vehicle_weight * multiplier
        used += 1
    if used == 0:
        return 0.0, False
    return min(max(score / used, 0.0), 100.0), True


def _era_score(
    choice: ComponentChoice,
    *,
    year: int,
    candidates: list[ComponentChoice],
) -> tuple[float, list[str], list[str]]:
    if choice.choice_type in {"gear_count", "overdrive"}:
        return 70.0, [], ["mechanical gearbox option; era fit de-emphasized"]

    reasons: list[str] = []
    penalties: list[str] = []
    start = choice.start_year or 1850
    age = max(0, year - start)
    newest_start = max((item.start_year or 1850) for item in candidates)
    relative_age = max(0, year - newest_start)

    if age <= relative_age + 5:
        score = 90.0 - relative_age * 2.0
        reasons.append("recent era choice for selected year")
    elif age <= relative_age + 20:
        score = 65.0 - (age - relative_age) * 0.8
        reasons.append("older but still plausible for selected year")
    else:
        score = 35.0 - min(age - relative_age, 40) * 0.5
        penalties.append("obsolete for selected year when newer options exist")
        reasons.append("older unlock year than other available options")

    if start < year - 35 and any((item.start_year or 0) >= year - 15 for item in candidates if item.id != choice.id):
        score -= 25.0
        penalties.append("superseded by newer available options")

    return max(score, 0.0), penalties, reasons


def _vehicle_fit_score(
    choice: ComponentChoice,
    *,
    vehicle_type: VehicleType,
    vehicle_group: str,
    candidates: list[ComponentChoice],
    cost_mode: CostMode,
    year: int,
) -> tuple[float, list[str], list[str]]:
    penalties: list[str] = []
    reasons: list[str] = []
    name = choice.display_name.lower()
    score = 55.0

    if choice.choice_type == "engine_layout":
        if is_primitive_layout(name):
            score -= 35.0
            penalties.append("primitive/small layout")
            if vehicle_group in PASSENGER_GROUPS:
                penalties.append("poor passenger car fit")
            if any(is_mainstream_layout(item.display_name) for item in candidates if item.id != choice.id):
                penalties.append("obsolete/poor sedan fit")
                score -= 20.0
            if (
                vehicle_group in PASSENGER_GROUPS
                and cost_mode in {CostMode.BALANCED, CostMode.LUXURY}
                and any(is_mainstream_layout(item.display_name) for item in candidates if item.id != choice.id)
            ):
                score -= 25.0
                penalties.append("primitive layout unsuitable for balanced/luxury passenger vehicle")
        elif is_mainstream_layout(name):
            score += 20.0
            reasons.append("mainstream balanced passenger layout")
        elif is_specialty_layout(name):
            score -= 15.0
            penalties.append("specialty layout")
            if vehicle_group in PASSENGER_GROUPS and not is_work_or_utility_focused(vehicle_type):
                penalties.append("specialty layout for passenger vehicle")
                score -= 10.0

        if vehicle_group == "sport_performance" and any(token in name for token in PERFORMANCE_LAYOUT_TOKENS):
            score += 12.0
            reasons.append("performance-oriented layout")
        if vehicle_group == "luxury_passenger" and any(token in name for token in LUXURY_LAYOUT_TOKENS):
            score += 10.0
            reasons.append("refinement-friendly layout")

    if choice.choice_type == "valvetrain" and is_primitive_valvetrain(name):
        score -= 30.0
        penalties.append("primitive valvetrain")
        if vehicle_group in PASSENGER_GROUPS:
            penalties.append("poor passenger car valvetrain fit")
        if any(
            not is_primitive_valvetrain(item.display_name)
            for item in candidates
            if item.id != choice.id
        ):
            score -= 25.0
            penalties.append("superseded by normal valvetrain options")

    if choice.choice_type == "forced_induction":
        weights = get_adjusted_vehicle_weights(vehicle_type)
        if "supercharg" in name or "turbo" in name:
            if weights.get("performance", 0.0) < 0.55:
                score -= 20.0
                penalties.append("forced induction for non-performance vehicle")
            else:
                score += 8.0
                reasons.append("performance boost where priorities support it")

    if choice.choice_type == "fuel_type" and "diesel" in name:
        weights = get_adjusted_vehicle_weights(vehicle_type)
        if weights.get("fuel", 0.0) >= 0.55:
            score += 8.0
            reasons.append("fuel economy oriented fuel type")
        if vehicle_group in PASSENGER_GROUPS and weights.get("luxury", 0.0) >= 0.6:
            score -= 8.0
            penalties.append("diesel less suited to luxury passenger focus")

    if is_work_or_utility_focused(vehicle_type):
        if any(token in name for token in ("truck", "utility", "torque", "heavy", "manual", "diesel")):
            score += 10.0
            reasons.append("utility/work-oriented component")

    if choice.choice_type == "gear_count":
        from gearcity_optimizer.core.wiki_component_compatibility import parse_gear_count

        gears = parse_gear_count(choice)
        score = 48.0
        if gears is not None:
            score += min(gears, 8) * 7.0
            reasons.append(
                f"{gears}-speed adds ~{gears * 10} lb-ft base gearbox torque capacity"
            )
            weights = get_adjusted_vehicle_weights(vehicle_type)
            if weights.get("performance", 0.0) >= 0.40:
                score += min(gears, 6) * 2.0
            if weights.get("fuel", 0.0) >= 0.50:
                score += min(gears, 6) * 1.5
                reasons.append("extra gears spread ratios for fuel economy")
            if weights.get("dependability", 0.0) >= 0.45 and gears is not None and gears >= 4:
                score += 4.0
                reasons.append("moderate gearing suits dependability focus")
        if cost_mode is CostMode.CHEAP:
            if gears is not None and gears >= 5:
                score -= 18.0
                penalties.append("many gears raise cost/complexity in cheap mode")
            elif gears is not None and gears >= 4:
                score -= 6.0
        elif cost_mode is CostMode.LUXURY and gears is not None and gears >= 4:
            score += 8.0
            reasons.append("refinement-friendly gearing")

    if year >= 1920 and choice.start_year is not None and choice.start_year < year - 30:
        if any(
            (item.start_year or 0) >= year - 10
            for item in candidates
            if item.id != choice.id
        ):
            score -= 15.0
            penalties.append("very early tech for selected year when newer options exist")

    return max(min(score, 100.0), 0.0), penalties, reasons


def _cost_mode_score(
    choice: ComponentChoice,
    *,
    cost_mode: CostMode,
    vehicle_type: VehicleType,
) -> tuple[float, list[str], list[str]]:
    penalties: list[str] = []
    reasons: list[str] = []
    name = choice.display_name.lower()
    skill = choice.required_skill or 0.0
    score = 60.0

    if cost_mode is CostMode.CHEAP:
        score -= skill * 0.35
        if any(token in name for token in ("luxury", "super", "turbo", "performance", "sync")):
            score -= 18.0
            penalties.append("expensive/complex for cheap mode")
        else:
            reasons.append("cost-conscious choice")
    elif cost_mode is CostMode.LUXURY:
        score += min(skill, 40.0) * 0.25
        if any(token in name for token in ("comfort", "smooth", "luxury", "sync", "refined")):
            score += 12.0
            reasons.append("refinement-friendly choice")
        if is_primitive_layout(name):
            score -= 20.0
            penalties.append("primitive choice for luxury mode")
    else:
        score += 5.0
        reasons.append("balanced cost fit")

    weights = get_adjusted_vehicle_weights(vehicle_type)
    if weights.get("dependability", 0.0) >= 0.5 and "reliability" in choice.stats:
        score += choice.stats["reliability"] * 0.15

    return max(min(score, 100.0), 0.0), penalties, reasons


def score_component_suitability(
    choice: ComponentChoice,
    *,
    vehicle_type: VehicleType,
    cost_mode: CostMode,
    year: int,
    candidates: list[ComponentChoice],
) -> ComponentSuitabilityScore:
    """Score one available component candidate."""
    vehicle_group = classify_vehicle_group(vehicle_type)
    stat_score, has_stats = _stat_score(choice, vehicle_type=vehicle_type)
    era_score, era_penalties, era_reasons = _era_score(choice, year=year, candidates=candidates)
    fit_score, fit_penalties, fit_reasons = _vehicle_fit_score(
        choice,
        vehicle_type=vehicle_type,
        vehicle_group=vehicle_group,
        candidates=candidates,
        cost_mode=cost_mode,
        year=year,
    )
    cost_score, cost_penalties, cost_reasons = _cost_mode_score(
        choice,
        cost_mode=cost_mode,
        vehicle_type=vehicle_type,
    )

    penalties = era_penalties + fit_penalties + cost_penalties
    reasons = era_reasons + fit_reasons + cost_reasons
    if has_stats:
        reasons.append("parsed Components.xml stats used")
    else:
        reasons.append("limited parsed stats; heuristic scoring only")
        penalties.append("missing parsed stats")

    if choice.choice_type == "unknown":
        penalties.append("uncertain choice type classification")

    if choice.choice_type in {"gear_count", "overdrive"}:
        weights = {
            "stat": 0.10 if has_stats else 0.05,
            "fit": 0.55,
            "era": 0.05,
            "cost": 0.30,
        }
    elif choice.choice_type == "cylinder_count":
        weights = {
            "stat": 0.25 if has_stats else 0.15,
            "fit": 0.40,
            "era": 0.10,
            "cost": 0.25,
        }
    else:
        weights = {
            "stat": 0.35 if has_stats else 0.15,
            "fit": 0.30,
            "era": 0.20,
            "cost": 0.15,
        }
    total = (
        stat_score * weights["stat"]
        + fit_score * weights["fit"]
        + era_score * weights["era"]
        + cost_score * weights["cost"]
        + 100.0 * 0.0
    )
    total -= len(penalties) * 4.0
    total = max(min(total, 100.0), 0.0)

    if has_stats and total >= 80.0 and not penalties:
        confidence = "high"
    elif has_stats and total >= 70.0 and not penalties:
        confidence = "medium"
    elif has_stats and total >= 55.0:
        confidence = "low"
    else:
        confidence = "low"

    return ComponentSuitabilityScore(
        component_name=choice.display_name,
        section=choice.section,
        choice_type=choice.choice_type,
        total_score=round(total, 1),
        availability_score=100.0,
        vehicle_fit_score=round(fit_score, 1),
        cost_mode_score=round(cost_score, 1),
        era_score=round(era_score, 1),
        stat_score=round(stat_score, 1),
        penalties=penalties,
        reasons=reasons,
        confidence=confidence,
        choice=choice,
    )


def determine_auto_pick_status(suitability: float, confidence: str) -> AutoPickStatus:
    """Map suitability and confidence to an auto-pick status."""
    if suitability < AUTO_PICK_NOT_RECOMMENDED_MAX_SCORE:
        return "not_recommended"
    if suitability < AUTO_PICK_USABLE_MIN_SCORE or confidence == "low":
        return "low_confidence_candidate"
    if suitability < AUTO_PICK_RECOMMENDED_MIN_SCORE:
        return "usable_candidate"
    if confidence in {"medium", "high"}:
        return "recommended"
    return "low_confidence_candidate"


def auto_pick_status_label(status: AutoPickStatus) -> str:
    """Return a human-readable auto-pick status label."""
    return AUTO_PICK_STATUS_LABELS.get(status, status.replace("_", " ").title())


def suggested_choice_column_label(status: AutoPickStatus) -> str:
    """Return the column label for the top-ranked component."""
    if status == "recommended":
        return "Suggested choice"
    return "Top available candidate"


def is_reliable_auto_pick_status(status: AutoPickStatus) -> bool:
    """Return True when the auto-pick can be applied to slider optimization."""
    return status in {"recommended", "usable_candidate"}


def has_low_confidence_auto_picks(
    result: ComponentChoiceRecommendationResult,
) -> bool:
    """Return True when any auto-pick choice is low-confidence or not recommended."""
    return any(
        item.auto_pick_status in {"low_confidence_candidate", "not_recommended"}
        for item in result.choices
        if item.top_candidate is not None
    )


def _confidence_from_scores(scores: list[ComponentSuitabilityScore]) -> str:
    if not scores:
        return "none"
    top = scores[0]
    if top.penalties:
        return "low"
    if top.total_score >= 80.0:
        return "high"
    if top.total_score >= AUTO_PICK_MIN_SCORE:
        if len(scores) >= 2 and top.total_score - scores[1].total_score < AUTO_PICK_MIN_GAP:
            return "low"
        return "medium"
    return "low"


def _alternative_penalty_summary(scores: list[ComponentSuitabilityScore]) -> list[str]:
    notes: list[str] = []
    for candidate in scores[1:5]:
        if candidate.penalties:
            notes.append(f"{candidate.component_name}: {', '.join(candidate.penalties)}")
    return notes


def _reason_for_candidates(
    scores: list[ComponentSuitabilityScore],
    *,
    auto_pick_enabled: bool,
    vehicle_type: VehicleType,
    auto_pick_status: AutoPickStatus,
) -> str:
    if not scores:
        return "No available options for this choice type."
    top = scores[0]
    if not auto_pick_enabled:
        return (
            "Candidate rankings for manual inspection. "
            + EXPERIMENTAL_DISCLAIMER
        )

    penalty_text = "; ".join(top.penalties)
    if auto_pick_status == "recommended":
        return (
            f"Recommended auto-pick: {top.component_name} scored {top.total_score:.1f}/100 "
            f"for {vehicle_type.name}. {'; '.join(top.reasons[:2])}."
        )
    if auto_pick_status == "usable_candidate":
        return (
            f"Usable candidate: {top.component_name} scored {top.total_score:.1f}/100 "
            f"for {vehicle_type.name}. Review alternatives before copying into GearCity."
        )

    reason_parts = [
        f"Top parsed candidate, but score is low ({top.total_score:.1f}/100).",
    ]
    if top.reasons:
        reason_parts.append("; ".join(top.reasons[:2]))
    if penalty_text:
        reason_parts.append(penalty_text)
    return " ".join(reason_parts)


def _rank_candidates(
    candidates: list[ComponentChoice],
    *,
    vehicle_type: VehicleType,
    cost_mode: CostMode,
    year: int,
) -> list[ComponentSuitabilityScore]:
    scored = [
        score_component_suitability(
            choice,
            vehicle_type=vehicle_type,
            cost_mode=cost_mode,
            year=year,
            candidates=candidates,
        )
        for choice in candidates
    ]
    return sorted(
        scored,
        key=lambda item: (item.total_score, item.stat_score, item.era_score, item.component_name),
        reverse=True,
    )


def _filter_wiki_compatible_ranked(
    choice_type: str,
    ranked: list[ComponentSuitabilityScore],
    context_choices: dict[str, ComponentChoice],
) -> tuple[list[ComponentSuitabilityScore], list[str]]:
    """Drop ranked candidates that violate wiki rules given prior selections."""
    compatible: list[ComponentSuitabilityScore] = []
    for item in ranked:
        trial = dict(context_choices)
        trial[choice_type] = item.choice
        if is_valid_partial_choices(trial):
            compatible.append(item)

    warnings: list[str] = []
    if ranked and not compatible:
        violations = validate_component_choices(
            {**context_choices, choice_type: ranked[0].choice}
        ).violations
        if violations:
            warnings.append(
                f"No wiki-compatible {choice_type_label(choice_type).lower()} "
                f"for current selections: {violations[0]}"
            )
    elif len(compatible) < len(ranked):
        dropped = len(ranked) - len(compatible)
        warnings.append(
            f"Filtered {dropped} incompatible "
            f"{choice_type_label(choice_type).lower()} option(s) using wiki rules."
        )
    return compatible or ranked, warnings


def _recommend_for_type(
    choice_type: str,
    candidates: list[ComponentChoice],
    *,
    vehicle_type: VehicleType,
    cost_mode: CostMode,
    year: int,
    component_choice_mode: ComponentChoiceMode,
    context_choices: dict[str, ComponentChoice] | None = None,
) -> ChoiceRecommendation:
    context_choices = context_choices or {}
    if not candidates:
        return ChoiceRecommendation(
            section=_section_for_choice_type(choice_type),
            choice_type=choice_type,
            recommended_choice=None,
            alternatives=[],
            candidates=[],
            reason=f"No available {choice_type_label(choice_type).lower()} for this year and skill setup.",
            confidence="none",
            warnings=["No available options matched this choice type."],
        )

    ranked = _rank_candidates(
        candidates,
        vehicle_type=vehicle_type,
        cost_mode=cost_mode,
        year=year,
    )
    ranked, compat_warnings = _filter_wiki_compatible_ranked(
        choice_type,
        ranked,
        context_choices,
    )
    warnings: list[str] = list(compat_warnings)
    if component_choice_mode == "manual":
        return ChoiceRecommendation(
            section=_section_for_choice_type(choice_type),
            choice_type=choice_type,
            recommended_choice=None,
            alternatives=[item.choice for item in ranked[1:4]],
            candidates=ranked[:5],
            reason=_reason_for_candidates(
                ranked,
                auto_pick_enabled=False,
                vehicle_type=vehicle_type,
                auto_pick_status="manual",
            ),
            confidence="low",
            auto_pick_enabled=False,
            auto_pick_status="manual",
            top_candidate=ranked[0].choice if ranked else None,
            warnings=warnings,
        )

    top = ranked[0]
    confidence = _confidence_from_scores(ranked)
    auto_pick_status = determine_auto_pick_status(top.total_score, confidence)
    recommended_choice = top.choice if auto_pick_status == "recommended" else None
    warnings = [EXPERIMENTAL_DISCLAIMER]
    if auto_pick_status in {"low_confidence_candidate", "not_recommended"}:
        warnings.append(NO_RELIABLE_AUTO_PICK_WARNING)
    elif top.penalties:
        warnings.append(
            f"Top-ranked {top.component_name} has suitability penalties: "
            + "; ".join(top.penalties)
        )
    alt_penalties = _alternative_penalty_summary(ranked)
    if alt_penalties:
        warnings.append("Alternative penalties: " + "; ".join(alt_penalties[:4]))

    return ChoiceRecommendation(
        section=_section_for_choice_type(choice_type),
        choice_type=choice_type,
        recommended_choice=recommended_choice,
        alternatives=[item.choice for item in ranked[1:4]],
        candidates=ranked[:5],
        reason=_reason_for_candidates(
            ranked,
            auto_pick_enabled=True,
            vehicle_type=vehicle_type,
            auto_pick_status=auto_pick_status,
        ),
        confidence=confidence,
        auto_pick_enabled=True,
        auto_pick_status=auto_pick_status,
        top_candidate=top.choice,
        warnings=warnings,
    )


def _section_for_choice_type(choice_type: str) -> str:
    if choice_type in ENGINE_CHOICE_TYPES:
        return "engine"
    if choice_type in CHASSIS_CHOICE_TYPES:
        return "chassis"
    if choice_type in GEARBOX_CHOICE_TYPES:
        return "gearbox"
    if choice_type == "vehicle_body":
        return "vehicle"
    return "unknown"


def recommend_component_choices(
    vehicle_type: VehicleType,
    cost_mode: str,
    year: int,
    skills: dict[str, float],
    available_choices: list[ComponentChoice],
    *,
    manual_selections: dict[str, ComponentChoice] | None = None,
    component_choice_mode: ComponentChoiceMode = "auto",
) -> ComponentChoiceRecommendationResult:
    """Rank component candidates and optionally experimental auto-pick."""
    del skills
    parsed_cost_mode = parse_cost_mode(cost_mode)
    manual_selections = manual_selections or {}

    grouped: dict[str, list[ComponentChoice]] = {}
    for choice in available_choices:
        grouped.setdefault(choice.choice_type, []).append(choice)

    choice_types = list(ENGINE_CHOICE_TYPES) + list(CHASSIS_CHOICE_TYPES) + list(GEARBOX_CHOICE_TYPES)
    recommendations: list[ChoiceRecommendation] = []
    warnings: list[str] = []
    any_auto_pick = False
    selected_context: dict[str, ComponentChoice] = dict(manual_selections)

    for choice_type in choice_types:
        candidates = grouped.get(choice_type, [])
        if choice_type in manual_selections:
            selected = manual_selections[choice_type]
            ranked = _rank_candidates(
                candidates or [selected],
                vehicle_type=vehicle_type,
                cost_mode=parsed_cost_mode,
                year=year,
            )
            recommendations.append(
                ChoiceRecommendation(
                    section=_section_for_choice_type(choice_type),
                    choice_type=choice_type,
                    recommended_choice=selected,
                    alternatives=[
                        item.choice
                        for item in ranked
                        if item.choice.id != selected.id or item.choice.name != selected.name
                    ][:3],
                    candidates=ranked[:5],
                    reason=f"Manual selection for {choice_type_label(choice_type).lower()}.",
                    confidence="medium",
                    auto_pick_enabled=False,
                    auto_pick_status="manual",
                    top_candidate=selected,
                )
            )
            continue

        recommendation = _recommend_for_type(
            choice_type,
            candidates,
            vehicle_type=vehicle_type,
            cost_mode=parsed_cost_mode,
            year=year,
            component_choice_mode=component_choice_mode,
            context_choices=selected_context,
        )
        recommendations.append(recommendation)
        warnings.extend(recommendation.warnings)
        any_auto_pick = any_auto_pick or recommendation.auto_pick_enabled
        pick = recommendation.recommended_choice or recommendation.top_candidate
        if pick is not None:
            trial = dict(selected_context)
            trial[choice_type] = pick
            if is_valid_partial_choices(trial):
                selected_context[choice_type] = pick

    present_types = {choice.choice_type for choice in available_choices if choice.choice_type != "unknown"}
    if not present_types:
        warnings.append(
            "No recognizable component choice types were found in the imported catalog."
        )
    if component_choice_mode == "auto" and not any_auto_pick:
        warnings.append(EXPERIMENTAL_DISCLAIMER)

    if component_choice_mode == "auto" and has_low_confidence_auto_picks(
        ComponentChoiceRecommendationResult(
            vehicle_type_name=vehicle_type.name,
            year=year,
            cost_mode=parsed_cost_mode.value,
            choices=recommendations,
        )
    ):
        warnings.append(LOW_CONFIDENCE_PAGE_WARNING)

    return ComponentChoiceRecommendationResult(
        vehicle_type_name=vehicle_type.name,
        year=year,
        cost_mode=parsed_cost_mode.value,
        choices=[item for item in recommendations if item.candidates or item.recommended_choice],
        auto_pick_validated=any_auto_pick,
        warnings=sorted(set(warnings)),
    )


def choices_by_section(
    result: ComponentChoiceRecommendationResult,
    section: str,
) -> list[ChoiceRecommendation]:
    """Return choice recommendations for one section."""
    normalized = section.strip().lower()
    return [item for item in result.choices if item.section == normalized]
