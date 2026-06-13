"""Tests for the component naming guide."""

from __future__ import annotations

from pathlib import Path

from gearcity_optimizer.reports.naming_guide import (
    MISSING_NAMING_GUIDE_MESSAGE,
    load_naming_guide_markdown,
    naming_guide_path,
)


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_naming_guide_markdown_file_exists():
    """The naming guide Markdown file should be committed in docs/."""
    path = naming_guide_path(_project_root())
    assert path.is_file()


def test_load_naming_guide_markdown_returns_content():
    """The naming guide loader should return the Markdown source."""
    content = load_naming_guide_markdown(_project_root())
    assert content is not None
    assert "# GearCity Component Naming Standard" in content
    assert "B-G-5P-40T" in content
    assert "Conflict / Resolution Summary" in content


def test_naming_guide_uses_s_for_sport_and_m_for_marine():
    """Role codes should use S for Sport and M for Marine."""
    content = load_naming_guide_markdown(_project_root())
    assert content is not None
    assert "| `S`  | Sport      |" in content
    assert "| `M`  | Marine     |" in content
    assert "Marine diesel engine" in content
    assert "M-D-5P-28T" in content
    assert "Sport gasoline engine" in content
    assert "S-G-6P-70T" in content
    assert "reserved for Ship" not in content
    assert "`S` is reserved for Ship" not in content


def test_missing_naming_guide_file_returns_none(tmp_path: Path):
    """A missing naming guide file should return None instead of raising."""
    assert load_naming_guide_markdown(tmp_path) is None


def test_missing_naming_guide_message_is_friendly():
    """The missing-file message should mention the expected path."""
    assert "component_naming_standard.md" in MISSING_NAMING_GUIDE_MESSAGE
