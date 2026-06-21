"""Build formula influence maps from parsed GearCity Wiki mechanics pages."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from gearcity_optimizer.core.wiki_variable_classification import is_wiki_output_section
from gearcity_optimizer.importers.wiki_slider_parser import MECHANICS_PAGES, PAGE_TO_SECTION

SLIDER_VAR_RE = re.compile(r"\b(Slider[s]?_[A-Za-z0-9_]+)\b")
COMPONENT_VAR_RE = re.compile(
    r"\b(SubComponent_[A-Za-z0-9_]+|Selected_[A-Za-z0-9_]+\.[A-Za-z0-9_]+)\b"
)
INPUT_VAR_RE = re.compile(
    r"\b([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)?)\b"
)

GOAL_OUTPUT_ALIASES: dict[str, frozenset[str]] = {
    "fuel": frozenset(
        {
            "fuel",
            "fuel_consumption",
            "fuel_consumption_mpg",
            "fuel_economy_rating",
            "fuel_rating",
            "rating_fuel",
        }
    ),
    "power": frozenset(
        {
            "power",
            "torque",
            "horsepower",
            "hp",
            "rpm",
            "max_torque_support",
            "power_rating",
            "rating_power",
        }
    ),
    "performance": frozenset({"performance", "performance_rating", "rating_performance"}),
    "drivability": frozenset(
        {"driveability", "driveability_rating", "rating_drivability", "comfort_rating"}
    ),
    "luxury": frozenset({"luxury", "luxury_rating", "rating_luxury"}),
    "safety": frozenset({"safety", "safety_rating", "rating_safety", "strength_rating"}),
    "cargo": frozenset({"cargo", "cargo_rating", "rating_cargo", "cargo_volume"}),
    "dependability": frozenset(
        {
            "dependability",
            "dependability_rating",
            "rating_dependability",
            "reliability",
            "reliability_rating",
            "durability_rating",
        }
    ),
    "manufacturing_cost": frozenset({"unit_costs", "manufacturing_costs", "design_costs"}),
}


@dataclass(frozen=True)
class FormulaEffect:
    """One wiki formula section and the variables it references."""

    page: str
    output_key: str
    output_label: str
    section_title: str
    formula_text: str
    input_variables: list[str]
    slider_variables: list[str]
    component_variables: list[str]
    source_page: str
    source_section: str
    source_context: str
    confidence: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FormulaEffect:
        migrated = dict(data)
        if "input_variables" not in migrated:
            sliders = migrated.get("slider_variables", [])
            components = migrated.get("component_variables", [])
            migrated["input_variables"] = sorted(set(sliders) | set(components))
        if "source_page" not in migrated:
            migrated["source_page"] = migrated.pop("source_url", migrated.get("page", ""))
        if "source_section" not in migrated:
            migrated["source_section"] = migrated.get("section_title", "")
        if "source_context" not in migrated:
            migrated["source_context"] = migrated.get("formula_text", "")[:240]
        migrated.pop("source_url", None)
        allowed = set(cls.__dataclass_fields__)
        return cls(**{key: value for key, value in migrated.items() if key in allowed})


def normalize_output_key(section_title: str) -> str:
    """Normalize a wiki section title into a lookup key."""
    cleaned = re.sub(r"[^\w\s]", " ", section_title.strip())
    return re.sub(r"\s+", "_", cleaned).lower()


def _unique_sorted(values: list[str]) -> list[str]:
    return sorted(set(values))


def _extract_input_variables(formula_text: str) -> list[str]:
    tokens = INPUT_VAR_RE.findall(formula_text)
    ignored = {"if", "else", "and", "or", "not", "true", "false"}
    return _unique_sorted(
        token
        for token in tokens
        if token not in ignored and not token.isdigit() and not token.startswith("ex_")
    )


def build_formula_effects(
    parsed_pages: dict[str, dict[str, Any]],
    source_page_by_name: dict[str, str] | None = None,
) -> list[FormulaEffect]:
    """Scan formula sections and link outputs to slider/component variables."""
    source_page_by_name = source_page_by_name or {}
    effects: list[FormulaEffect] = []

    for page_name in sorted(parsed_pages):
        if page_name not in MECHANICS_PAGES:
            continue
        page = parsed_pages[page_name]
        formula_sections = page.get("formula_sections", {})
        source_page = source_page_by_name.get(page_name, page_name)
        page_section = PAGE_TO_SECTION.get(page_name, page_name)

        for section_title, formula_text in formula_sections.items():
            if not formula_text.strip():
                continue
            if not is_wiki_output_section(section_title):
                continue
            slider_variables = _unique_sorted(SLIDER_VAR_RE.findall(formula_text))
            component_variables = _unique_sorted(COMPONENT_VAR_RE.findall(formula_text))
            input_variables = _extract_input_variables(formula_text)
            if not slider_variables and not component_variables:
                continue
            output_key = normalize_output_key(section_title)
            confidence = "confirmed" if slider_variables else "inferred"
            effects.append(
                FormulaEffect(
                    page=page_section,
                    output_key=output_key,
                    output_label=section_title.strip(),
                    section_title=section_title.strip(),
                    formula_text=formula_text.strip(),
                    input_variables=input_variables,
                    slider_variables=slider_variables,
                    component_variables=component_variables,
                    source_page=source_page,
                    source_section=section_title.strip(),
                    source_context=formula_text.strip()[:240],
                    confidence=confidence,
                )
            )
    return effects


def effect_matches_goal(effect: FormulaEffect, goal_key: str) -> bool:
    """Return True when a formula effect is relevant to an optimization goal."""
    normalized_goal = goal_key.strip().lower()
    normalized_output = effect.output_key.lower()
    if normalized_goal in normalized_output or normalized_output in normalized_goal:
        return True
    aliases = GOAL_OUTPUT_ALIASES.get(normalized_goal, frozenset())
    if normalized_output in aliases:
        return True
    return any(alias in normalized_output for alias in aliases)


def build_slider_influence_weights(
    goal_weights: dict[str, float],
    effects: list[FormulaEffect],
) -> dict[str, float]:
    """Aggregate slider influence weights from goals and formula effects."""
    weights: dict[str, float] = {}
    for goal_key, goal_weight in goal_weights.items():
        if goal_weight <= 0.0:
            continue
        for effect in effects:
            if not effect.slider_variables:
                continue
            if not effect_matches_goal(effect, goal_key):
                continue
            for slider_variable in effect.slider_variables:
                weights[slider_variable] = weights.get(slider_variable, 0.0) + goal_weight
    return weights
