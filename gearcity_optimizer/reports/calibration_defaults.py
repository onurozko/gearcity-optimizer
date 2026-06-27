"""Bundled calibration correction tables and default loading."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources

from gearcity_optimizer.reports.save_calibration_corrections import (
    CalibrationCorrections,
    corrections_from_dict,
)

BUNDLED_CORRECTIONS_NAME = "calibration_corrections.json"


@lru_cache(maxsize=1)
def load_default_calibration_corrections() -> CalibrationCorrections:
    """Load shipped segment corrections safe for auto-apply with formula bridge fixes."""
    try:
        payload = (
            resources.files("gearcity_optimizer.resources")
            .joinpath(BUNDLED_CORRECTIONS_NAME)
            .read_text(encoding="utf-8")
        )
    except (FileNotFoundError, ModuleNotFoundError, OSError, TypeError):
        return CalibrationCorrections()

    full = corrections_from_dict(json.loads(payload))
    engine = {
        key: value
        for key, value in full.engine.items()
        if "layout=I" in key
    }
    gearbox = {
        key: value
        for key, value in full.gearbox.items()
        if "mod_bucket=mod=3+" not in key
    }
    return CalibrationCorrections(
        version=full.version,
        engine=engine,
        gearbox=gearbox,
    )
