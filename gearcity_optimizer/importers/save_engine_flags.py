"""Map GearCity save engine text fields onto wiki formula flags."""


def _valve_rpm_subcomponent(valve: str) -> float:
    """Approximate SubComponent_Valve_RPM from save Valve text."""
    valve_text = valve.lower()
    if "dohc" in valve_text:
        return 1.18
    if "sohc" in valve_text:
        return 1.12
    if any(token in valve_text for token in ("ohv", "overhead")):
        return 0.95
    return 0.80


def _fuel_rpm_subcomponent(fuel_type: str) -> float:
    """Approximate SubComponent_FuelType_RPM from save Fueltype text."""
    fuel_text = fuel_type.lower()
    if "diesel" in fuel_text:
        return 0.85
    if "electric" in fuel_text:
        return 0.50
    return 1.0


def engine_formula_flags_from_save(
    *,
    valve: str = "",
    induction: str = "",
    fuel_type: str = "",
) -> dict[str, bool | float]:
    """Infer engine formula inputs from save EngineInfo text columns."""
    valve_text = valve.lower()
    induction_text = induction.lower()
    fuel_text = fuel_type.lower()

    return {
        "has_overhead_cam": any(
            token in valve_text for token in ("ohv", "dohc", "sohc", "overhead")
        ),
        "has_fuel_injection": "injection" in fuel_text or "injection" in induction_text,
        "is_supercharged": "supercharg" in induction_text,
        "is_turbocharged": "turbo" in induction_text and "twin" not in induction_text,
        "wiki_valve_rpm": _valve_rpm_subcomponent(valve),
        "wiki_fuel_rpm": _fuel_rpm_subcomponent(fuel_type),
    }
