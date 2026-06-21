"""Discover and import GearCity Components.xml into local user data."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from gearcity_optimizer.data_sources import project_root

USER_COMPONENTS_DIR = "user_data/game_files/components"
COMPONENTS_FILENAME = "Components.xml"
METADATA_FILENAME = "metadata.json"


@dataclass(frozen=True)
class ComponentsSource:
    """Imported Components.xml source metadata."""

    name: str
    path: Path
    components_file: Path
    source_kind: str


def components_root() -> Path:
    """Return the user-imported Components.xml directory."""
    return project_root() / USER_COMPONENTS_DIR


def discover_components_source() -> ComponentsSource | None:
    """Return imported Components.xml source if present."""
    root = components_root()
    metadata_path = root / METADATA_FILENAME
    components_path = root / COMPONENTS_FILENAME
    if not metadata_path.is_file() or not components_path.is_file():
        return None

    try:
        with metadata_path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(data, dict):
        return None

    name = str(data.get("name", "Imported Components")).strip()
    components_name = str(data.get("components_file", COMPONENTS_FILENAME)).strip()
    components_file = root / components_name
    if not components_file.is_file():
        return None

    return ComponentsSource(
        name=name or "Imported Components",
        path=root,
        components_file=components_file,
        source_kind=str(data.get("source", "user_import")),
    )


def import_components_xml(
    *,
    xml_content: bytes | str,
    name: str = "Default GearCity Components",
    overwrite: bool = False,
) -> ComponentsSource:
    """Validate and save a Components.xml import under user_data/game_files/components/."""
    from gearcity_optimizer.importers.components_xml import (
        validate_components_xml,
        _prepare_xml_bytes,
    )

    xml_bytes = _prepare_xml_bytes(xml_content)
    validate_components_xml(xml_bytes)

    root = components_root()
    if root.exists() and not overwrite:
        existing = discover_components_source()
        if existing is not None:
            raise FileExistsError(
                "Components.xml is already imported. Re-import with overwrite enabled."
            )

    root.mkdir(parents=True, exist_ok=True)
    components_path = root / COMPONENTS_FILENAME
    components_path.write_bytes(xml_bytes)

    metadata = {
        "name": name.strip() or "Default GearCity Components",
        "source": "user_import",
        "components_file": COMPONENTS_FILENAME,
    }
    with (root / METADATA_FILENAME).open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2)
        handle.write("\n")

    return ComponentsSource(
        name=metadata["name"],
        path=root,
        components_file=components_path,
        source_kind="user_import",
    )


def import_components_from_path(
    source_path: Path | str,
    *,
    name: str = "Default GearCity Components",
    overwrite: bool = False,
) -> ComponentsSource:
    """Import Components.xml from a local filesystem path."""
    path = Path(source_path)
    if not path.is_file():
        raise FileNotFoundError(
            f"Components file not found at {path}. "
            "Check the path and try file upload instead."
        )

    return import_components_xml(
        xml_content=path.read_bytes(),
        name=name,
        overwrite=overwrite,
    )


def components_missing_message() -> str:
    """Return guidance when Components.xml has not been imported."""
    return (
        "No Components.xml has been imported yet. Import it with:\n"
        '  gearcity-optimizer import-components --components '
        '"D:\\SteamLibrary\\steamapps\\common\\GearCity\\media\\Scripts\\Components.xml"\n'
        "or use the Streamlit Tech Availability tab."
    )
