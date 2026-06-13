#!/usr/bin/env python3
"""Parse cached GearCity Wiki pages into structured JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gearcity_optimizer.importers.wiki_parser import import_wiki_pages


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Parse cached GearCity Wiki pages."
    )
    parser.add_argument(
        "--urls-file",
        default="sources/wiki_urls.json",
        help="JSON file listing wiki page names",
    )
    parser.add_argument(
        "--vehicle-types-file",
        default="data/vehicle_types.csv",
        help="Existing vehicle types CSV for comparison",
    )
    args = parser.parse_args()

    summary = import_wiki_pages(
        urls_file=args.urls_file,
        existing_vehicle_types_csv=args.vehicle_types_file,
    )

    print("GearCity Wiki import complete.\n")

    if summary["missing_sources"]:
        print("Missing cached sources:")
        for name in summary["missing_sources"]:
            print(f"  - {name}")
        print()

    print("Parsed pages:")
    for page in summary["parsed"]:
        print(
            f"  - {page['name']} ({page['source_type']}): "
            f"{page['tables']} tables, {page['formula_chunks']} formula chunks"
        )
        print(f"      -> {page['output']}")

    if summary.get("formula_index_path"):
        print(f"\nFormula index: {summary['formula_index_path']}")

    if summary.get("vehicle_types_from_wiki"):
        print(f"\nVehicle types CSV: {summary['vehicle_types_from_wiki']}")

    comparison = summary.get("vehicle_type_comparison")
    if comparison:
        print("\nVehicle type comparison:")
        print(f"  Match: {comparison['match']}")
        if comparison["missing_vehicle_types"]:
            print(f"  Missing: {comparison['missing_vehicle_types']}")
        if comparison["extra_vehicle_types"]:
            print(f"  Extra: {comparison['extra_vehicle_types']}")
        if comparison["changed_values"]:
            print(f"  Changed values: {len(comparison['changed_values'])}")
            for change in comparison["changed_values"][:10]:
                print(
                    f"    {change['vehicle_type']}.{change['column']}: "
                    f"{change['existing']} -> {change['generated']}"
                )

    print(f"\nSummary JSON:\n{json.dumps(summary, indent=2)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
