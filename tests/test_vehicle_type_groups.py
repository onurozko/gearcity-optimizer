"""Tests for vehicle type grouping and similarity."""

from __future__ import annotations

from pathlib import Path

import pytest

from gearcity_optimizer.cli import SUBCOMMANDS, main
from gearcity_optimizer.core.models import VehicleType
from gearcity_optimizer.core.vehicle_type_groups import (
    calculate_vehicle_type_similarity,
    cluster_vehicle_types,
    describe_vehicle_type_group,
    find_most_similar_vehicle_types,
    get_vehicle_type_feature_vector,
)
from gearcity_optimizer.core.vehicle_types import load_vehicle_types
from gearcity_optimizer.ui.streamlit_helpers import group_count_options


def _vehicle_types_path() -> str:
    return str(Path(__file__).resolve().parent.parent / "data" / "vehicle_types.csv")


def _load_all_vehicle_types() -> list[VehicleType]:
    return list(load_vehicle_types(_vehicle_types_path()).values())


def _make_vehicle_type(**overrides) -> VehicleType:
    defaults = {
        "name": "Test",
        "performance": 0.4,
        "drivability": 0.4,
        "luxury": 0.4,
        "safety": 0.4,
        "fuel": 0.4,
        "power": 0.4,
        "cargo": 0.4,
        "dependability": 0.4,
        "wealth_demo": 3,
        "military_fleet": False,
        "civilian_fleet": False,
    }
    defaults.update(overrides)
    return VehicleType(**defaults)


def test_group_count_below_two_raises_value_error():
    vehicle_types = _load_all_vehicle_types()
    with pytest.raises(ValueError, match="at least 2"):
        cluster_vehicle_types(vehicle_types, 1)


def test_group_count_above_vehicle_type_count_raises_value_error():
    vehicle_types = _load_all_vehicle_types()
    with pytest.raises(ValueError, match="cannot exceed"):
        cluster_vehicle_types(vehicle_types, len(vehicle_types) + 1)


def test_clustering_returns_exactly_k_groups():
    vehicle_types = _load_all_vehicle_types()
    groups = cluster_vehicle_types(vehicle_types, 5)
    assert len(groups) == 5


def test_every_vehicle_type_appears_exactly_once():
    vehicle_types = _load_all_vehicle_types()
    groups = cluster_vehicle_types(vehicle_types, 6)
    assigned = [name for group in groups for name in group.vehicle_types]
    expected = sorted(vehicle_type.name for vehicle_type in vehicle_types)
    assert sorted(assigned) == expected
    assert len(assigned) == len(expected)


def test_clustering_is_deterministic():
    vehicle_types = _load_all_vehicle_types()
    first = cluster_vehicle_types(vehicle_types, 5)
    second = cluster_vehicle_types(vehicle_types, 5)
    assert first == second


def test_similarity_score_highest_for_same_vehicle_type():
    vehicle_types = _load_all_vehicle_types()
    pairs = calculate_vehicle_type_similarity(vehicle_types)
    sedan_self = next(
        pair
        for pair in pairs
        if pair["vehicle_type_a"] == "Sedan" and pair["vehicle_type_b"] == "Sedan"
    )
    sedan_hatchback = next(
        pair
        for pair in pairs
        if {"Sedan", "Hatchback"} == {pair["vehicle_type_a"], pair["vehicle_type_b"]}
    )
    assert sedan_self["similarity_score"] == pytest.approx(100.0)
    assert sedan_self["similarity_score"] > sedan_hatchback["similarity_score"]


def test_find_most_similar_vehicle_types_excludes_self():
    vehicle_types = _load_all_vehicle_types()
    similar = find_most_similar_vehicle_types("Sedan", vehicle_types, top_n=5)
    assert similar
    names = [name for name, _ in similar]
    assert "Sedan" not in names
    assert all(isinstance(score, float) for _, score in similar)


def test_group_vehicle_types_cli_is_registered():
    assert "group-vehicle-types" in SUBCOMMANDS


def test_group_vehicle_types_cli_output(capsys):
    exit_code = main(
        [
            "group-vehicle-types",
            "--groups",
            "5",
            "--vehicle-types-file",
            _vehicle_types_path(),
        ]
    )
    assert exit_code == 0
    captured = capsys.readouterr().out
    assert "Vehicle type groups, k=5" in captured
    assert "Group 1:" in captured


def test_group_vehicle_types_cli_similar_to(capsys):
    exit_code = main(
        [
            "group-vehicle-types",
            "--show-similar-to",
            "Sedan",
            "--vehicle-types-file",
            _vehicle_types_path(),
        ]
    )
    assert exit_code == 0
    captured = capsys.readouterr().out
    assert "Most similar to Sedan:" in captured
    listed_names = [
        line.split(" - ", 1)[0].split(". ", 1)[-1]
        for line in captured.splitlines()
        if line.strip() and line.strip()[0].isdigit()
    ]
    assert "Sedan" not in listed_names


def test_group_count_options_returns_two_through_n():
    vehicle_types = _load_all_vehicle_types()
    options = group_count_options(len(vehicle_types))
    assert options == list(range(2, len(vehicle_types) + 1))


def test_feature_vector_excludes_fleet_flags():
    vehicle_type = _make_vehicle_type(
        name="Fleet Test",
        military_fleet=True,
        civilian_fleet=True,
        wealth_demo=9,
    )
    vector = get_vehicle_type_feature_vector(vehicle_type)
    assert set(vector.keys()) == {
        "performance",
        "drivability",
        "luxury",
        "safety",
        "fuel",
        "power",
        "cargo",
        "dependability",
    }


def test_describe_vehicle_type_group_is_deterministic():
    centroid = {
        "performance": 0.8,
        "drivability": 0.85,
        "luxury": 0.1,
        "safety": 0.1,
        "fuel": 0.05,
        "power": 0.75,
        "cargo": 0.1,
        "dependability": 0.3,
    }
    assert describe_vehicle_type_group(centroid) == "Performance/sport-focused group"
    assert describe_vehicle_type_group(centroid) == describe_vehicle_type_group(centroid)
