"""Command-line interface for GearCity design helper commands."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd

from gearcity_optimizer.core.component_models import (
    load_chassis_candidates,
    load_engine_candidates,
    load_gearbox_candidates,
)
from gearcity_optimizer.core.component_optimizer import (
    PACKAGE_OBJECTIVES,
    rank_component_packages,
)
from gearcity_optimizer.core.component_priorities import (
    calculate_component_priorities,
    format_stat_label,
    get_adjusted_vehicle_weights,
)
from gearcity_optimizer.core.models import load_candidate_designs
from gearcity_optimizer.core.optimizer import VALID_OBJECTIVES, rank_candidates
from gearcity_optimizer.core.scoring import calculate_value_score
from gearcity_optimizer.core.vehicle_type_groups import (
    cluster_vehicle_types,
    find_most_similar_vehicle_types,
)
from gearcity_optimizer.core.vehicle_types import load_vehicle_types
from gearcity_optimizer.data_sources import (
    DEFAULT_CANDIDATES,
    DEFAULT_CHASSIS,
    DEFAULT_ENGINES,
    DEFAULT_GEARBOXES,
    DEFAULT_VEHICLE_TYPES,
    data_path,
)
from gearcity_optimizer.formula_browser import (
    FormulaIndexError,
    FORMULA_INDEX_MISSING_MSG,
    GENERATED_FILES_MISSING_MSG,
    excerpt_text,
    export_formula_markdown,
    get_formula_section,
    list_formula_pages,
    list_formula_sections,
    load_formula_index,
    search_formulas,
)
from gearcity_optimizer.formulas.chassis_formula import (
    ChassisFormulaInputs,
    calculate_chassis,
    export_chassis_candidates_csv,
    load_chassis_formula_inputs,
)
from gearcity_optimizer.formulas.engine_formula import (
    EngineFormulaInputs,
    calculate_engine,
    export_engine_candidates_csv,
    load_engine_formula_inputs,
)
from gearcity_optimizer.formulas.gearbox_formula import (
    GearboxFormulaInputs,
    calculate_gearbox,
    export_gearbox_candidates_csv,
    load_gearbox_formula_inputs,
)
from gearcity_optimizer.importers.wiki_downloader import (
    download_wiki_pages,
    project_root_from_module,
)
from gearcity_optimizer.importers.wiki_parser import (
    compare_vehicle_type_tables,
    import_wiki_pages,
    is_wiki_page_json,
)
from gearcity_optimizer.importers.component_sources import (
    components_missing_message,
    import_components_from_path,
)
from gearcity_optimizer.importers.components_xml import (
    ComponentsValidationError,
    catalog_summary,
    classify_components,
    load_imported_components_catalog,
    validate_year_input,
)
from gearcity_optimizer.importers.map_sources import (
    discover_map_sources,
    import_map_from_path,
    resolve_map_for_cli,
)
from gearcity_optimizer.importers.turn_events_parser import load_turn_events_for_map
from gearcity_optimizer.reports.danger_periods import (
    danger_periods_for_map,
    summarize_timeline,
)
from gearcity_optimizer.reports.advisor import (
    explain_candidate,
    explain_component_priorities,
    explain_package,
)
from gearcity_optimizer.core.terminology import (
    DESIGN_SLIDER_SECTION_TITLE,
    FINAL_VEHICLE_RATING_SECTION_TITLE,
    format_audit_entry_text,
    get_verified_terminology_entry,
    list_terminology_entries,
)
from gearcity_optimizer.core.terminology_verification import verify_term_search
from gearcity_optimizer.core.slider_registry import (
    list_sliders,
    registry_sections,
    validate_registry,
)
from gearcity_optimizer.reports.slider_optimizer import (
    SliderOptimizationInput,
    optimize_real_slider_settings,
)
from gearcity_optimizer.ui.slider_audit import format_slider_audit_row
from gearcity_optimizer.reports.design_checklist import (
    build_design_checklist,
    format_checklist_for_cli,
    format_final_vehicle_rating_priorities,
)

SUBCOMMANDS = {
    "run-app",
    "setup-sources",
    "design-checklist",
    "priorities",
    "rank-designs",
    "packages",
    "download-wiki",
    "import-wiki",
    "inspect-sources",
    "formulas",
    "calc-gearboxes",
    "calc-chassis",
    "calc-engines",
    "terminology-audit",
    "import-map",
    "list-maps",
    "danger-periods",
    "events-summary",
    "group-vehicle-types",
    "import-components",
    "tech-availability",
    "slider-audit",
    "optimize-sliders",
}

UNKNOWN_SUBCOMMAND = "__unknown__"


def _default_data_path(relative: str) -> str:
    """Resolve data file path relative to project root."""
    return data_path(relative)


def _format_warnings(warnings: list[str]) -> str:
    """Join warnings for tabular display."""
    return "; ".join(warnings) if warnings else ""


def _resolve_subcommand(argv: list[str] | None) -> tuple[str | None, list[str]]:
    """Detect subcommand while preserving legacy rank-designs invocation."""
    args = argv or []
    if not args:
        return None, []

    first = args[0]
    if first in SUBCOMMANDS:
        return first, args[1:]

    if first.startswith("-"):
        return None, args

    return UNKNOWN_SUBCOMMAND, args


def _get_vehicle_type(
    vehicle_types: dict, name: str | None, required: bool = False
):
    """Look up a vehicle type by name."""
    if name is None:
        if required:
            raise SystemExit("Error: --vehicle-type is required.")
        return None
    vehicle_type = vehicle_types.get(name)
    if vehicle_type is None:
        raise SystemExit(f"Error: unknown vehicle type {name!r}.")
    return vehicle_type


def handle_rank_designs(args: argparse.Namespace) -> int:
    """Rank finished vehicle designs."""
    vehicle_types = load_vehicle_types(args.vehicle_types_file)
    candidates = load_candidate_designs(args.candidate_file)

    results = rank_candidates(
        candidates=candidates,
        vehicle_types=vehicle_types,
        vehicle_type_name=args.vehicle_type,
        year=args.year,
        objective=args.objective,
    )

    if not results:
        print("No matching candidates found.")
        return 0

    display_rows = results[: args.top]
    table = pd.DataFrame(
        [
            {
                "rank": r["rank"],
                "name": r["name"],
                "vehicle_type": r["vehicle_type"],
                "vehicle_type_fit": round(r["vehicle_type_fit"], 2),
                "final_buyer_rating_proxy": round(
                    r["final_buyer_rating_proxy"], 2
                ),
                "value_per_cost": round(r["value_per_cost"], 4),
                "unit_cost": r["unit_cost"],
                "sale_price": r["sale_price"],
                "warnings": _format_warnings(r["warnings"]),
            }
            for r in display_rows
        ]
    )

    title_parts = [f"objective={args.objective}", f"year={args.year}"]
    if args.vehicle_type:
        title_parts.append(f"vehicle_type={args.vehicle_type}")

    print(f"\nRanked designs ({', '.join(title_parts)})\n")
    print(table.to_string(index=False))

    print("\n--- Advisor comments for top 3 ---\n")
    for row in display_rows[:3]:
        candidate = next(c for c in candidates if c.name == row["name"])
        vehicle_type = vehicle_types[candidate.vehicle_type]
        score = calculate_value_score(candidate, vehicle_type, year=args.year)
        comments = explain_candidate(candidate, vehicle_type, score)

        print(f"#{row['rank']} {row['name']}")
        for comment in comments:
            print(f"  - {comment}")
        print()

    return 0


def _print_priority_section(
    title: str, priorities: list, component: str
) -> None:
    """Print a ranked priority list for one component category."""
    print(f"\n{title}:")
    for index, item in enumerate(priorities, start=1):
        label = format_stat_label(component, item.stat)
        print(f"  {index}. {label} - {item.priority:.0f}")


def handle_priorities(args: argparse.Namespace) -> int:
    """Show component stat priorities for a vehicle type."""
    vehicle_types = load_vehicle_types(args.vehicle_types_file)
    vehicle_type = _get_vehicle_type(
        vehicle_types, args.vehicle_type, required=True
    )

    adjusted = get_adjusted_vehicle_weights(vehicle_type)
    priorities = calculate_component_priorities(vehicle_type)

    print(f"\nSelected vehicle type: {vehicle_type.name}\n")
    print(f"{FINAL_VEHICLE_RATING_SECTION_TITLE}:")
    for line in format_final_vehicle_rating_priorities(adjusted):
        print(f"  {line}")

    _print_priority_section("Chassis focus", priorities["chassis"], "chassis")
    _print_priority_section("Engine focus", priorities["engine"], "engine")
    _print_priority_section("Gearbox focus", priorities["gearbox"], "gearbox")
    _print_priority_section(
        DESIGN_SLIDER_SECTION_TITLE,
        priorities["vehicle_design"],
        "vehicle_design",
    )

    print("\n--- Advisor comments ---\n")
    for comment in explain_component_priorities(vehicle_type, priorities):
        print(f"  - {comment}")
    print()

    return 0


def handle_design_checklist(args: argparse.Namespace) -> int:
    """Show a practical vehicle design checklist for a vehicle type."""
    vehicle_types = load_vehicle_types(args.vehicle_types_file)
    vehicle_type = _get_vehicle_type(
        vehicle_types, args.vehicle_type, required=True
    )

    report = build_design_checklist(vehicle_type, year=args.year)
    print()
    print(format_checklist_for_cli(report))

    if args.output_markdown:
        output_path = Path(args.output_markdown)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report.markdown, encoding="utf-8")
        print(f"\nWrote Markdown checklist: {output_path}")

    return 0


def _format_fit_debug(debug: dict | None, indent: str = "  ") -> str:
    """Format package fit debug contributions for CLI output."""
    if not debug:
        return ""

    lines: list[str] = []

    if debug.get("final_formula_fit_score") is not None:
        lines.append(f"{indent}Formula scoring:")
        lines.append(
            f"{indent}  component_package_score: "
            f"{debug.get('component_package_score', 0):.2f}"
        )
        lines.append(
            f"{indent}  assembly_vehicle_type_fit: "
            f"{debug.get('assembly_vehicle_type_fit', 0):.2f}"
        )
        lines.append(
            f"{indent}  assembly_overall: {debug.get('assembly_overall', 0):.2f}"
        )
        lines.append(
            f"{indent}  assembly_quality: {debug.get('assembly_quality', 0):.2f}"
        )
        lines.append(
            f"{indent}  final_formula_fit_score: "
            f"{debug.get('final_formula_fit_score', 0):.2f}"
        )
        lines.append(
            f"{indent}  final_formula_value_score: "
            f"{debug.get('final_formula_value_score', 0):.4f}"
        )
        lines.append("")

    weights = debug.get("component_weights", {})
    if weights:
        lines.append(
            f"{indent}Component weights: chassis={weights.get('chassis', 0):.3f}, "
            f"engine={weights.get('engine', 0):.3f}, "
            f"gearbox={weights.get('gearbox', 0):.3f}"
        )
    lines.append(
        f"{indent}Component fits: chassis={debug.get('chassis_fit', 0):.2f}, "
        f"engine={debug.get('engine_fit', 0):.2f}, "
        f"gearbox={debug.get('gearbox_fit', 0):.2f}"
    )

    cost = debug.get("cost_breakdown")
    if cost:
        proxy = debug.get("proxy_cost_used", False)
        label = "proxy" if proxy else "actual"
        lines.append(
            f"{indent}Unit costs ({label}): chassis={cost.get('chassis', 0):.0f}, "
            f"engine={cost.get('engine', 0):.0f}, "
            f"gearbox={cost.get('gearbox', 0):.0f}"
        )

    assembly = debug.get("assembly_ratings")
    if assembly:
        lines.append(
            f"{indent}Assembly ratings: "
            + ", ".join(f"{k}={v:.1f}" for k, v in sorted(assembly.items()))
        )

    for component in ("chassis", "engine", "gearbox"):
        comp_debug = debug.get(component)
        if not comp_debug:
            continue
        stat_lines = [
            f"{k}={v:.2f}"
            for k, v in sorted(comp_debug.items())
            if k not in {"component"} and isinstance(v, (int, float))
        ]
        if stat_lines:
            lines.append(
                f"{indent}{component} stat contributions: {', '.join(stat_lines[:6])}"
            )

    return "\n".join(lines)


def handle_packages(args: argparse.Namespace) -> int:
    """Rank chassis + engine + gearbox packages for a vehicle type."""
    vehicle_types = load_vehicle_types(args.vehicle_types_file)
    vehicle_type = _get_vehicle_type(
        vehicle_types, args.vehicle_type, required=True
    )

    chassis_list = load_chassis_candidates(args.chassis_file)
    engine_list = load_engine_candidates(args.engine_file)
    gearbox_list = load_gearbox_candidates(args.gearbox_file)

    packages = rank_component_packages(
        chassis_list=chassis_list,
        engine_list=engine_list,
        gearbox_list=gearbox_list,
        vehicle_type=vehicle_type,
        objective=args.objective,
        top=args.top,
        year=args.year,
    )

    if not packages:
        print("No valid component packages found.")
        return 0

    table = pd.DataFrame(
        [
            {
                "rank": index,
                "chassis": package.chassis_name,
                "engine": package.engine_name,
                "gearbox": package.gearbox_name,
                "package_score": round(package.package_score, 2),
                "package_value_score": round(package.package_value_score, 4),
                "total_unit_cost": package.total_unit_cost,
                "warnings": _format_warnings(package.warnings),
            }
            for index, package in enumerate(packages, start=1)
        ]
    )

    print(
        f"\nComponent packages (vehicle_type={vehicle_type.name}, "
        f"objective={args.objective}, year={args.year})\n"
    )
    print(table.to_string(index=False))

    if args.debug_fit:
        print("\n--- Package fit debug (top 3) ---\n")
        for index, package in enumerate(packages[:3], start=1):
            print(
                f"#{index} {package.chassis_name} + {package.engine_name} + "
                f"{package.gearbox_name}"
            )
            print(_format_fit_debug(package.fit_debug))
            print()

    print("\n--- Advisor comments for top 3 packages ---\n")
    for index, package in enumerate(packages[:3], start=1):
        print(f"#{index} {package.chassis_name} + {package.engine_name} + {package.gearbox_name}")
        for comment in explain_package(package, vehicle_type):
            print(f"  - {comment}")
        print()

    return 0


def handle_download_wiki(args: argparse.Namespace) -> int:
    """Download configured GearCity Wiki pages."""
    results = download_wiki_pages(
        urls_file=args.urls_file,
        force=args.force,
        delay_seconds=args.delay,
    )

    downloaded = [r["name"] for r in results if r["downloaded"]]
    skipped = [r["name"] for r in results if r.get("skipped")]
    failures = [(r["name"], r["errors"]) for r in results if r.get("errors")]

    print("GearCity Wiki download complete.\n")
    print("Downloaded:", ", ".join(downloaded) if downloaded else "(none, cached)")
    if skipped:
        print("Skipped (cached):", ", ".join(sorted(set(skipped))))
    if failures:
        print("\nFailures:")
        for name, errors in failures:
            print(f"  {name}: {'; '.join(errors)}")
        print(
            "\nWiki download failed for one or more pages. "
            "Check your network connection and retry:"
        )
        print("  gearcity-optimizer setup-sources")
        return 1
    print(
        "\nManifest:",
        _default_data_path("generated/raw_parsed/wiki_download_manifest.json"),
    )
    return 0


def handle_import_wiki(args: argparse.Namespace) -> int:
    """Parse cached GearCity Wiki pages."""
    summary = import_wiki_pages(
        urls_file=args.urls_file,
        existing_vehicle_types_csv=args.vehicle_types_file,
        debug=args.debug,
    )

    print("GearCity Wiki import complete.\n")
    if summary["missing_sources"]:
        print("Missing cached sources:", ", ".join(summary["missing_sources"]))
        print(
            "\nWiki import failed because cached source files are missing. "
            "Run download-wiki first, or retry:"
        )
        print("  gearcity-optimizer setup-sources")
        return 1

    if not summary["parsed"]:
        print("No wiki pages were parsed.")
        print("  gearcity-optimizer setup-sources")
        return 1

    for page in summary["parsed"]:
        print(
            f"  {page['name']}: {page['tables']} tables, "
            f"{page['formula_chunks']} formula chunks, "
            f"{page['formula_sections']} formula sections"
        )

    if summary.get("formula_index_path"):
        print(f"\nFormula index: {summary['formula_index_path']}")
        for page_name, count in summary.get("formula_index_counts", {}).items():
            print(f"  - {page_name}: {count} sections")

    if summary.get("vehicle_types_from_wiki"):
        rows = summary.get("vehicle_types_row_count", "?")
        print(f"\nVehicle types CSV: {summary['vehicle_types_from_wiki']} ({rows} rows)")

    comparison = summary.get("vehicle_type_comparison")
    if comparison:
        print(f"\nVehicle type table match: {comparison['match']}")
        print(f"  Missing: {comparison.get('missing_count', 0)}")
        print(f"  Extra: {comparison.get('extra_count', 0)}")
        print(f"  Changed: {comparison.get('changed_count', 0)}")
    if summary.get("vehicle_type_comparison_path"):
        print(f"Comparison JSON: {summary['vehicle_type_comparison_path']}")
    return 0


def handle_setup_sources(args: argparse.Namespace) -> int:
    """Download, import, and inspect wiki sources (fresh-clone helper)."""
    print("GearCity Optimizer source setup\n")

    print("Step 1/3: Downloading configured GearCity Wiki pages...")
    result = handle_download_wiki(args)
    if result != 0:
        print("\nSetup failed during wiki download.")
        return result
    print()

    print("Step 2/3: Importing/parsing wiki pages...")
    result = handle_import_wiki(args)
    if result != 0:
        print("\nSetup failed during wiki import.")
        return result
    print()

    print("Step 3/3: Inspecting local source cache...")
    result = handle_inspect_sources(args)
    if result != 0:
        print("\nSetup failed during source inspection.")
        return result

    print("\nSetup complete. Wiki cache and parser outputs are ready.")
    print("Start the UI with: gearcity-optimizer run-app")
    return 0


def build_streamlit_run_command(
    *,
    app_path: Path | None = None,
    root: Path | None = None,
) -> list[str]:
    """Build the subprocess command used by run-app."""
    base = root or project_root_from_module()
    app = app_path or (base / "streamlit_app.py")
    return [sys.executable, "-m", "streamlit", "run", str(app)]


def handle_run_app(args: argparse.Namespace) -> int:
    """Launch the Streamlit design checklist UI."""
    try:
        import streamlit  # noqa: F401
    except ImportError:
        print("Streamlit is not installed. Run:")
        print("  pip install -e .")
        print("or")
        print("  pip install -e '.[dev]'")
        return 1

    cmd = build_streamlit_run_command()
    print("Starting GearCity Vehicle Design Helper...")
    print(" ".join(cmd))
    return subprocess.call(cmd)


def _print_vehicle_type_changes(comparison: dict) -> None:
    """Print readable changed-value details from a comparison result."""
    changed = comparison.get("changed_values", [])
    if not changed:
        return
    print("\nChanged vehicle type values:")
    for item in changed:
        print(
            f"  * {item['vehicle_type']} / {item['column']}: "
            f"data={item['existing']}, wiki={item['generated']}"
        )


def _load_comparison_json(path: Path) -> dict | None:
    """Load vehicle type comparison JSON if present."""
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def handle_formulas(args: argparse.Namespace) -> int:
    """Browse and search parsed wiki formula sections."""
    try:
        index = load_formula_index(args.formula_index)
    except FormulaIndexError as exc:
        print(exc)
        return 1

    if args.export_markdown:
        out = export_formula_markdown(index)
        print(f"Exported formula index to: {out}")
        return 0

    if args.list_pages:
        print("Formula pages:")
        for page in list_formula_pages(index):
            print(f"  - {page}")
        return 0

    if args.page and args.list_sections:
        try:
            sections = list_formula_sections(index, args.page)
        except FormulaIndexError as exc:
            print(exc)
            return 1
        print(f"Sections in {args.page}:")
        for section in sections:
            print(f"  - {section}")
        return 0

    if args.search:
        try:
            results = search_formulas(index, args.search, page_name=args.page)
        except FormulaIndexError as exc:
            print(exc)
            return 1

        if not results:
            print(f"No matches for {args.search!r}.")
            return 0

        for result in results:
            print(f"\n{result['page']} / {result['section']}")
            if args.full:
                print(result["text"])
            elif result["matching_lines"]:
                for line in result["matching_lines"]:
                    print(f"  {line}")
            else:
                print(excerpt_text(result["text"]))
        return 0

    if args.page and args.section:
        try:
            text = get_formula_section(index, args.page, args.section)
        except FormulaIndexError as exc:
            print(exc)
            return 1
        print(text)
        return 0

    print(
        "Specify an action: --list-pages, --list-sections, --search, "
        "--section, or --export-markdown"
    )
    return 1


def handle_inspect_sources(args: argparse.Namespace) -> int:
    """Inspect downloaded and parsed wiki sources."""
    root = project_root_from_module()
    manifest_path = root / "generated/raw_parsed/wiki_download_manifest.json"
    formula_index_path = root / "generated/raw_parsed/wiki_formula_index.json"
    wiki_csv_path = root / "generated/normalized/vehicle_types_from_wiki.csv"
    existing_csv_path = Path(args.vehicle_types_file)

    print("GearCity Wiki source inspection\n")

    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        print("Downloaded wiki pages:")
        for page in manifest.get("pages", []):
            status = "cached" if page.get("skipped") else "downloaded"
            if page.get("downloaded"):
                status = "downloaded"
            elif page.get("skipped"):
                status = "cached"
            print(f"  - {page['name']} ({status})")
            print(f"      {page['url']}")
            if page.get("errors"):
                print(f"      errors: {len(page['errors'])}")
    else:
        print(
            "No download manifest found. This is normal for a fresh clone. "
            "Run: download-wiki"
        )

    parsed_dir = root / "generated/raw_parsed"
    if not parsed_dir.exists():
        print(f"\n{GENERATED_FILES_MISSING_MSG}")
        parsed_files = []
    else:
        parsed_files = sorted(
            path for path in parsed_dir.glob("wiki_*.json") if is_wiki_page_json(path)
        )

    print(f"\nParsed pages: {len(parsed_files)}")
    total_tables = 0
    total_formulas = 0
    total_formula_sections = 0
    for path in parsed_files:
        data = json.loads(path.read_text(encoding="utf-8"))
        tables = len(data.get("tables", []))
        formulas = len(data.get("formula_chunks", []))
        formula_sections = len(data.get("formula_sections", {}))
        total_tables += tables
        total_formulas += formulas
        total_formula_sections += formula_sections
        print(
            f"  - {path.name}: {tables} tables, {formulas} formula chunks, "
            f"{formula_sections} formula sections"
        )

    print(
        f"\nTotals: {total_tables} tables, {total_formulas} formula chunks, "
        f"{total_formula_sections} formula sections"
    )

    comparison_path = root / "generated/raw_parsed/vehicle_type_table_comparison.json"

    if formula_index_path.exists():
        index = json.loads(formula_index_path.read_text(encoding="utf-8"))
        print("\nFormula index sections:")
        for page_name, sections in index.items():
            count = len(sections)
            print(f"  - {page_name}: {count} sections")
            if count == 0:
                print(
                    f"    WARNING: Formula sections for {page_name} are empty. "
                    "Re-run import-wiki --debug and inspect parser output."
                )
    else:
        print(f"\n{FORMULA_INDEX_MISSING_MSG}")

    print("\nNormalized files:")
    if wiki_csv_path.exists():
        row_count = len(pd.read_csv(wiki_csv_path))
        print(f"  - {wiki_csv_path} ({row_count} rows)")
    else:
        print("  - generated/normalized/vehicle_types_from_wiki.csv (missing)")
        print(GENERATED_FILES_MISSING_MSG)

    print("\nVehicle type comparison:")
    comparison = _load_comparison_json(comparison_path)
    if comparison is None and wiki_csv_path.exists() and existing_csv_path.exists():
        comparison = compare_vehicle_type_tables(existing_csv_path, wiki_csv_path)

    if comparison is not None:
        print(f"  Exact match: {comparison['match']}")
        print(
            f"  Missing rows: "
            f"{comparison.get('missing_count', len(comparison.get('missing_vehicle_types', [])))}"
        )
        print(
            f"  Extra rows: "
            f"{comparison.get('extra_count', len(comparison.get('extra_vehicle_types', [])))}"
        )
        print(
            f"  Changed values: "
            f"{comparison.get('changed_count', len(comparison.get('changed_values', [])))}"
        )
        _print_vehicle_type_changes(comparison)
        if comparison_path.exists():
            print(f"  Comparison JSON: {comparison_path}")
    else:
        print("  Not available (run import-wiki first)")

    return 0


def handle_calc_gearboxes(args: argparse.Namespace) -> int:
    """Calculate gearbox specs and ratings from wiki formulas."""
    inputs_list = load_gearbox_formula_inputs(args.input_file)
    if args.year is not None:
        inputs_list = [replace(item, year=args.year) for item in inputs_list]

    rows: list[tuple[GearboxFormulaInputs, Any]] = []
    table_rows = []
    for inputs in inputs_list:
        result = calculate_gearbox(inputs)
        rows.append((inputs, result))
        table_rows.append(
            {
                "name": inputs.name,
                "max_torque_support": round(result.max_torque_support, 2),
                "weight": round(result.weight, 2),
                "power_rating": round(result.power_rating, 2),
                "fuel_economy_rating": round(result.fuel_economy_rating, 2),
                "performance_rating": round(result.performance_rating, 2),
                "reliability_rating": round(result.reliability_rating, 2),
                "comfort_rating": round(result.comfort_rating, 2),
                "overall_rating": round(result.overall_rating, 2),
                "manufacturing_requirements": round(
                    result.manufacturing_requirements, 2
                ),
                "design_requirements": round(result.design_requirements, 2),
                "warnings": _format_warnings(result.warnings),
            }
        )

    print(f"\nGearbox formula results (year={args.year or 'from input'})\n")
    print(pd.DataFrame(table_rows).to_string(index=False))

    if args.output_file:
        export_gearbox_candidates_csv(rows, args.output_file)
        print(f"\nExported package-compatible CSV: {args.output_file}")

    return 0


def handle_calc_chassis(args: argparse.Namespace) -> int:
    """Calculate chassis specs and ratings from wiki formulas."""
    inputs_list = load_chassis_formula_inputs(args.input_file)
    if args.year is not None:
        inputs_list = [replace(item, year=args.year) for item in inputs_list]

    table_rows = []
    for inputs in inputs_list:
        result = calculate_chassis(inputs)
        table_rows.append(
            {
                "name": inputs.name,
                "chassis_length": round(result.chassis_length, 2),
                "chassis_width": round(result.chassis_width, 2),
                "chassis_weight": round(result.chassis_weight, 2),
                "max_engine_length": round(result.max_engine_length, 2),
                "max_engine_width": round(result.max_engine_width, 2),
                "comfort_rating": round(result.comfort_rating, 2),
                "performance_rating": round(result.performance_rating, 2),
                "strength_rating": round(result.strength_rating, 2),
                "durability_rating": round(result.durability_rating, 2),
                "overall_rating": round(result.overall_rating, 2),
                "design_requirements": round(result.design_requirements, 2),
                "manufacturing_requirements": round(
                    result.manufacturing_requirements, 2
                ),
                "warnings": _format_warnings(result.warnings),
            }
        )

    print(f"\nChassis formula results (year={args.year or 'from input'})\n")
    print(pd.DataFrame(table_rows).to_string(index=False))

    if args.output_file:
        export_chassis_candidates_csv(
            inputs_list, args.output_file, year_override=args.year
        )
        print(f"\nExported package-compatible CSV: {args.output_file}")

    return 0


def handle_calc_engines(args: argparse.Namespace) -> int:
    """Calculate engine specs and ratings from wiki formulas."""
    inputs_list = load_engine_formula_inputs(args.input_file)
    if args.year is not None:
        inputs_list = [replace(item, year=args.year) for item in inputs_list]

    table_rows = []
    for inputs in inputs_list:
        result = calculate_engine(inputs)
        table_rows.append(
            {
                "name": inputs.name,
                "horsepower": round(result.horsepower, 2),
                "torque": round(result.torque, 2),
                "fuel_economy": round(result.fuel_economy, 2),
                "reliability_rating": round(result.reliability_rating, 2),
                "smoothness_rating": round(result.smoothness_rating, 2),
                "performance_rating": round(result.performance_rating, 2),
                "overall_rating": round(result.overall_rating, 2),
                "weight": round(result.weight, 2),
                "width": round(result.width, 2),
                "length": round(result.length, 2),
                "design_requirements": round(result.design_requirements, 2),
                "manufacturing_requirements": round(
                    result.manufacturing_requirements, 2
                ),
                "warnings": _format_warnings(result.warnings),
            }
        )

    print(f"\nEngine formula results (year={args.year or 'from input'})\n")
    print(pd.DataFrame(table_rows).to_string(index=False))

    if args.output_file:
        export_engine_candidates_csv(
            inputs_list, args.output_file, year_override=args.year
        )
        print(f"\nExported package-compatible CSV: {args.output_file}")

    return 0


def handle_import_map(args: argparse.Namespace) -> int:
    """Import a map TurnEvents.xml file into user_data/maps/."""
    source = import_map_from_path(
        map_id=args.id,
        name=args.name,
        source_path=args.turn_events,
        description=args.description,
        overwrite=args.overwrite,
    )
    print(f"Imported map {source.id!r} ({source.name})")
    print(f"Saved TurnEvents.xml to {source.turn_events_file}")
    return 0


def handle_list_maps(args: argparse.Namespace) -> int:
    """List imported map timelines."""
    sources = discover_map_sources()
    if not sources:
        print("No map timelines imported yet.")
        print(
            "Import one with:\n"
            "  gearcity-optimizer import-map --id base_city "
            '--name "Base City Map" --turn-events "<path-to-TurnEvents.xml>"'
        )
        return 0

    print(f"\nImported maps ({len(sources)})\n")
    for source in sources:
        print(f"- {source.id}: {source.name}")
        print(f"  path: {source.path}")
        print(f"  turn events: {source.turn_events_file}")
        print(f"  kind: {source.source_kind}")
    return 0


def handle_danger_periods(args: argparse.Namespace) -> int:
    """Print map-specific danger periods from imported TurnEvents data."""
    map_source = resolve_map_for_cli(args.map)
    periods = danger_periods_for_map(map_source)
    print(f"\n{map_source.name} danger periods\n")
    if not periods:
        print("No elevated danger periods detected.")
        return 0

    for period in periods:
        print(
            f"- {period.start_year} turn {period.start_turn} to "
            f"{period.end_year} turn {period.end_turn}: "
            f"{period.label} [{period.danger_type}, {period.severity}]"
        )
        print(f"  map: {period.map_name} ({period.map_id})")
        print(f"  supporting turns: {', '.join(period.supporting_events[:5])}")
        if len(period.supporting_events) > 5:
            print(f"  ... and {len(period.supporting_events) - 5} more")
    return 0


def handle_events_summary(args: argparse.Namespace) -> int:
    """Print a compact summary of one map timeline."""
    map_source = resolve_map_for_cli(args.map)
    timeline = load_turn_events_for_map(map_source)
    summary = summarize_timeline(timeline)
    print(f"\n{map_source.name} events summary\n")
    for key, value in summary.items():
        print(f"- {key}: {value}")
    return 0


def handle_import_components(args: argparse.Namespace) -> int:
    """Import a GearCity Components.xml file into user_data/game_files/components/."""
    source = import_components_from_path(
        args.components,
        name=args.name,
        overwrite=args.overwrite,
    )
    print(f"Imported Components catalog {source.name!r}")
    print(f"Saved Components.xml to {source.components_file}")
    return 0


def handle_tech_availability(args: argparse.Namespace) -> int:
    """Print available and locked components for a year and skill profile."""
    try:
        validate_year_input(args.year)
    except ValueError as exc:
        raise SystemExit(f"Error: {exc}") from exc

    catalog = load_imported_components_catalog()
    if catalog is None:
        raise SystemExit(components_missing_message())

    skill_levels = {
        "chassis": args.chassis_skill,
        "engine": args.engine_skill,
        "gearbox": args.gearbox_skill,
        "vehicle": args.vehicle_skill,
    }
    category = args.category
    available_rows, locked_rows = classify_components(
        catalog,
        args.year,
        skill_levels,
        category_filter=category,
        name_search=args.search,
    )

    summary = catalog_summary(catalog)
    print(f"\nTech availability for year {args.year}\n")
    print(f"Catalog entries: {len(catalog.components)}")
    if summary:
        print(
            "Categories: "
            + ", ".join(f"{key}={count}" for key, count in sorted(summary.items()))
        )
    print(f"\nAvailable ({len(available_rows)})")
    for row in available_rows[: args.limit]:
        component = row.component
        print(
            f"- {component.name} [{component.category}/{component.subcategory}] "
            f"skill={component.required_skill} start={component.start_year}"
        )
    if len(available_rows) > args.limit:
        print(f"  ... and {len(available_rows) - args.limit} more")

    print(f"\nLocked / unavailable ({len(locked_rows)})")
    for row in locked_rows[: args.limit]:
        component = row.component
        print(
            f"- {component.name} [{component.category}/{component.subcategory}] "
            f"{row.status}: {row.reason}"
        )
    if len(locked_rows) > args.limit:
        print(f"  ... and {len(locked_rows) - args.limit} more")

    if args.vehicle_type:
        vehicle_types = load_vehicle_types(args.vehicle_types_file)
        if args.vehicle_type not in vehicle_types:
            raise SystemExit(f"Unknown vehicle type: {args.vehicle_type!r}")
        vehicle_type = vehicle_types[args.vehicle_type]
        rec_input = RecommendationInput(
            vehicle_type_name=args.vehicle_type,
            year=args.year,
            cost_mode=args.cost_mode,
            chassis_skill=args.chassis_skill,
            engine_skill=args.engine_skill,
            gearbox_skill=args.gearbox_skill,
            vehicle_skill=args.vehicle_skill,
        )
        result = build_recommendation_result(
            vehicle_type=vehicle_type,
            inputs=rec_input,
            catalog=catalog,
        )
        print(f"\nRecommendation preview for {args.vehicle_type} ({args.cost_mode})\n")
        print(result.strategy_summary)
        print(f"\nAvoid:")
        for item in result.avoid:
            print(f"- {item}")
        print(f"\n{result.gearbox_guidance}")
        for note in result.limitations:
            print(f"  note: {note}")

    return 0


def handle_slider_audit(args: argparse.Namespace) -> int:
    """Print the real controllable slider/input registry."""
    warnings = validate_registry()
    section = args.section
    sliders = list_sliders(section=section)

    print("\nReal GearCity slider/input audit\n")
    if section:
        print(f"Section filter: {section}")
    else:
        print(f"Sections: {', '.join(registry_sections())}")
    print(f"Entries: {len(sliders)}\n")

    for warning in warnings:
        print(f"  warning: {warning}")

    for slider in sliders:
        row = format_slider_audit_row(slider)
        print(f"- {row['key']} ({row['section']})")
        print(f"  label: {row['label']}")
        print(f"  formula variable: {row['formula variable']}")
        print(f"  range: {row['range']}")
        print(f"  affected outputs: {row['affected outputs']}")
        print(f"  confidence: {row['confidence']}")
        print(f"  source: {row['source']}")
    return 0


def handle_optimize_sliders(args: argparse.Namespace) -> int:
    """Recommend real slider settings and show predicted output stats."""
    try:
        validate_year_input(args.year)
    except ValueError as exc:
        raise SystemExit(f"Error: {exc}") from exc

    vehicle_types = load_vehicle_types(args.vehicle_types_file)
    if args.vehicle_type not in vehicle_types:
        raise SystemExit(f"Unknown vehicle type: {args.vehicle_type!r}")

    vehicle_type = vehicle_types[args.vehicle_type]
    result = optimize_real_slider_settings(
        SliderOptimizationInput(
            vehicle_type=vehicle_type,
            year=args.year,
            cost_mode=args.cost_mode,
            chassis_skill=args.chassis_skill,
            engine_skill=args.engine_skill,
            gearbox_skill=args.gearbox_skill,
            vehicle_skill=args.vehicle_skill,
            depth=args.depth,
        )
    )

    print(f"\nModel-optimized slider settings for {args.vehicle_type} ({args.cost_mode})\n")
    print("Actual controls to set:\n")
    current_section = None
    for setting in result.control_settings:
        if setting.section != current_section:
            current_section = setting.section
            print(f"[{current_section}]")
        print(
            f"  {setting.label}: {setting.value} "
            f"({setting.formula_variable or 'n/a'}, {setting.confidence})"
        )
        print(f"    reason: {setting.reason}")

    print("\nPredicted output stats:\n")
    for output in result.predicted_outputs:
        proxy = " [proxy]" if output.is_proxy else ""
        print(
            f"  {output.label}: {output.value:.2f} "
            f"(importance {output.target_weight:.3f}){proxy}"
        )

    print("\nTradeoffs:")
    for item in result.tradeoffs:
        print(f"  - {item}")

    print("\nLimitations:")
    for item in result.limitations:
        print(f"  - {item}")

    if result.warnings:
        print("\nWarnings:")
        for item in result.warnings:
            print(f"  - {item}")

    return 0


def handle_group_vehicle_types(args: argparse.Namespace) -> int:
    """Cluster vehicle types by design-stat importance weights."""
    vehicle_types_dict = load_vehicle_types(args.vehicle_types_file)
    vehicle_types = list(vehicle_types_dict.values())

    if args.show_similar_to:
        try:
            similar = find_most_similar_vehicle_types(
                args.show_similar_to,
                vehicle_types,
                top_n=args.top,
            )
        except ValueError as exc:
            raise SystemExit(f"Error: {exc}") from exc

        print(f"\nMost similar to {args.show_similar_to}:\n")
        if not similar:
            print("No other vehicle types to compare.")
            return 0

        for index, (name, score) in enumerate(similar, start=1):
            print(f"{index}. {name} - {score:.1f}")
        print()
        return 0

    try:
        groups = cluster_vehicle_types(vehicle_types, args.groups)
    except ValueError as exc:
        raise SystemExit(f"Error: {exc}") from exc

    print(f"\nVehicle type groups, k={args.groups}\n")
    for group in groups:
        top_labels = ", ".join(stat for stat, _ in group.top_priorities)
        print(f"Group {group.group_id}: {group.description}")
        print(f"Top priorities: {top_labels}")
        print("Vehicle types:")
        for name in group.vehicle_types:
            print(f"  - {name}")

        if args.show_centroids:
            print("Centroid:")
            for stat in sorted(group.centroid.keys()):
                print(f"  {stat}: {group.centroid[stat]:.3f}")
        print()

    return 0


def handle_terminology_audit(args: argparse.Namespace) -> int:
    """Search or list evidence-backed terminology mappings."""
    if args.term:
        evidence, note = verify_term_search(args.term, full=args.full)
        print(f"\nTerm search: {args.term}\n")
        print(note)
        print("")
        if not evidence:
            return 0
        for item in evidence:
            print(f"  * [{item.source_type}] {item.source_file}")
            print(f"    matched: {item.matched_text!r}")
            print(f"    context: {item.context}")
            print("")
        lowered = args.term.lower()
        if lowered in {"handling", "drivability", "driveability"}:
            entry = get_verified_terminology_entry("vehicle", "drivability")
            print(format_audit_entry_text(entry, full=args.full))
        return 0

    entries = list_terminology_entries()
    print(f"\nTerminology audit ({len(entries)} entries)\n")
    for entry in entries:
        if args.full:
            print(format_audit_entry_text(entry, full=True))
        else:
            mapping = entry.formula_label
            if entry.observed_game_label:
                mapping = f"{entry.formula_label} vs {entry.observed_game_label}"
            print(
                f"- [{entry.component}.{entry.internal_key}] {mapping} "
                f"-> {entry.display_label} ({entry.status}, "
                f"{len(entry.evidence)} evidence)"
            )
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser and all subcommand parsers."""
    parser = argparse.ArgumentParser(
        description="GearCity vehicle design helper and component advisor.",
        epilog=(
            "Main workflow:\n"
            "  run-app           Start the Streamlit design checklist UI\n"
            "  setup-sources     Download and parse wiki references (fresh clone)\n"
            "  design-checklist  Print a practical vehicle design checklist\n"
            "  priorities        Show component stat priorities for a vehicle type\n"
            "\n"
            "Fresh clone: pip install -e \".[dev]\" && gearcity-optimizer setup-sources\n"
            "Daily use:   gearcity-optimizer run-app"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")

    run_app_parser = subparsers.add_parser(
        "run-app",
        help="Start the Streamlit design checklist UI",
    )
    setup_sources_parser = subparsers.add_parser(
        "setup-sources",
        help="Download, import, and inspect wiki sources (fresh-clone setup)",
    )
    design_checklist_parser = subparsers.add_parser(
        "design-checklist",
        help="Show a practical vehicle design checklist for a vehicle type",
    )
    priorities_parser = subparsers.add_parser(
        "priorities",
        help="Show component stat priorities for a vehicle type",
    )
    packages_parser = subparsers.add_parser(
        "packages",
        help="Rank chassis + engine + gearbox combinations",
    )
    rank_parser = subparsers.add_parser(
        "rank-designs",
        help="Rank finished vehicle designs (default mode)",
    )
    download_wiki_parser = subparsers.add_parser(
        "download-wiki",
        help="Download configured GearCity Wiki pages",
    )
    import_wiki_parser = subparsers.add_parser(
        "import-wiki",
        help="Parse cached GearCity Wiki pages",
    )
    inspect_sources_parser = subparsers.add_parser(
        "inspect-sources",
        help="Inspect downloaded and parsed wiki sources",
    )
    formulas_parser = subparsers.add_parser(
        "formulas",
        help="Browse and search parsed wiki formula sections",
    )

    for sub in (rank_parser, priorities_parser, design_checklist_parser, packages_parser):
        sub.add_argument(
            "--vehicle-type",
            default=None,
            help="Vehicle type name (required for priorities/design-checklist/packages)",
        )
        sub.add_argument(
            "--vehicle-types-file",
            default=_default_data_path(DEFAULT_VEHICLE_TYPES),
            help="Path to vehicle types CSV",
        )

    for sub in (rank_parser, packages_parser):
        sub.add_argument(
            "--year",
            type=int,
            default=1901,
            help="Simulation year (default: 1901)",
        )
        sub.add_argument(
            "--top",
            type=int,
            default=20,
            help="Number of results to display (default: 20)",
        )

    design_checklist_parser.add_argument(
        "--year",
        type=int,
        default=1901,
        help="Simulation year (default: 1901)",
    )
    design_checklist_parser.add_argument(
        "--output-markdown",
        default=None,
        help="Optional path to write the checklist as Markdown",
    )

    rank_parser.add_argument(
        "--objective",
        choices=VALID_OBJECTIVES,
        default="balanced",
        help="Ranking objective (default: balanced)",
    )
    rank_parser.add_argument(
        "--candidate-file",
        default=_default_data_path(DEFAULT_CANDIDATES),
        help="Path to candidate designs CSV",
    )

    packages_parser.add_argument(
        "--objective",
        choices=PACKAGE_OBJECTIVES,
        default="balanced",
        help="Package ranking objective (default: balanced)",
    )
    packages_parser.add_argument(
        "--chassis-file",
        default=_default_data_path(DEFAULT_CHASSIS),
        help="Path to chassis candidates CSV",
    )
    packages_parser.add_argument(
        "--engine-file",
        default=_default_data_path(DEFAULT_ENGINES),
        help="Path to engine candidates CSV",
    )
    packages_parser.add_argument(
        "--gearbox-file",
        default=_default_data_path(DEFAULT_GEARBOXES),
        help="Path to gearbox candidates CSV",
    )
    packages_parser.add_argument(
        "--debug-fit",
        action="store_true",
        help="Show numeric stat contributions to package score",
    )

    for sub in (setup_sources_parser, download_wiki_parser, import_wiki_parser):
        sub.add_argument(
            "--urls-file",
            default=_default_data_path("sources/wiki_urls.json"),
            help="JSON file listing wiki URLs",
        )

    for sub in (download_wiki_parser, setup_sources_parser):
        sub.add_argument(
            "--force",
            action="store_true",
            help="Redownload even if cached files exist",
        )
        sub.add_argument(
            "--delay",
            type=float,
            default=1.0,
            help="Delay between requests in seconds (default: 1.0)",
        )

    for sub in (import_wiki_parser, setup_sources_parser, inspect_sources_parser):
        sub.add_argument(
            "--vehicle-types-file",
            default=_default_data_path(DEFAULT_VEHICLE_TYPES),
            help="Existing vehicle types CSV for comparison",
        )

    for sub in (import_wiki_parser, setup_sources_parser):
        sub.add_argument(
            "--debug",
            action="store_true",
            help="Print detailed parser diagnostics",
        )

    formulas_parser.add_argument(
        "--list-pages",
        action="store_true",
        help="List available formula pages",
    )
    formulas_parser.add_argument(
        "--page",
        default=None,
        help="Wiki page name (e.g. gearbox_game_mechanics)",
    )
    formulas_parser.add_argument(
        "--list-sections",
        action="store_true",
        help="List sections for the selected page",
    )
    formulas_parser.add_argument(
        "--search",
        default=None,
        help="Search formula text across pages or one page",
    )
    formulas_parser.add_argument(
        "--section",
        default=None,
        help="Show one formula section from the selected page",
    )
    formulas_parser.add_argument(
        "--full",
        action="store_true",
        help="Show full formula text for search results",
    )
    formulas_parser.add_argument(
        "--export-markdown",
        action="store_true",
        help="Export formula index to Markdown",
    )
    formulas_parser.add_argument(
        "--formula-index",
        default=_default_data_path("generated/raw_parsed/wiki_formula_index.json"),
        help="Path to wiki_formula_index.json",
    )

    calc_gearboxes_parser = subparsers.add_parser(
        "calc-gearboxes",
        help="Calculate gearbox specs and ratings from wiki formulas",
    )
    calc_gearboxes_parser.add_argument(
        "--input-file",
        default=_default_data_path("data/gearbox_design_inputs.csv"),
        help="CSV file with gearbox formula inputs",
    )
    calc_gearboxes_parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Override year for all rows",
    )
    calc_gearboxes_parser.add_argument(
        "--output-file",
        default=None,
        help="Export package-compatible gearbox candidates CSV",
    )

    calc_chassis_parser = subparsers.add_parser(
        "calc-chassis",
        help="Calculate chassis specs and ratings from wiki formulas",
    )
    calc_chassis_parser.add_argument(
        "--input-file",
        default=_default_data_path("data/chassis_design_inputs.csv"),
        help="CSV file with chassis formula inputs",
    )
    calc_chassis_parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Override year for all rows",
    )
    calc_chassis_parser.add_argument(
        "--output-file",
        default=None,
        help="Export package-compatible chassis candidates CSV",
    )

    calc_engines_parser = subparsers.add_parser(
        "calc-engines",
        help="Calculate engine specs and ratings from wiki formulas",
    )
    terminology_audit_parser = subparsers.add_parser(
        "terminology-audit",
        help="Audit terminology mappings against local wiki sources",
    )
    terminology_audit_parser.add_argument(
        "--term",
        default=None,
        help="Search one term in local wiki sources",
    )
    terminology_audit_parser.add_argument(
        "--all",
        action="store_true",
        help="List all known terminology entries (default when --term omitted)",
    )
    terminology_audit_parser.add_argument(
        "--full",
        action="store_true",
        help="Show full evidence context",
    )
    calc_engines_parser.add_argument(
        "--input-file",
        default=_default_data_path("data/engine_design_inputs.csv"),
        help="CSV file with engine formula inputs",
    )
    calc_engines_parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Override year for all rows",
    )
    calc_engines_parser.add_argument(
        "--output-file",
        default=None,
        help="Export package-compatible engine candidates CSV",
    )

    import_map_parser = subparsers.add_parser(
        "import-map",
        help="Import a map TurnEvents.xml timeline into user_data/maps/",
    )
    import_map_parser.add_argument(
        "--id",
        required=True,
        help="Map id slug (for example base_city)",
    )
    import_map_parser.add_argument(
        "--name",
        required=True,
        help='Display name (for example "Base City Map")',
    )
    import_map_parser.add_argument(
        "--turn-events",
        required=True,
        help="Path to TurnEvents.xml",
    )
    import_map_parser.add_argument(
        "--description",
        default="Imported GearCity map timeline.",
        help="Optional map description for map.json",
    )
    import_map_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing map with the same id",
    )

    list_maps_parser = subparsers.add_parser(
        "list-maps",
        help="List imported map TurnEvents timelines",
    )

    danger_periods_parser = subparsers.add_parser(
        "danger-periods",
        help="Show map-specific economic danger periods",
    )
    danger_periods_parser.add_argument(
        "--map",
        default=None,
        help="Map id (required when multiple maps are imported)",
    )

    events_summary_parser = subparsers.add_parser(
        "events-summary",
        help="Summarize one imported map timeline",
    )
    events_summary_parser.add_argument(
        "--map",
        default=None,
        help="Map id (required when multiple maps are imported)",
    )

    import_components_parser = subparsers.add_parser(
        "import-components",
        help="Import GearCity Components.xml into user_data/game_files/components/",
    )
    import_components_parser.add_argument(
        "--components",
        required=True,
        help="Path to Components.xml",
    )
    import_components_parser.add_argument(
        "--name",
        default="Default GearCity Components",
        help="Label stored in metadata.json",
    )
    import_components_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing imported Components.xml",
    )

    tech_availability_parser = subparsers.add_parser(
        "tech-availability",
        help="List available and locked components by year and design skill",
    )
    tech_availability_parser.add_argument(
        "--year",
        type=int,
        default=1900,
        help="Game year (minimum 1900)",
    )
    tech_availability_parser.add_argument(
        "--chassis-skill",
        type=float,
        default=0.0,
        help="Chassis design skill (0-100)",
    )
    tech_availability_parser.add_argument(
        "--engine-skill",
        type=float,
        default=0.0,
        help="Engine design skill (0-100)",
    )
    tech_availability_parser.add_argument(
        "--gearbox-skill",
        type=float,
        default=0.0,
        help="Gearbox design skill (0-100)",
    )
    tech_availability_parser.add_argument(
        "--vehicle-skill",
        type=float,
        default=0.0,
        help="Vehicle/coachwork design skill (0-100)",
    )
    tech_availability_parser.add_argument(
        "--category",
        default=None,
        choices=["chassis", "engine", "gearbox", "vehicle", "unknown"],
        help="Optional skill/category filter",
    )
    tech_availability_parser.add_argument(
        "--search",
        default=None,
        help="Optional name search filter",
    )
    tech_availability_parser.add_argument(
        "--vehicle-type",
        default=None,
        help="Optional vehicle type for recommendation preview",
    )
    tech_availability_parser.add_argument(
        "--cost-mode",
        default="balanced",
        choices=["cheap", "balanced", "luxury"],
        help="Cost mode for recommendation preview",
    )
    tech_availability_parser.add_argument(
        "--vehicle-types-file",
        default=_default_data_path(DEFAULT_VEHICLE_TYPES),
        help="Path to vehicle types CSV",
    )
    tech_availability_parser.add_argument(
        "--limit",
        type=int,
        default=25,
        help="Maximum rows to print per section (default: 25)",
    )

    slider_audit_parser = subparsers.add_parser(
        "slider-audit",
        help="List real controllable GearCity sliders/inputs from the formula registry",
    )
    slider_audit_parser.add_argument(
        "--section",
        default=None,
        choices=["chassis", "engine", "gearbox", "vehicle", "testing"],
        help="Optional section filter",
    )

    optimize_sliders_parser = subparsers.add_parser(
        "optimize-sliders",
        help="Recommend real slider values and predict output stats",
    )
    optimize_sliders_parser.add_argument(
        "--vehicle-type",
        required=True,
        help="Vehicle type name",
    )
    optimize_sliders_parser.add_argument(
        "--year",
        type=int,
        default=1900,
        help="Game year (minimum 1900)",
    )
    optimize_sliders_parser.add_argument(
        "--cost-mode",
        default="balanced",
        choices=["cheap", "balanced", "luxury"],
        help="Cost mode objective",
    )
    optimize_sliders_parser.add_argument(
        "--chassis-skill",
        type=float,
        default=0.0,
        help="Chassis design skill (0-100)",
    )
    optimize_sliders_parser.add_argument(
        "--engine-skill",
        type=float,
        default=0.0,
        help="Engine design skill (0-100)",
    )
    optimize_sliders_parser.add_argument(
        "--gearbox-skill",
        type=float,
        default=0.0,
        help="Gearbox design skill (0-100)",
    )
    optimize_sliders_parser.add_argument(
        "--vehicle-skill",
        type=float,
        default=0.0,
        help="Vehicle/coachwork design skill (0-100)",
    )
    optimize_sliders_parser.add_argument(
        "--depth",
        default="balanced",
        choices=["quick", "balanced", "thorough"],
        help="Optimization depth",
    )
    optimize_sliders_parser.add_argument(
        "--vehicle-types-file",
        default=_default_data_path(DEFAULT_VEHICLE_TYPES),
        help="Path to vehicle types CSV",
    )

    group_vehicle_types_parser = subparsers.add_parser(
        "group-vehicle-types",
        help="Cluster vehicle types by similar design-stat priorities",
    )
    group_vehicle_types_parser.add_argument(
        "--groups",
        "-k",
        type=int,
        default=5,
        help="Number of clusters (default: 5)",
    )
    group_vehicle_types_parser.add_argument(
        "--vehicle-types-file",
        default=_default_data_path(DEFAULT_VEHICLE_TYPES),
        help="Path to vehicle types CSV",
    )
    group_vehicle_types_parser.add_argument(
        "--show-centroids",
        action="store_true",
        help="Print centroid weights for each group",
    )
    group_vehicle_types_parser.add_argument(
        "--show-similar-to",
        default=None,
        metavar="NAME",
        help="Show vehicle types most similar to NAME instead of clustering",
    )
    group_vehicle_types_parser.add_argument(
        "--top",
        type=int,
        default=5,
        help="Number of similar vehicle types to show (default: 5)",
    )

    parser._cli_parsers = {
        "run_app": run_app_parser,
        "rank": rank_parser,
        "priorities": priorities_parser,
        "design_checklist": design_checklist_parser,
        "packages": packages_parser,
        "download_wiki": download_wiki_parser,
        "import_wiki": import_wiki_parser,
        "inspect_sources": inspect_sources_parser,
        "setup_sources": setup_sources_parser,
        "formulas": formulas_parser,
        "calc_gearboxes": calc_gearboxes_parser,
        "calc_chassis": calc_chassis_parser,
        "calc_engines": calc_engines_parser,
        "terminology_audit": terminology_audit_parser,
        "import_map": import_map_parser,
        "list_maps": list_maps_parser,
        "danger_periods": danger_periods_parser,
        "events_summary": events_summary_parser,
        "import_components": import_components_parser,
        "tech_availability": tech_availability_parser,
        "slider_audit": slider_audit_parser,
        "optimize_sliders": optimize_sliders_parser,
        "group_vehicle_types": group_vehicle_types_parser,
    }
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI with subcommands or legacy rank-designs mode."""
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    subcommand, remaining = _resolve_subcommand(raw_argv)

    parser = build_parser()
    cli_parsers = parser._cli_parsers
    run_app_parser = cli_parsers["run_app"]
    rank_parser = cli_parsers["rank"]
    priorities_parser = cli_parsers["priorities"]
    design_checklist_parser = cli_parsers["design_checklist"]
    packages_parser = cli_parsers["packages"]
    download_wiki_parser = cli_parsers["download_wiki"]
    import_wiki_parser = cli_parsers["import_wiki"]
    inspect_sources_parser = cli_parsers["inspect_sources"]
    setup_sources_parser = cli_parsers["setup_sources"]
    formulas_parser = cli_parsers["formulas"]
    calc_gearboxes_parser = cli_parsers["calc_gearboxes"]
    calc_chassis_parser = cli_parsers["calc_chassis"]
    calc_engines_parser = cli_parsers["calc_engines"]
    terminology_audit_parser = cli_parsers["terminology_audit"]
    import_map_parser = cli_parsers["import_map"]
    list_maps_parser = cli_parsers["list_maps"]
    danger_periods_parser = cli_parsers["danger_periods"]
    events_summary_parser = cli_parsers["events_summary"]
    import_components_parser = cli_parsers["import_components"]
    tech_availability_parser = cli_parsers["tech_availability"]
    slider_audit_parser = cli_parsers["slider_audit"]
    optimize_sliders_parser = cli_parsers["optimize_sliders"]
    group_vehicle_types_parser = cli_parsers["group_vehicle_types"]

    if subcommand == UNKNOWN_SUBCOMMAND:
        print(f"Unknown command: {raw_argv[0]!r}")
        print("Known commands:", ", ".join(sorted(SUBCOMMANDS)))
        print(
            "Tip: run without a subcommand for legacy design ranking, e.g.\n"
            "  python -m gearcity_optimizer.cli --vehicle-type Sedan --objective balanced"
        )
        return 1

    if subcommand is None:
        if not remaining or any(arg in ("-h", "--help") for arg in remaining):
            parser.print_help()
            return 0
        rank_parser.set_defaults(func=handle_rank_designs)
        args = rank_parser.parse_args(remaining)
        return handle_rank_designs(args)

    if subcommand == "run-app":
        run_app_parser.set_defaults(func=handle_run_app)
        args = run_app_parser.parse_args(remaining)
        return handle_run_app(args)

    if subcommand == "rank-designs":
        rank_parser.set_defaults(func=handle_rank_designs)
        args = rank_parser.parse_args(remaining)
        return handle_rank_designs(args)

    if subcommand == "priorities":
        priorities_parser.set_defaults(func=handle_priorities)
        args = priorities_parser.parse_args(remaining)
        return handle_priorities(args)

    if subcommand == "design-checklist":
        design_checklist_parser.set_defaults(func=handle_design_checklist)
        args = design_checklist_parser.parse_args(remaining)
        return handle_design_checklist(args)

    if subcommand == "packages":
        packages_parser.set_defaults(func=handle_packages)
        args = packages_parser.parse_args(remaining)
        return handle_packages(args)

    if subcommand == "download-wiki":
        download_wiki_parser.set_defaults(func=handle_download_wiki)
        args = download_wiki_parser.parse_args(remaining)
        return handle_download_wiki(args)

    if subcommand == "import-wiki":
        import_wiki_parser.set_defaults(func=handle_import_wiki)
        args = import_wiki_parser.parse_args(remaining)
        return handle_import_wiki(args)

    if subcommand == "inspect-sources":
        inspect_sources_parser.set_defaults(func=handle_inspect_sources)
        args = inspect_sources_parser.parse_args(remaining)
        return handle_inspect_sources(args)

    if subcommand == "setup-sources":
        setup_sources_parser.set_defaults(func=handle_setup_sources)
        args = setup_sources_parser.parse_args(remaining)
        return handle_setup_sources(args)

    if subcommand == "formulas":
        formulas_parser.set_defaults(func=handle_formulas)
        args = formulas_parser.parse_args(remaining)
        return handle_formulas(args)

    if subcommand == "calc-gearboxes":
        calc_gearboxes_parser.set_defaults(func=handle_calc_gearboxes)
        args = calc_gearboxes_parser.parse_args(remaining)
        return handle_calc_gearboxes(args)

    if subcommand == "calc-chassis":
        calc_chassis_parser.set_defaults(func=handle_calc_chassis)
        args = calc_chassis_parser.parse_args(remaining)
        return handle_calc_chassis(args)

    if subcommand == "calc-engines":
        calc_engines_parser.set_defaults(func=handle_calc_engines)
        args = calc_engines_parser.parse_args(remaining)
        return handle_calc_engines(args)

    if subcommand == "terminology-audit":
        terminology_audit_parser.set_defaults(func=handle_terminology_audit)
        args = terminology_audit_parser.parse_args(remaining)
        return handle_terminology_audit(args)

    if subcommand == "import-map":
        import_map_parser.set_defaults(func=handle_import_map)
        args = import_map_parser.parse_args(remaining)
        return handle_import_map(args)

    if subcommand == "list-maps":
        list_maps_parser.set_defaults(func=handle_list_maps)
        args = list_maps_parser.parse_args(remaining)
        return handle_list_maps(args)

    if subcommand == "danger-periods":
        danger_periods_parser.set_defaults(func=handle_danger_periods)
        args = danger_periods_parser.parse_args(remaining)
        return handle_danger_periods(args)

    if subcommand == "events-summary":
        events_summary_parser.set_defaults(func=handle_events_summary)
        args = events_summary_parser.parse_args(remaining)
        return handle_events_summary(args)

    if subcommand == "group-vehicle-types":
        group_vehicle_types_parser.set_defaults(func=handle_group_vehicle_types)
        args = group_vehicle_types_parser.parse_args(remaining)
        return handle_group_vehicle_types(args)

    if subcommand == "import-components":
        import_components_parser.set_defaults(func=handle_import_components)
        args = import_components_parser.parse_args(remaining)
        return handle_import_components(args)

    if subcommand == "tech-availability":
        tech_availability_parser.set_defaults(func=handle_tech_availability)
        args = tech_availability_parser.parse_args(remaining)
        return handle_tech_availability(args)

    if subcommand == "slider-audit":
        slider_audit_parser.set_defaults(func=handle_slider_audit)
        args = slider_audit_parser.parse_args(remaining)
        return handle_slider_audit(args)

    if subcommand == "optimize-sliders":
        optimize_sliders_parser.set_defaults(func=handle_optimize_sliders)
        args = optimize_sliders_parser.parse_args(remaining)
        return handle_optimize_sliders(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
