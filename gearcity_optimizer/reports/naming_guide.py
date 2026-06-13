"""Load the GearCity component naming guide Markdown."""

from __future__ import annotations

from pathlib import Path

from gearcity_optimizer.data_sources import project_root

NAMING_GUIDE_RELATIVE_PATH = Path("docs") / "component_naming_standard.md"

MISSING_NAMING_GUIDE_MESSAGE = (
    "The naming guide file is not available. "
    f"Expected location: {NAMING_GUIDE_RELATIVE_PATH.as_posix()}"
)


def naming_guide_path(root: Path | None = None) -> Path:
    """Return the path to the component naming guide Markdown file."""
    return (root or project_root()) / NAMING_GUIDE_RELATIVE_PATH


def load_naming_guide_markdown(root: Path | None = None) -> str | None:
    """Load naming guide Markdown, or None if the file is missing."""
    path = naming_guide_path(root)
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")
