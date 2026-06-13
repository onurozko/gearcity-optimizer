"""Search local wiki sources and verify terminology mappings with evidence."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from gearcity_optimizer.data_sources import project_root

Status = str  # "confirmed", "conflicting", "unknown"

CONTEXT_CHARS = 120

DRIVABILITY_TERMS = (
    "Rating_Drivability",
    "Car_Type.Rating_Drivability",
    "Drivability",
    "Driveability",
    "Rating_Handling",
    "Handling",
    "Vehicle Handling Rating",
    "Vehicle Type Handling Rate",
    "Steering",
    "SubComponent_FrSus_Steering",
    "SubComponent_RrSus_Steering",
)

ENGINE_RELIABILITY_TERMS = (
    "Engine.Reliability",
    "Reliability Rating",
    "Engine Reliability Rating",
    "Reliability_Rating",
)

CHASSIS_DURABILITY_TERMS = (
    "ChassisInfo.Overall_Dependabilty",
    "Overall_Dependabilty",
    "Durability Rating",
    "Durability_Rating",
    "Chassis Durability",
    "Chassis Dependability",
)

GEARBOX_RELIABILITY_TERMS = (
    "Gearbox Reliability",
    "Gearbox.Reliability",
    "Reliability_Rating",
)

GEARBOX_COMFORT_TERMS = (
    "Gearbox Comfort Rating",
    "Comfort Rating",
    "Comfort_Rating",
    "Smoothness",
    "Shifting Ease",
    "Shifting_Ease",
    "Sliders_Design_Ease",
    "Subcomponents_Gearbox_Smoothness",
    "Subcomponents_Gearbox_Ease",
)

FINAL_VEHICLE_DEPENDABILITY_TERMS = (
    "Rating_Dependability",
    "Dependability Rating",
    "Selected_Chassis.Durability_Rating",
    "Selected_Engine.Reliability_Rating",
    "Selected_Gearbox.Reliability_Rating",
)

FINAL_VEHICLE_OVERALL_TERMS = (
    "Rating_Overall",
    "Overall Rating",
)

ENGINE_POWER_TERMS = (
    "Power Rating",
    "Power_Rating",
    "Horsepower",
    "Torque",
    "RPM",
    "hp =",
    "Selected_Engine.HP",
    "Selected_Engine.Torque",
)

FINAL_VEHICLE_POWER_TERMS = (
    "Rating_Power",
    "Final Vehicle Power",
)

DRIVABILITY_HANDLING_EQUIVALENCE = (
    re.compile(
        r"handling\s+is\s+(?:the\s+same\s+as|equivalent\s+to|also\s+called)\s+driv(?:e)?ability",
        re.I,
    ),
    re.compile(
        r"driv(?:e)?ability\s+is\s+(?:the\s+same\s+as|equivalent\s+to|also\s+called)\s+handling",
        re.I,
    ),
    re.compile(r"handling\s*[=:/]\s*driv(?:e)?ability", re.I),
    re.compile(r"driv(?:e)?ability\s*[=:/]\s*handling", re.I),
    re.compile(r"handling\s*/\s*driv(?:e)?ability|driv(?:e)?ability\s*/\s*handling", re.I),
)

DRIVABILITY_HANDLING_CONFLICT = (
    re.compile(r"handling\s+(?:and|,)\s+driv(?:e)?ability\s+(?:are\s+)?separate", re.I),
    re.compile(r"separate\s+from\s+driv(?:e)?ability", re.I),
    re.compile(r"different\s+(?:stat|rating)\s+from\s+driv(?:e)?ability", re.I),
    re.compile(r"handling\s+is\s+not\s+(?:the\s+same\s+as\s+)?driv(?:e)?ability", re.I),
    re.compile(r"not\s+(?:the\s+same\s+as\s+)?driv(?:e)?ability", re.I),
)

DURABILITY_DEPENDABILITY_EQUIVALENCE = (
    re.compile(
        r"durability\s+is\s+(?:the\s+same\s+as|equivalent\s+to)\s+dependability",
        re.I,
    ),
    re.compile(
        r"dependability\s+is\s+(?:the\s+same\s+as|equivalent\s+to)\s+durability",
        re.I,
    ),
    re.compile(r"overall_dependabil(?:ity|ty).*(?:same|equivalent).*durability", re.I),
)

DURABILITY_DEPENDABILITY_CONFLICT = (
    re.compile(r"durability\s+(?:and|,)\s+dependability\s+(?:are\s+)?separate", re.I),
    re.compile(r"separate\s+from\s+(?:final\s+)?dependability", re.I),
)

COMFORT_SMOOTHNESS_EQUIVALENCE = (
    re.compile(
        r"comfort\s+is\s+(?:the\s+same\s+as|equivalent\s+to|also\s+called)\s+smoothness",
        re.I,
    ),
    re.compile(
        r"smoothness\s+is\s+(?:the\s+same\s+as|equivalent\s+to|also\s+called)\s+comfort",
        re.I,
    ),
)

COMFORT_SMOOTHNESS_CONFLICT = (
    re.compile(r"comfort\s+(?:and|,)\s+smoothness\s+(?:are\s+)?separate", re.I),
    re.compile(r"comfort\s+is\s+not\s+smoothness", re.I),
)


@dataclass(frozen=True)
class TerminologyEvidence:
    """One match from a local wiki or parsed source file."""

    source_file: str
    source_type: str
    matched_text: str
    context: str


@dataclass
class TerminologyEntry:
    """Evidence-backed terminology mapping."""

    component: str
    internal_key: str
    formula_label: str
    observed_game_label: str | None
    display_label: str
    status: Status
    evidence: list[TerminologyEvidence] = field(default_factory=list)
    explanation: str = ""
    layer: str = ""

    @property
    def friendly_label(self) -> str:
        """Backward-compatible alias for display_label."""
        return self.display_label

    @property
    def confidence(self) -> str:
        """Backward-compatible confidence derived from verification status."""
        if self.status == "confirmed":
            return "confirmed"
        return "uncertain"


def _source_globs(root: Path) -> list[tuple[str, str]]:
    return [
        ("sources/wiki_raw/*.txt", "wiki_raw"),
        ("sources/wiki_text/*.html", "wiki_text"),
        ("sources/wiki_html/*.html", "wiki_html"),
        ("generated/raw_parsed/*.json", "wiki_parsed"),
    ]


def _context_snippet(text: str, index: int, term: str, context_chars: int) -> str:
    start = max(0, index - context_chars)
    end = min(len(text), index + len(term) + context_chars)
    return " ".join(text[start:end].split())


def _search_text(
    text: str,
    term: str,
    source_file: str,
    source_type: str,
    context_chars: int,
) -> list[TerminologyEvidence]:
    matches: list[TerminologyEvidence] = []
    pattern = re.compile(re.escape(term), re.I)
    for match in pattern.finditer(text):
        matches.append(
            TerminologyEvidence(
                source_file=source_file,
                source_type=source_type,
                matched_text=match.group(0),
                context=_context_snippet(text, match.start(), term, context_chars),
            )
        )
    return matches


def _search_file(
    path: Path,
    term: str,
    source_file: str,
    source_type: str,
    context_chars: int,
) -> list[TerminologyEvidence]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    if source_type == "wiki_parsed" and path.suffix == ".json":
        try:
            data = json.loads(text)
            text = json.dumps(data, ensure_ascii=False)
        except json.JSONDecodeError:
            pass
    return _search_text(text, term, source_file, source_type, context_chars)


def search_terminology_sources(
    terms: list[str],
    *,
    root: Path | None = None,
    context_chars: int = CONTEXT_CHARS,
) -> list[TerminologyEvidence]:
    """Search local wiki and parsed files for terminology matches."""
    base = root or project_root()
    evidence: list[TerminologyEvidence] = []
    seen: set[tuple[str, str, str]] = set()

    for glob_pattern, source_type in _source_globs(base):
        for path in sorted(base.glob(glob_pattern)):
            rel = str(path.relative_to(base)).replace("\\", "/")
            for term in terms:
                for item in _search_file(path, term, rel, source_type, context_chars):
                    key = (item.source_file, item.matched_text.lower(), item.context[:80])
                    if key in seen:
                        continue
                    seen.add(key)
                    evidence.append(item)

    formula_index = base / "generated" / "raw_parsed" / "wiki_formula_index.json"
    if formula_index.is_file():
        rel = str(formula_index.relative_to(base)).replace("\\", "/")
        for term in terms:
            for item in _search_file(
                formula_index,
                term,
                rel,
                "formula_index",
                context_chars,
            ):
                key = (item.source_file, item.matched_text.lower(), item.context[:80])
                if key not in seen:
                    seen.add(key)
                    evidence.append(item)

    return evidence


def sources_available(root: Path | None = None) -> bool:
    """Return True when at least one searchable terminology source exists."""
    base = root or project_root()
    for glob_pattern, _ in _source_globs(base):
        if any(base.glob(glob_pattern)):
            return True
    return (base / "generated" / "raw_parsed" / "wiki_formula_index.json").is_file()


def _evidence_has_term(evidence: list[TerminologyEvidence], pattern: str) -> bool:
    regex = re.compile(pattern, re.I)
    return any(regex.search(item.matched_text) or regex.search(item.context) for item in evidence)


def _assess_status(
    evidence: list[TerminologyEvidence],
    equivalence_patterns: tuple[re.Pattern[str], ...],
    conflict_patterns: tuple[re.Pattern[str], ...],
    *,
    term_a_pattern: str,
    term_b_pattern: str | None = None,
) -> Status:
    for item in evidence:
        for pattern in equivalence_patterns:
            if pattern.search(item.context):
                return "confirmed"
    for item in evidence:
        for pattern in conflict_patterns:
            if pattern.search(item.context):
                return "conflicting"
    has_a = _evidence_has_term(evidence, term_a_pattern)
    has_b = _evidence_has_term(evidence, term_b_pattern) if term_b_pattern else False
    if has_a and has_b:
        return "unknown"
    if has_a or has_b:
        return "unknown"
    return "unknown"


def _missing_sources_explanation() -> str:
    return (
        "Terminology sources are missing. Run:\n"
        "  python -m gearcity_optimizer.cli setup-sources\n"
        "or:\n"
        "  python -m gearcity_optimizer.cli download-wiki\n"
        "  python -m gearcity_optimizer.cli import-wiki"
    )


def verify_drivability_handling_mapping(
    *,
    root: Path | None = None,
) -> TerminologyEntry:
    """Verify Driveability formula naming vs UI Handling wording."""
    evidence = search_terminology_sources(list(DRIVABILITY_TERMS), root=root)
    status = _assess_status(
        evidence,
        DRIVABILITY_HANDLING_EQUIVALENCE,
        DRIVABILITY_HANDLING_CONFLICT,
        term_a_pattern=r"driv(?:e)?ability|rating_drivability|car_type\.rating_drivability",
        term_b_pattern=r"handling",
    )
    has_formula = _evidence_has_term(
        evidence,
        r"rating_drivability|car_type\.rating_drivability|driveability rating",
    )
    has_steering = _evidence_has_term(
        evidence, r"steering|frsus_steering|rrsus_steering|subcomponent_frsus"
    )
    has_suspicious_dynamic = _evidence_has_term(
        evidence, r"vehicle handling rating.*dependability"
    )

    if not evidence:
        explanation = _missing_sources_explanation()
    elif status == "confirmed":
        explanation = (
            "Local wiki sources explicitly connect Handling and Driveability. "
            "This tool still uses Driveability as the formula-backed label."
        )
    elif status == "conflicting":
        explanation = (
            "Some sources treat Handling and Driveability as separate concepts. "
            "Wiki vehicle formulas use Driveability / Rating_Drivability for the "
            "final vehicle stat."
        )
    elif has_formula:
        parts = [
            "The GearCity wiki formulas use Driveability / Rating_Drivability "
            "for the final vehicle stat.",
        ]
        if has_steering:
            parts.append(
                "Chassis steering/handling subcomponent values feed into this rating."
            )
        parts.append(
            "Vehicle type scoring uses Car_Type.Rating_Drivability."
        )
        parts.append(
            "Some in-game screens may display Handling, but Handling is not treated "
            "as a separate confirmed final stat."
        )
        if has_suspicious_dynamic:
            parts.append(
                "Dynamic Reports contains inconsistent Handling wording that is not "
                "used as proof of a separate final Handling stat."
            )
        explanation = " ".join(parts)
    else:
        explanation = (
            "Local sources mention Driveability and/or Handling but the final "
            "vehicle formula name is not confirmed yet."
        )

    display_label = "Driveability"

    return TerminologyEntry(
        component="vehicle",
        internal_key="drivability",
        formula_label="Driveability",
        observed_game_label="Handling",
        display_label=display_label,
        status=status,
        evidence=evidence,
        explanation=explanation,
        layer="final vehicle stat",
    )


def verify_engine_reliability_mapping(*, root: Path | None = None) -> TerminologyEntry:
    """Verify engine reliability terminology from local wiki evidence."""
    evidence = search_terminology_sources(list(ENGINE_RELIABILITY_TERMS), root=root)
    has_formula = _evidence_has_term(evidence, r"reliability")
    status: Status = "confirmed" if has_formula else "unknown"
    explanation = (
        "Local wiki engine formula sources reference Reliability Rating."
        if has_formula
        else _missing_sources_explanation()
        if not evidence
        else "Engine reliability terms appear in sources but need manual review."
    )
    return TerminologyEntry(
        component="engine",
        internal_key="reliability",
        formula_label="Reliability Rating",
        observed_game_label=None,
        display_label="Engine Reliability Rating",
        status=status,
        evidence=evidence,
        explanation=(
            f"{explanation} Component-level engine stat; not final vehicle dependability."
        ),
        layer="component stat",
    )


def verify_chassis_durability_mapping(*, root: Path | None = None) -> TerminologyEntry:
    """Verify chassis durability vs dependability terminology."""
    evidence = search_terminology_sources(list(CHASSIS_DURABILITY_TERMS), root=root)
    status = _assess_status(
        evidence,
        DURABILITY_DEPENDABILITY_EQUIVALENCE,
        DURABILITY_DEPENDABILITY_CONFLICT,
        term_a_pattern=r"durability",
        term_b_pattern=r"dependabil",
    )
    has_durability = _evidence_has_term(evidence, r"durability")
    if not evidence:
        explanation = _missing_sources_explanation()
    elif status == "confirmed":
        explanation = "Local sources explicitly link chassis durability and dependability."
    elif status == "conflicting":
        explanation = (
            "Local sources treat chassis durability and dependability as distinct."
        )
    else:
        explanation = (
            "Chassis Durability Rating is a component-level wiki stat. It may relate "
            "to dependability UI wording but is not proven identical to final vehicle "
            "dependability."
        )

    if status == "confirmed":
        display_label = "Durability Rating / Dependability"
    elif has_durability:
        display_label = "Chassis Durability Rating"
    else:
        display_label = "Durability Rating (dependability-related)"

    if not has_durability and not evidence:
        status = "unknown"

    return TerminologyEntry(
        component="chassis",
        internal_key="durability",
        formula_label="Durability Rating",
        observed_game_label="Dependability",
        display_label=display_label,
        status=status,
        evidence=evidence,
        explanation=explanation,
        layer="component stat",
    )


def verify_gearbox_reliability_mapping(*, root: Path | None = None) -> TerminologyEntry:
    """Verify gearbox reliability terminology from local wiki evidence."""
    evidence = search_terminology_sources(list(GEARBOX_RELIABILITY_TERMS), root=root)
    has_formula = _evidence_has_term(evidence, r"reliability")
    status: Status = "confirmed" if has_formula else "unknown"
    explanation = (
        "Local wiki gearbox formula sources reference Reliability Rating."
        if has_formula
        else _missing_sources_explanation()
        if not evidence
        else "Gearbox reliability terms appear in sources but need manual review."
    )
    return TerminologyEntry(
        component="gearbox",
        internal_key="reliability",
        formula_label="Reliability Rating",
        observed_game_label=None,
        display_label="Gearbox Reliability Rating",
        status=status,
        evidence=evidence,
        explanation=(
            f"{explanation} Component-level gearbox stat; not final vehicle dependability."
        ),
        layer="component stat",
    )


def verify_gearbox_comfort_mapping(*, root: Path | None = None) -> TerminologyEntry:
    """Verify gearbox comfort vs smoothness terminology."""
    evidence = search_terminology_sources(list(GEARBOX_COMFORT_TERMS), root=root)
    status = _assess_status(
        evidence,
        COMFORT_SMOOTHNESS_EQUIVALENCE,
        COMFORT_SMOOTHNESS_CONFLICT,
        term_a_pattern=r"comfort",
        term_b_pattern=r"smoothness|shifting ease",
    )
    has_comfort = _evidence_has_term(evidence, r"comfort")
    if not evidence:
        explanation = _missing_sources_explanation()
    elif status == "confirmed":
        explanation = "Local sources explicitly equate gearbox Comfort and Smoothness."
    elif status == "conflicting":
        explanation = "Local sources treat Comfort and Smoothness as separate gearbox stats."
    else:
        explanation = (
            "Gearbox Comfort Rating is influenced by shifting ease and gearbox "
            "smoothness variables. UI Smoothness label is not proven identical."
        )

    if status == "confirmed":
        display_label = "Comfort Rating / Smoothness"
    else:
        display_label = "Gearbox Comfort Rating"

    if not has_comfort and not evidence:
        status = "unknown"

    return TerminologyEntry(
        component="gearbox",
        internal_key="comfort",
        formula_label="Comfort Rating",
        observed_game_label="Smoothness",
        display_label=display_label,
        status=status,
        evidence=evidence,
        explanation=explanation,
        layer="component stat",
    )


def verify_final_vehicle_dependability_mapping(
    *,
    root: Path | None = None,
) -> TerminologyEntry:
    """Verify final vehicle dependability vs component reliability/durability."""
    evidence = search_terminology_sources(list(FINAL_VEHICLE_DEPENDABILITY_TERMS), root=root)
    has_final_formula = _evidence_has_term(evidence, r"rating_dependability")
    has_component_inputs = _evidence_has_term(
        evidence, r"durability_rating|reliability_rating"
    )
    if not evidence:
        status: Status = "unknown"
        explanation = _missing_sources_explanation()
    elif has_final_formula:
        status = "confirmed"
        explanation = (
            "Local wiki vehicle formulas define Rating_Dependability as the assembled "
            "vehicle dependability stat. It uses component reliability/durability inputs "
            "plus testing, materials, design focus, and penalties. Engine reliability, "
            "chassis durability, and gearbox reliability are related component-level "
            "stats but not identical to final vehicle dependability."
        )
    elif has_component_inputs:
        status = "unknown"
        explanation = (
            "Sources reference component durability/reliability inputs. Final vehicle "
            "Rating_Dependability formula not confirmed in local sources yet."
        )
    else:
        status = "unknown"
        explanation = "Dependability terms appear but need manual review."

    return TerminologyEntry(
        component="vehicle",
        internal_key="dependability",
        formula_label="Dependability Rating",
        observed_game_label="Dependability",
        display_label="Dependability",
        status=status,
        evidence=evidence,
        explanation=explanation,
        layer="final vehicle stat",
    )


def verify_final_vehicle_overall_mapping(*, root: Path | None = None) -> TerminologyEntry:
    """Verify overall rating terminology and distinguish from dependability."""
    evidence = search_terminology_sources(list(FINAL_VEHICLE_OVERALL_TERMS), root=root)
    has_overall = _evidence_has_term(evidence, r"rating_overall|overall rating")
    if not evidence:
        status: Status = "unknown"
        explanation = _missing_sources_explanation()
    elif has_overall:
        status = "confirmed"
        explanation = (
            "Local wiki sources define Rating_Overall as a broad summary of final "
            "vehicle ratings. Overall is not the same as dependability or component "
            "reliability/durability."
        )
    else:
        status = "unknown"
        explanation = "Overall rating terms appear but need manual review."

    return TerminologyEntry(
        component="vehicle",
        internal_key="overall",
        formula_label="Overall Rating",
        observed_game_label="Overall",
        display_label="Overall Rating",
        status=status,
        evidence=evidence,
        explanation=explanation,
        layer="summary rating",
    )


def verify_engine_power_rating_mapping(*, root: Path | None = None) -> TerminologyEntry:
    """Verify engine Power Rating vs horsepower and torque specs."""
    evidence = search_terminology_sources(list(ENGINE_POWER_TERMS), root=root)
    has_power_rating = _evidence_has_term(evidence, r"power_rating|power rating")
    has_horsepower = _evidence_has_term(evidence, r"horsepower|\bhp\b")
    has_torque = _evidence_has_term(evidence, r"torque")
    if not evidence:
        status: Status = "unknown"
        explanation = _missing_sources_explanation()
    elif has_power_rating and (has_horsepower or has_torque):
        status = "confirmed"
        explanation = (
            "Horsepower and torque are engine specs calculated from design inputs. "
            "Power Rating is a separate formula-derived component rating, not merely "
            "a cosmetic label."
        )
    elif has_power_rating:
        status = "confirmed"
        explanation = (
            "Local wiki engine formulas reference Power Rating as a derived rating."
        )
    else:
        status = "unknown"
        explanation = (
            "Engine power terms appear in sources but Power Rating formula not "
            "confirmed yet."
        )

    return TerminologyEntry(
        component="engine",
        internal_key="power_rating",
        formula_label="Power Rating",
        observed_game_label="Power",
        display_label="Engine Power Rating",
        status=status,
        evidence=evidence,
        explanation=explanation,
        layer="component stat",
    )


def verify_final_vehicle_power_mapping(*, root: Path | None = None) -> TerminologyEntry:
    """Verify final assembled vehicle power rating vs engine specs."""
    terms = list(FINAL_VEHICLE_POWER_TERMS) + list(ENGINE_POWER_TERMS)
    evidence = search_terminology_sources(terms, root=root)
    has_final_power = _evidence_has_term(evidence, r"rating_power")
    has_engine_hp = _evidence_has_term(evidence, r"selected_engine\.hp|horsepower")
    if not evidence:
        status: Status = "unknown"
        explanation = _missing_sources_explanation()
    elif has_final_power:
        status = "confirmed"
        explanation = (
            "Local wiki vehicle formulas define Rating_Power as a final assembled "
            "vehicle stat derived from engine horsepower/torque and related inputs. "
            "This is separate from raw engine horsepower and torque specs."
        )
    elif has_engine_hp:
        status = "unknown"
        explanation = (
            "Engine horsepower/torque specs appear in sources. Final vehicle "
            "Rating_Power formula not confirmed yet."
        )
    else:
        status = "unknown"
        explanation = "Vehicle power terms need manual review."

    return TerminologyEntry(
        component="vehicle",
        internal_key="power",
        formula_label="Power Rating",
        observed_game_label="Power",
        display_label="Final Vehicle Power Rating",
        status=status,
        evidence=evidence,
        explanation=explanation,
        layer="final vehicle stat",
    )


VERIFICATION_BUILDERS: dict[tuple[str, str], Callable[..., TerminologyEntry]] = {
    ("vehicle", "drivability"): verify_drivability_handling_mapping,
    ("vehicle", "dependability"): verify_final_vehicle_dependability_mapping,
    ("vehicle", "overall"): verify_final_vehicle_overall_mapping,
    ("vehicle", "power"): verify_final_vehicle_power_mapping,
    ("engine", "reliability"): verify_engine_reliability_mapping,
    ("engine", "power_rating"): verify_engine_power_rating_mapping,
    ("chassis", "durability"): verify_chassis_durability_mapping,
    ("gearbox", "reliability"): verify_gearbox_reliability_mapping,
    ("gearbox", "comfort"): verify_gearbox_comfort_mapping,
}


def verify_term_search(
    term: str,
    *,
    root: Path | None = None,
    full: bool = False,
) -> tuple[list[TerminologyEvidence], str]:
    """Search for a single term and return evidence plus availability note."""
    evidence = search_terminology_sources([term], root=root)
    if evidence:
        note = f"Found {len(evidence)} match(es) for {term!r}."
    else:
        note = _missing_sources_explanation() if not sources_available(root) else (
            f"No matches for {term!r} in available local sources."
        )
    if not full and evidence:
        evidence = evidence[:5]
    return evidence, note


def format_audit_entry_text(entry: TerminologyEntry, *, full: bool = False) -> str:
    """Format one terminology audit entry for CLI output."""
    mapping = entry.formula_label
    if entry.observed_game_label:
        mapping = f"{entry.formula_label} vs {entry.observed_game_label}"
    lines = [
        "Term / mapping:",
        mapping,
        "",
        "Status:",
        entry.status,
        "",
        "Display label:",
        entry.display_label,
        "",
        "Evidence:",
    ]
    if not entry.evidence:
        lines.append("  (none)")
    else:
        shown = entry.evidence if full else entry.evidence[:5]
        for item in shown:
            lines.append(f"  * [{item.source_type}] {item.source_file}")
            lines.append(f"    matched: {item.matched_text!r}")
            lines.append(f"    context: {item.context}")
        if not full and len(entry.evidence) > 5:
            lines.append(f"  ... and {len(entry.evidence) - 5} more (use --full)")
    lines.extend(["", "Conclusion:", entry.explanation, ""])
    return "\n".join(lines)
