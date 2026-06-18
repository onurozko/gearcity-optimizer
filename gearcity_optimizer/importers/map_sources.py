"""Discover and import GearCity map TurnEvents sources."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from gearcity_optimizer.data_sources import project_root
from gearcity_optimizer.importers.turn_events_parser import (
    TurnEventsValidationError,
    validate_turn_events_xml,
)

USER_MAPS_DIR = "user_data/maps"
BUNDLED_MAPS_DIR = "sources/maps"


@dataclass(frozen=True)
class MapSource:
    """A map-specific TurnEvents timeline source."""

    id: str
    name: str
    description: str
    path: Path
    turn_events_file: Path
    source_kind: str  # user_import, bundled_example, developer_fixture


def user_maps_root() -> Path:
    """Return the user-imported maps directory."""
    return project_root() / USER_MAPS_DIR


def bundled_maps_root() -> Path:
    """Return optional bundled/developer map fixtures directory."""
    return project_root() / BUNDLED_MAPS_DIR


def generate_map_id(name: str) -> str:
    """Build a stable map id slug from a display name."""
    slug = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    if slug.endswith("_map"):
        slug = slug[: -len("_map")]
    return slug or "map"


def _read_map_metadata(map_dir: Path, source_kind: str) -> MapSource | None:
    """Load one map folder if metadata and TurnEvents file are valid."""
    metadata_path = map_dir / "map.json"
    if not metadata_path.is_file():
        return None

    try:
        with metadata_path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(data, dict):
        return None

    map_id = str(data.get("id", "")).strip()
    name = str(data.get("name", "")).strip()
    if not map_id or not name:
        return None

    turn_events_name = str(data.get("turn_events_file", "TurnEvents.xml")).strip()
    turn_events_file = map_dir / turn_events_name
    if not turn_events_file.is_file():
        return None

    description = str(
        data.get("description", "Imported GearCity map timeline.")
    ).strip()

    return MapSource(
        id=map_id,
        name=name,
        description=description or "Imported GearCity map timeline.",
        path=map_dir,
        turn_events_file=turn_events_file,
        source_kind=source_kind,
    )


def discover_map_sources() -> list[MapSource]:
    """Discover imported and bundled map timelines."""
    sources: list[MapSource] = []

    user_root = user_maps_root()
    if user_root.is_dir():
        for child in sorted(user_root.iterdir()):
            if not child.is_dir():
                continue
            source = _read_map_metadata(child, "user_import")
            if source is not None:
                sources.append(source)

    bundled_root = bundled_maps_root()
    if bundled_root.is_dir():
        for child in sorted(bundled_root.iterdir()):
            if not child.is_dir():
                continue
            source = _read_map_metadata(child, "bundled_example")
            if source is not None:
                sources.append(source)

    sources.sort(key=lambda item: (item.name.lower(), item.id))
    return sources


def load_map_source(map_id: str) -> MapSource:
    """Load one map source by id."""
    for source in discover_map_sources():
        if source.id == map_id:
            return source
    raise KeyError(f"Unknown map id: {map_id}")


def get_default_map_source() -> MapSource | None:
    """Return the first discovered map source, if any."""
    sources = discover_map_sources()
    return sources[0] if sources else None


def import_map_turn_events(
    *,
    map_id: str,
    name: str,
    xml_content: bytes | str,
    description: str = "Imported GearCity map timeline.",
    overwrite: bool = False,
) -> MapSource:
    """Validate and save a TurnEvents.xml import under user_data/maps/."""
    map_id = map_id.strip()
    name = name.strip()
    if not map_id:
        raise ValueError("Map id is required.")
    if not name:
        raise ValueError("Map name is required.")

    if isinstance(xml_content, str):
        xml_bytes = xml_content.encode("utf-8")
    else:
        xml_bytes = xml_content

    validate_turn_events_xml(xml_bytes)

    map_dir = user_maps_root() / map_id
    if map_dir.exists() and not overwrite:
        raise FileExistsError(
            f"Map id {map_id!r} already exists. Choose another id or overwrite."
        )

    map_dir.mkdir(parents=True, exist_ok=True)
    turn_events_path = map_dir / "TurnEvents.xml"
    turn_events_path.write_bytes(xml_bytes)

    metadata = {
        "id": map_id,
        "name": name,
        "description": description,
        "turn_events_file": "TurnEvents.xml",
    }
    with (map_dir / "map.json").open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2)
        handle.write("\n")

    return MapSource(
        id=map_id,
        name=name,
        description=description,
        path=map_dir,
        turn_events_file=turn_events_path,
        source_kind="user_import",
    )


def import_map_from_path(
    *,
    map_id: str,
    name: str,
    source_path: Path | str,
    description: str = "Imported GearCity map timeline.",
    overwrite: bool = False,
) -> MapSource:
    """Import TurnEvents.xml from a local filesystem path."""
    path = Path(source_path)
    if not path.is_file():
        raise FileNotFoundError(
            f"TurnEvents file not found at {path}. "
            "Check the path and try file upload instead."
        )

    xml_content = path.read_bytes()
    return import_map_turn_events(
        map_id=map_id,
        name=name,
        xml_content=xml_content,
        description=description,
        overwrite=overwrite,
    )


def resolve_map_for_cli(map_id: str | None) -> MapSource:
    """Resolve a map for CLI commands, printing guidance when ambiguous."""
    sources = discover_map_sources()
    if not sources:
        raise SystemExit(
            "No map timelines are imported. Run:\n"
            "  gearcity-optimizer import-map --id base_city "
            '--name "Base City Map" --turn-events "<path-to-TurnEvents.xml>"'
        )

    if map_id:
        try:
            return load_map_source(map_id)
        except KeyError:
            available = ", ".join(source.id for source in sources)
            raise SystemExit(
                f"Unknown map id {map_id!r}. Available maps: {available}"
            ) from None

    if len(sources) == 1:
        return sources[0]

    available = "\n".join(f"  - {source.id}: {source.name}" for source in sources)
    raise SystemExit(
        "Multiple maps are available. Pass --map <id>.\n"
        f"Available maps:\n{available}"
    )
