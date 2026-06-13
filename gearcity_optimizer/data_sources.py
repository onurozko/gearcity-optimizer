"""Default paths to project data, generated output, and downloaded sources."""

from __future__ import annotations

from pathlib import Path

DEFAULT_VEHICLE_TYPES = "data/vehicle_types.csv"
DEFAULT_CANDIDATES = "data/candidate_designs.csv"
DEFAULT_CHASSIS = "data/chassis_candidates.csv"
DEFAULT_ENGINES = "data/engine_candidates.csv"
DEFAULT_GEARBOXES = "data/gearbox_candidates.csv"
DEFAULT_WIKI_URLS = "sources/wiki_urls.json"
DEFAULT_FORMULA_INDEX = "generated/raw_parsed/wiki_formula_index.json"


def project_root() -> Path:
    """Return the repository root directory."""
    return Path(__file__).resolve().parent.parent


def data_path(relative: str) -> str:
    """Resolve a path relative to the project root."""
    return str(project_root() / relative)
