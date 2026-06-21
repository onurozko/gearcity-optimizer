"""Build wiki-backed slider registry and formula influence artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gearcity_optimizer.importers.wiki_downloader import project_root_from_module
from gearcity_optimizer.importers.wiki_formula_effects import FormulaEffect, build_formula_effects
from gearcity_optimizer.importers.wiki_parser import build_formula_index, parse_wiki_page, resolve_page_source
from gearcity_optimizer.importers.wiki_slider_parser import (
    MECHANICS_PAGES,
    SliderDefinition,
    parse_sliders_from_parsed_page,
)

SLIDER_REGISTRY_FILENAME = "wiki_slider_registry.json"
FORMULA_EFFECTS_FILENAME = "wiki_formula_effects.json"


def _url_map(entries: list[dict[str, str]]) -> dict[str, str]:
    return {entry["name"]: entry["url"] for entry in entries}


def build_wiki_knowledge(
    parsed_pages: dict[str, dict[str, Any]],
    *,
    url_entries: list[dict[str, str]] | None = None,
    output_dir: str | Path = "generated/raw_parsed",
) -> dict[str, Any]:
    """Build slider registry and formula effects JSON from parsed wiki pages."""
    root = project_root_from_module()
    output_path = Path(output_dir)
    if not output_path.is_absolute():
        output_path = root / output_path
    output_path.mkdir(parents=True, exist_ok=True)

    urls = _url_map(url_entries or [])
    sliders: list[SliderDefinition] = []
    for page_name in sorted(parsed_pages):
        if page_name not in MECHANICS_PAGES:
            continue
        page = parsed_pages[page_name]
        sliders.extend(
            parse_sliders_from_parsed_page(
                page,
                page_name=page_name,
                source_page=page_name,
            )
        )

    effects = build_formula_effects(parsed_pages, source_page_by_name=urls)
    slider_payload = {
        "source_mode": "wiki",
        "slider_count": len(sliders),
        "sliders": [slider.to_dict() for slider in sliders],
    }
    effects_payload = {
        "source_mode": "wiki",
        "effect_count": len(effects),
        "effects": [effect.to_dict() for effect in effects],
    }

    slider_file = output_path / SLIDER_REGISTRY_FILENAME
    effects_file = output_path / FORMULA_EFFECTS_FILENAME
    slider_file.write_text(json.dumps(slider_payload, indent=2), encoding="utf-8")
    effects_file.write_text(json.dumps(effects_payload, indent=2), encoding="utf-8")

    return {
        "slider_registry_path": str(slider_file),
        "formula_effects_path": str(effects_file),
        "slider_count": len(sliders),
        "effect_count": len(effects),
        "pages_with_sliders": sorted({slider.page for slider in sliders}),
    }


def _load_urls(urls_file: Path) -> list[dict[str, str]]:
    with urls_file.open(encoding="utf-8") as handle:
        return json.load(handle)


def build_wiki_knowledge_from_cache(
    *,
    urls_file: str | Path = "sources/wiki_urls.json",
    raw_dir: str | Path = "sources/wiki_raw",
    text_dir: str | Path = "sources/wiki_text",
    html_dir: str | Path = "sources/wiki_html",
    parsed_dir: str | Path = "generated/raw_parsed",
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Rebuild wiki knowledge from cached wiki sources."""
    root = project_root_from_module()
    urls_path = Path(urls_file)
    if not urls_path.is_absolute():
        urls_path = root / urls_path
    raw_path = Path(raw_dir)
    text_path = Path(text_dir)
    html_path = Path(html_dir)
    parsed_path = Path(parsed_dir)
    if not raw_path.is_absolute():
        raw_path = root / raw_path
    if not text_path.is_absolute():
        text_path = root / text_path
    if not html_path.is_absolute():
        html_path = root / html_path
    if not parsed_path.is_absolute():
        parsed_path = root / parsed_path

    entries = _load_urls(urls_path)
    parsed_pages: dict[str, dict[str, Any]] = {}
    missing: list[str] = []

    for entry in entries:
        name = entry["name"]
        if name not in MECHANICS_PAGES:
            continue
        parsed_file = parsed_path / f"wiki_{name}.json"
        if parsed_file.exists():
            parsed_pages[name] = json.loads(parsed_file.read_text(encoding="utf-8"))
            continue
        source = resolve_page_source(name, raw_path, text_path, html_path)
        if source is None:
            missing.append(name)
            continue
        source_type, content = source
        parsed_pages[name] = parse_wiki_page(name, content, source_type)

    if missing:
        return {
            "error": "missing_sources",
            "missing_sources": missing,
            "slider_count": 0,
            "effect_count": 0,
        }

    output = output_dir or parsed_path
    summary = build_wiki_knowledge(parsed_pages, url_entries=entries, output_dir=output)
    summary["formula_index_counts"] = {
        page: len(sections)
        for page, sections in build_formula_index(parsed_pages).items()
    }
    return summary


def load_formula_effects_from_file(path: Path) -> list[FormulaEffect]:
    """Load formula effects from generated JSON."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [FormulaEffect.from_dict(item) for item in payload.get("effects", [])]


def load_slider_definitions_from_file(path: Path) -> list[SliderDefinition]:
    """Load slider definitions from generated JSON."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [SliderDefinition.from_dict(item) for item in payload.get("sliders", [])]
