#!/usr/bin/env python3
"""Download configured GearCity Wiki pages to local cache."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gearcity_optimizer.importers.wiki_downloader import download_wiki_pages


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download configured GearCity Wiki pages."
    )
    parser.add_argument(
        "--urls-file",
        default="sources/wiki_urls.json",
        help="JSON file listing wiki URLs to download",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Redownload even if cached files exist",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay in seconds between requests (default: 1.0)",
    )
    args = parser.parse_args()

    results = download_wiki_pages(
        urls_file=args.urls_file,
        force=args.force,
        delay_seconds=args.delay,
    )

    downloaded = [r["name"] for r in results if r["downloaded"]]
    skipped = [r["name"] for r in results if r.get("skipped")]
    failures = [
        (r["name"], r["errors"])
        for r in results
        if r.get("errors")
    ]

    print("GearCity Wiki download complete.\n")

    if downloaded:
        print("Downloaded:")
        for name in downloaded:
            print(f"  - {name}")
    else:
        print("Downloaded: (none, all files cached)")

    if skipped:
        print("\nSkipped (cached):")
        for name in skipped:
            print(f"  - {name}")

    if failures:
        print("\nExport/raw failures:")
        for name, errors in failures:
            print(f"  - {name}:")
            for error in errors:
                print(f"      {error}")

    manifest = Path("generated/raw_parsed/wiki_download_manifest.json")
    print(f"\nManifest: {manifest.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
