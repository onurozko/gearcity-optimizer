"""Map GearCity save engine text fields onto wiki formula flags."""


def engine_formula_flags_from_save(
    *,
    valve: str = "",
    induction: str = "",
    fuel_type: str = "",
) -> dict[str, bool]:
    """Infer boolean engine formula inputs from save EngineInfo text columns."""
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
    }
