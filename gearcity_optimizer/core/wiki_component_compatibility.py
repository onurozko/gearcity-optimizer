"""Wiki-backed component compatibility rules for engine, chassis, and gearbox choices."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gearcity_optimizer.importers.component_choices import ComponentChoice

WIKI_COMPATIBILITY_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "wiki_component_compatibility.json"
)

INDUCTION_PREFIXES = (
    ("noinduction", "No Induction"),
    ("natural", "Naturally Aspirated"),
    ("supercharg", "Supercharger"),
    ("turbo", "Turbocharger"),
    ("twincharger", "Twincharger"),
    ("hybridturbo", "Hybrid Turbocharger"),
)


@dataclass(frozen=True)
class CompatibilityResult:
    """Validation outcome for a component choice set."""

    is_valid: bool
    violations: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _choice_text(choice: ComponentChoice) -> str:
    return " ".join(
        [
            choice.display_name,
            choice.name,
            choice.raw_attributes.get("picture", ""),
            choice.raw_attributes.get("type", ""),
        ]
    )


def _matches_entry(choice: ComponentChoice, canonical: str, aliases: tuple[str, ...]) -> bool:
    name = _normalize(choice.name)
    display = _normalize(choice.display_name)
    picture = _normalize(choice.raw_attributes.get("picture", "").rsplit(".", 1)[0])
    tokens = {token for token in (name, display, picture) if token}
    candidates = (_normalize(canonical), *(_normalize(alias) for alias in aliases))
    return any(candidate and candidate in tokens for candidate in candidates)


@lru_cache(maxsize=1)
def load_wiki_compatibility_rules() -> dict[str, Any]:
    """Load wiki-backed compatibility rules from bundled JSON."""
    with WIKI_COMPATIBILITY_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def resolve_engine_layout_key(layout: ComponentChoice) -> str | None:
    """Map a Components.xml layout choice to a wiki layout key."""
    rules = load_wiki_compatibility_rules()
    for key, spec in rules["engine_layouts"].items():
        aliases = tuple(spec.get("aliases", ()))
        if _matches_entry(layout, key, aliases):
            return key
    return None


def parse_cylinder_count(choice: ComponentChoice) -> int | None:
    """Parse numeric cylinder count from a cylinder_count choice."""
    if "cylinders" in choice.stats:
        return max(1, int(choice.stats["cylinders"]))
    name = _normalize(choice.display_name)
    match = re.search(r"(\d+)", name)
    if match:
        return int(match.group(1))
    word_map = {
        "single": 1,
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
        "twelve": 12,
        "fifteen": 15,
        "sixteen": 16,
        "eighteen": 18,
    }
    for word, count in word_map.items():
        if word in name:
            return count
    if "cylinder" in name and "single" not in name:
        return 1
    return None


def parse_gear_count(choice: ComponentChoice) -> int | None:
    """Parse gear count from a gear_count choice."""
    if "gears" in choice.stats:
        return max(1, int(choice.stats["gears"]))
    match = re.search(r"(\d+)", _normalize(choice.display_name))
    if match:
        return int(match.group(1))
    return None


def layout_cylinder_bank_arrangement(layout: ComponentChoice) -> int:
    """Return wiki cylinder arrangement for formula inputs."""
    key = resolve_engine_layout_key(layout)
    if key is None:
        return 1
    return int(load_wiki_compatibility_rules()["engine_layouts"][key].get("cylinder_arrangement", 1))


def _resolve_named_entry(
    choice: ComponentChoice,
    table: dict[str, dict[str, Any]],
) -> str | None:
    for key, spec in table.items():
        aliases = tuple(spec.get("aliases", ()))
        if _matches_entry(choice, key, aliases):
            return key
    return None


def _resolve_fuel(choice: ComponentChoice) -> str | None:
    return _resolve_named_entry(choice, load_wiki_compatibility_rules()["fuel_types"])


def _resolve_induction(choice: ComponentChoice) -> str | None:
    rules = load_wiki_compatibility_rules()
    resolved = _resolve_named_entry(choice, rules["inductions"])
    if resolved:
        return resolved
    normalized = _normalize(_choice_text(choice))
    for prefix, canonical in INDUCTION_PREFIXES:
        if prefix in normalized:
            return canonical
    return None


def _resolve_valvetrain(choice: ComponentChoice) -> tuple[str | None, int | None]:
    rules = load_wiki_compatibility_rules()
    key = _resolve_named_entry(choice, rules["valvetrains"])
    if key is None:
        return None, None
    return key, int(rules["valvetrains"][key]["valve_group"])


def _resolve_gearbox_type(choice: ComponentChoice) -> str | None:
    return _resolve_named_entry(choice, load_wiki_compatibility_rules()["gearbox_types"])


def _resolve_gearbox_addon(choice: ComponentChoice) -> str | None:
    return _resolve_named_entry(choice, load_wiki_compatibility_rules()["gearbox_addons"])


def _allowed_inductions_for_layout(layout_key: str) -> tuple[str, ...]:
    spec = load_wiki_compatibility_rules()["engine_layouts"][layout_key]
    return tuple(spec.get("inductions", ()))


def _induction_allowed(choice: ComponentChoice, layout_key: str) -> bool:
    allowed = _allowed_inductions_for_layout(layout_key)
    resolved = _resolve_induction(choice)
    if resolved is None:
        return True
    if resolved in allowed:
        return True
    normalized = _normalize(resolved)
    if "turbo" in normalized:
        return any("turbo" in _normalize(item) for item in allowed)
    return False


def _fuel_allowed(choice: ComponentChoice, layout_key: str) -> bool:
    allowed = tuple(load_wiki_compatibility_rules()["engine_layouts"][layout_key].get("fuels", ()))
    resolved = _resolve_fuel(choice)
    if resolved is None:
        return True
    return resolved in allowed


def _cylinder_allowed(choice: ComponentChoice, layout_key: str) -> bool:
    spec = load_wiki_compatibility_rules()["engine_layouts"][layout_key]
    allowed_counts = spec.get("cylinder_counts", [])
    special_aliases = tuple(spec.get("special_cylinder_aliases", ()))
    if special_aliases and _matches_entry(choice, special_aliases[0], special_aliases):
        return True
    count = parse_cylinder_count(choice)
    if count is None:
        return not allowed_counts
    if not allowed_counts:
        return _matches_entry(choice, special_aliases[0], special_aliases) if special_aliases else False
    return count in allowed_counts


def validate_component_choices(choices: dict[str, ComponentChoice]) -> CompatibilityResult:
    """Validate a complete or partial component choice set against wiki rules."""
    violations: list[str] = []
    warnings: list[str] = []

    layout = choices.get("engine_layout")
    if layout is not None:
        layout_key = resolve_engine_layout_key(layout)
        if layout_key is None:
            warnings.append(
                f"Unknown engine layout {layout.display_name!r}; wiki compatibility checks skipped."
            )
        else:
            cylinder = choices.get("cylinder_count")
            if cylinder is not None and not _cylinder_allowed(cylinder, layout_key):
                allowed = load_wiki_compatibility_rules()["engine_layouts"][layout_key].get(
                    "cylinder_counts", []
                )
                violations.append(
                    f"{layout.display_name} does not support {cylinder.display_name}. "
                    f"Allowed cylinder counts: {', '.join(str(item) for item in allowed) or 'special only'}."
                )

            fuel = choices.get("fuel_type")
            if fuel is not None and not _fuel_allowed(fuel, layout_key):
                allowed_fuels = load_wiki_compatibility_rules()["engine_layouts"][layout_key]["fuels"]
                violations.append(
                    f"{layout.display_name} does not support fuel {fuel.display_name}. "
                    f"Allowed fuels include: {', '.join(allowed_fuels[:4])}..."
                )

            valvetrain = choices.get("valvetrain")
            if valvetrain is not None:
                _, valve_group = _resolve_valvetrain(valvetrain)
                allowed_groups = load_wiki_compatibility_rules()["engine_layouts"][layout_key]["valve_groups"]
                if valve_group is not None and valve_group not in allowed_groups:
                    if valve_group == 1:
                        detail = "No Valve layouts only (Electric, Steam, Wankel)."
                    elif valve_group == 3:
                        detail = "Poppet-style valvetrains only (Radial, Rotary)."
                    else:
                        detail = "Normal valvetrains only."
                    violations.append(
                        f"{layout.display_name} does not support valvetrain {valvetrain.display_name}. "
                        f"{detail}"
                    )

            induction = choices.get("forced_induction")
            if induction is not None and not _induction_allowed(induction, layout_key):
                violations.append(
                    f"{layout.display_name} does not support induction {induction.display_name}."
                )

    gearbox_type = choices.get("gearbox_type")
    if gearbox_type is not None:
        type_key = _resolve_gearbox_type(gearbox_type)
        if type_key is None:
            warnings.append(
                f"Unknown gearbox type {gearbox_type.display_name!r}; wiki gear rules skipped."
            )
        else:
            spec = load_wiki_compatibility_rules()["gearbox_types"][type_key]
            gear = choices.get("gear_count")
            if gear is not None:
                gear_count = parse_gear_count(gear)
                allowed_gears = spec.get("gear_counts", [])
                if gear_count is not None and gear_count not in allowed_gears:
                    violations.append(
                        f"{gearbox_type.display_name} does not support {gear.display_name}. "
                        f"Allowed gear counts: {', '.join(str(item) for item in allowed_gears)}."
                    )
            overdrive = choices.get("overdrive")
            if overdrive is not None:
                addon = _resolve_gearbox_addon(overdrive)
                allowed_addons = spec.get("addons", [])
                if addon is not None and addon not in allowed_addons:
                    violations.append(
                        f"{gearbox_type.display_name} does not support addon {overdrive.display_name}."
                    )

    return CompatibilityResult(
        is_valid=not violations,
        violations=tuple(violations),
        warnings=tuple(warnings),
    )


def is_valid_component_choices(choices: dict[str, ComponentChoice]) -> bool:
    """Return True when choices satisfy wiki compatibility rules."""
    return validate_component_choices(choices).is_valid


def is_valid_partial_choices(choices: dict[str, ComponentChoice]) -> bool:
    """Return True when a partial beam-search state has no rule violations so far."""
    return is_valid_component_choices(choices)


def compatibility_violations(choices: dict[str, ComponentChoice]) -> list[str]:
    """Return human-readable compatibility violations."""
    return list(validate_component_choices(choices).violations)


def filter_compatible_candidates(
    choice_type: str,
    candidate: ComponentChoice,
    partial_choices: dict[str, ComponentChoice],
) -> bool:
    """Return True if adding candidate to partial choices keeps wiki compatibility."""
    trial = dict(partial_choices)
    trial[choice_type] = candidate
    return is_valid_partial_choices(trial)


def filter_engine_layout_candidates(
    candidates: list[ComponentChoice],
    *,
    partial_choices: dict[str, ComponentChoice] | None = None,
) -> list[ComponentChoice]:
    """Filter layout candidates that violate wiki rules in the current partial design."""
    partial = dict(partial_choices or {})
    filtered: list[ComponentChoice] = []
    for candidate in candidates:
        if filter_compatible_candidates("engine_layout", candidate, partial):
            filtered.append(candidate)
    return filtered or candidates
