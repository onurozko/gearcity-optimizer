"""Reference LayoutComponents dimensions for wiki formula inputs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gearcity_optimizer.importers.component_choices import ComponentChoice

LAYOUT_REFERENCE_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "engine_layout_reference.json"
)


@dataclass(frozen=True)
class EngineLayoutReference:
    """Layout subcomponent values from GearCity LayoutComponents."""

    key: str
    engine_length: float
    engine_width: float
    layout_power: float
    layout_fuel: float
    layout_smooth: float
    cylinder_length_arrangement: int


@lru_cache(maxsize=1)
def load_engine_layout_reference() -> dict[str, EngineLayoutReference]:
    """Load bundled layout reference rows keyed by wiki layout key."""
    with LAYOUT_REFERENCE_PATH.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    return {
        key: EngineLayoutReference(
            key=key,
            engine_length=float(values["engine_length"]),
            engine_width=float(values["engine_width"]),
            layout_power=float(values["layout_power"]),
            layout_fuel=float(values.get("layout_fuel", 0.5)),
            layout_smooth=float(values.get("layout_smooth", 0.5)),
            cylinder_length_arrangement=int(values["cylinder_length_arrangement"]),
        )
        for key, values in raw.items()
    }


def layout_reference_for_key(layout_key: str | None) -> EngineLayoutReference | None:
    """Return reference dimensions for a wiki layout key."""
    if not layout_key:
        return None
    return load_engine_layout_reference().get(layout_key)


def layout_reference_for_choice(layout: ComponentChoice) -> EngineLayoutReference | None:
    """Return reference dimensions for a Components.xml layout choice."""
    from gearcity_optimizer.core.wiki_component_compatibility import resolve_engine_layout_key

    return layout_reference_for_key(resolve_engine_layout_key(layout))
