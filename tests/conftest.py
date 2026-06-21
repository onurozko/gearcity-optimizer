"""Shared pytest fixtures for wiki-backed optimizer tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from gearcity_optimizer.core import slider_registry as registry_module
from gearcity_optimizer.core.slider_registry import load_slider_registry
from gearcity_optimizer.importers.wiki_knowledge_builder import (
    FORMULA_EFFECTS_FILENAME,
    SLIDER_REGISTRY_FILENAME,
    build_wiki_knowledge,
)
from gearcity_optimizer.importers.wiki_parser import parse_wiki_page

FIXTURES = Path(__file__).parent / "fixtures" / "wiki"


@pytest.fixture(autouse=True)
def clear_registry_cache() -> None:
    load_slider_registry.cache_clear()
    yield
    load_slider_registry.cache_clear()


@pytest.fixture
def missing_wiki_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the slider registry at paths with no wiki artifacts."""
    missing_dir = tmp_path / "empty"
    missing_dir.mkdir()
    monkeypatch.setattr(
        registry_module,
        "_registry_paths",
        lambda: (
            missing_dir / "wiki_slider_registry.json",
            missing_dir / "wiki_formula_effects.json",
        ),
    )
    load_slider_registry.cache_clear()
    return missing_dir


@pytest.fixture
def wiki_model_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Build and patch a full wiki slider/formula model from test fixtures."""
    parsed_pages = {
        "engine_game_mechanics": parse_wiki_page(
            "engine_game_mechanics",
            (FIXTURES / "engine_sliders_sample.txt").read_text(encoding="utf-8"),
            "raw",
        ),
        "chassis_game_mechanics": parse_wiki_page(
            "chassis_game_mechanics",
            (FIXTURES / "chassis_sliders_sample.txt").read_text(encoding="utf-8"),
            "raw",
        ),
        "gearbox_game_mechanics": parse_wiki_page(
            "gearbox_game_mechanics",
            (FIXTURES / "gearbox_sliders_sample.txt").read_text(encoding="utf-8"),
            "raw",
        ),
        "vehicle_game_mechanics": parse_wiki_page(
            "vehicle_game_mechanics",
            (FIXTURES / "vehicle_sliders_sample.txt").read_text(encoding="utf-8"),
            "raw",
        ),
    }
    build_wiki_knowledge(parsed_pages, output_dir=tmp_path)
    monkeypatch.setattr(
        registry_module,
        "_registry_paths",
        lambda: (
            tmp_path / SLIDER_REGISTRY_FILENAME,
            tmp_path / FORMULA_EFFECTS_FILENAME,
        ),
    )
    load_slider_registry.cache_clear()
    return tmp_path
