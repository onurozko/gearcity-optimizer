"""Tests for wiki-backed engine, chassis, and gearbox compatibility rules."""

from __future__ import annotations

from gearcity_optimizer.core.wiki_component_compatibility import (
    filter_compatible_candidates,
    is_valid_component_choices,
    layout_cylinder_bank_arrangement,
    parse_gear_count,
    validate_component_choices,
)
from gearcity_optimizer.importers.component_choices import ComponentChoice


def _choice(
    name: str,
    choice_type: str,
    *,
    display_name: str | None = None,
    **stats: float,
) -> ComponentChoice:
    return ComponentChoice(
        id=name,
        name=name,
        display_name=display_name or name,
        section="engine",
        choice_type=choice_type,
        start_year=1890,
        end_year=5050,
        required_skill=0.0,
        stats=dict(stats),
        raw_attributes={"picture": f"{name}.dds"},
        source_path="test",
        confidence="high",
    )


def test_straight_layout_supports_two_and_six_cylinders():
    layout = _choice("StraightLayout", "engine_layout")
    two = _choice("TwoCylinder", "cylinder_count", cylinders=2)
    six = _choice("SixCylinder", "cylinder_count", cylinders=6)
    one = _choice("OneCylinder", "cylinder_count", cylinders=1)

    assert is_valid_component_choices({"engine_layout": layout, "cylinder_count": two})
    assert is_valid_component_choices({"engine_layout": layout, "cylinder_count": six})
    assert not is_valid_component_choices({"engine_layout": layout, "cylinder_count": one})
    assert layout_cylinder_bank_arrangement(layout) == 1


def test_single_layout_only_supports_one_cylinder():
    layout = _choice("SingleLayout", "engine_layout")
    one = _choice("OneCylinder", "cylinder_count", cylinders=1)
    two = _choice("TwoCylinder", "cylinder_count", cylinders=2)

    assert is_valid_component_choices({"engine_layout": layout, "cylinder_count": one})
    assert not is_valid_component_choices({"engine_layout": layout, "cylinder_count": two})


def test_straight_layout_rejects_no_valve():
    layout = _choice("StraightLayout", "engine_layout")
    novalve = _choice("NoValve", "valvetrain", display_name="No Valve")

    result = validate_component_choices({"engine_layout": layout, "valvetrain": novalve})
    assert not result.is_valid
    assert any("No Valve" in item or "NoValve" in item for item in result.violations)


def test_steam_layout_requires_water_fuel_and_no_valve():
    layout = _choice("SteamLayout", "engine_layout")
    water = _choice("WaterFuel", "fuel_type", display_name="Water")
    gas = _choice("4StrokeGasFuel", "fuel_type", display_name="Gasoline")
    novalve = _choice("NoValve", "valvetrain", display_name="No Valve")
    ohv = _choice("OHV", "valvetrain")
    induction = _choice("NaturalyAspiratedInduction", "forced_induction", display_name="Naturally Aspirated")

    steam_combo = {
        "engine_layout": layout,
        "fuel_type": water,
        "valvetrain": novalve,
        "forced_induction": induction,
    }
    assert is_valid_component_choices(steam_combo)

    bad_fuel = dict(steam_combo)
    bad_fuel["fuel_type"] = gas
    assert not is_valid_component_choices(bad_fuel)

    bad_valve = dict(steam_combo)
    bad_valve["valvetrain"] = ohv
    assert not is_valid_component_choices(bad_valve)


def test_manual_gearbox_supports_one_gear_automatic_does_not():
    manual = _choice("SynchronisedManual", "gearbox_type", display_name="Manual")
    automatic = _choice("Automatic", "gearbox_type")
    one_gear = _choice("OneGear", "gear_count", display_name="1 Gear", gears=1)
    three_gear = _choice("ThreeGear", "gear_count", display_name="3 Gear", gears=3)

    assert is_valid_component_choices({"gearbox_type": manual, "gear_count": one_gear})
    assert is_valid_component_choices({"gearbox_type": manual, "gear_count": three_gear})
    assert not is_valid_component_choices({"gearbox_type": automatic, "gear_count": one_gear})
    assert is_valid_component_choices({"gearbox_type": automatic, "gear_count": three_gear})


def test_non_synchronous_gearbox_supports_three_gears():
    gearbox = _choice("NonSynchronisedManual", "gearbox_type", display_name="Non-Synchronous")
    three_gear = _choice("ThreeGear", "gear_count", display_name="3 Gear", gears=3)

    assert is_valid_component_choices({"gearbox_type": gearbox, "gear_count": three_gear})
    assert parse_gear_count(three_gear) == 3


def test_filter_compatible_candidates_drops_invalid_beam_branch():
    layout = _choice("StraightLayout", "engine_layout")
    two = _choice("TwoCylinder", "cylinder_count", cylinders=2)
    novalve = _choice("NoValve", "valvetrain", display_name="No Valve")
    ohv = _choice("OHV", "valvetrain")

    partial = {"engine_layout": layout, "cylinder_count": two}
    assert filter_compatible_candidates("valvetrain", ohv, partial)
    assert not filter_compatible_candidates("valvetrain", novalve, partial)


def test_chassis_choices_have_no_wiki_cross_rules():
    frame = _choice("LadderFrame", "frame")
    drivetrain = _choice("FRDrivetrain", "drivetrain")
    suspension = _choice("SolidAxleSuspension", "suspension")

    assert is_valid_component_choices(
        {
            "frame": frame,
            "drivetrain": drivetrain,
            "suspension": suspension,
        }
    )


def test_wiki_layout_unlock_years_match_reference():
    from gearcity_optimizer.core.wiki_component_compatibility import load_wiki_compatibility_rules

    layouts = load_wiki_compatibility_rules()["engine_layouts"]
    assert layouts["I"]["unlock_year"] == 1891
    assert layouts["Single"]["unlock_year"] == 1890
    assert layouts["Steam"]["unlock_year"] == 1870
    assert layouts["VV"]["unlock_year"] == 1995
