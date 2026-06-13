"""Command-line interface for GearCity design helper commands."""

from __future__ import annotations

import argparse
import json
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
from gearcity_optimizer.reports.advisor import (
    explain_candidate,
    explain_component_priorities,
    explain_package,
)
from gearcity_optimizer.reports.design_checklist import (
    build_design_checklist,
    format_checklist_for_cli,
)

SUBCOMMANDS = {
    "rank-designs",
    "priorities",
    "design-checklist",
    "packages",
    "download-wiki",
    "import-wiki",
    "inspect-sources",
    "setup-sources",
    "formulas",
    "calc-gearboxes",
    "calc-chassis",
    "calc-engines",
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

    print(f"\nVehicle Type: {vehicle_type.name}\n")
    print("Adjusted vehicle priorities:")
    display_order = [
        "safety",
        "fuel",
        "cargo",
        "dependability",
        "luxury",
        "power",
        "performance",
        "drivability",
        "quality",
    ]
    for rating in display_order:
        if rating in adjusted:
            print(f"  {rating}: {adjusted[rating]:.2f}")

    _print_priority_section("Chassis focus", priorities["chassis"], "chassis")
    _print_priority_section("Engine focus", priorities["engine"], "engine")
    _print_priority_section("Gearbox focus", priorities["gearbox"], "gearbox")
    _print_priority_section(
        "Vehicle design focus", priorities["vehicle_design"], "vehicle_design"
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
    print("Setting up local wiki cache and generated parser outputs...\n")
    result = handle_download_wiki(args)
    if result != 0:
        return result
    print()
    result = handle_import_wiki(args)
    if result != 0:
        return result
    print()
    return handle_inspect_sources(args)


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


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser and all subcommand parsers."""
    parser = argparse.ArgumentParser(
        description="GearCity vehicle design optimizer and component advisor."
    )
    subparsers = parser.add_subparsers(dest="command")

    rank_parser = subparsers.add_parser(
        "rank-designs",
        help="Rank finished vehicle designs (default mode)",
    )
    priorities_parser = subparsers.add_parser(
        "priorities",
        help="Show component stat priorities for a vehicle type",
    )
    design_checklist_parser = subparsers.add_parser(
        "design-checklist",
        help="Show a practical vehicle design checklist for a vehicle type",
    )
    packages_parser = subparsers.add_parser(
        "packages",
        help="Rank chassis + engine + gearbox combinations",
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
    setup_sources_parser = subparsers.add_parser(
        "setup-sources",
        help="Download, import, and inspect wiki sources (fresh-clone helper)",
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

    parser._cli_parsers = {
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
    }
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI with subcommands or legacy rank-designs mode."""
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    subcommand, remaining = _resolve_subcommand(raw_argv)

    parser = build_parser()
    cli_parsers = parser._cli_parsers
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

    if subcommand == UNKNOWN_SUBCOMMAND:
        print(f"Unknown command: {raw_argv[0]!r}")
        print("Known commands:", ", ".join(sorted(SUBCOMMANDS)))
        print(
            "Tip: run without a subcommand for legacy design ranking, e.g.\n"
            "  python -m gearcity_optimizer.cli --vehicle-type Sedan --objective balanced"
        )
        return 1

    if subcommand is None:
        rank_parser.set_defaults(func=handle_rank_designs)
        args = rank_parser.parse_args(remaining)
        return handle_rank_designs(args)

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

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
