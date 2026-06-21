"""Cluster and compare vehicle types by design-stat importance weights."""

from __future__ import annotations

import math
from dataclasses import dataclass

from gearcity_optimizer.core.models import RATING_ATTRIBUTES, VehicleType

DESIGN_STAT_DIMENSIONS: tuple[str, ...] = RATING_ATTRIBUTES

MAX_POSSIBLE_DISTANCE = math.sqrt(len(DESIGN_STAT_DIMENSIONS))

_KMEANS_MAX_ITERATIONS = 100


@dataclass
class VehicleTypeGroup:
    """One cluster of vehicle types with similar design-stat priorities."""

    group_id: int
    vehicle_types: list[str]
    centroid: dict[str, float]
    top_priorities: list[tuple[str, float]]
    description: str


def get_vehicle_type_feature_vector(vehicle_type: VehicleType) -> dict[str, float]:
    """Return design-stat importance weights for clustering (excludes fleet flags)."""
    return {stat: float(getattr(vehicle_type, stat)) for stat in DESIGN_STAT_DIMENSIONS}


def _feature_vector_to_tuple(vector: dict[str, float]) -> tuple[float, ...]:
    return tuple(vector[stat] for stat in DESIGN_STAT_DIMENSIONS)


def _euclidean_distance(a: dict[str, float], b: dict[str, float]) -> float:
    return math.sqrt(
        sum((a[stat] - b[stat]) ** 2 for stat in DESIGN_STAT_DIMENSIONS)
    )


def _mean_vectors(vectors: list[dict[str, float]]) -> dict[str, float]:
    if not vectors:
        return {stat: 0.0 for stat in DESIGN_STAT_DIMENSIONS}
    count = len(vectors)
    return {
        stat: sum(vector[stat] for vector in vectors) / count
        for stat in DESIGN_STAT_DIMENSIONS
    }


def _top_priorities(
    centroid: dict[str, float], count: int = 3
) -> list[tuple[str, float]]:
    ranked = sorted(
        centroid.items(),
        key=lambda item: (-item[1], item[0]),
    )
    return ranked[:count]


def describe_vehicle_type_group(centroid: dict[str, float]) -> str:
    """Return a short plain-English label for a group centroid."""
    sorted_stats = sorted(
        centroid.items(),
        key=lambda item: (-item[1], item[0]),
    )
    top_three = {stat for stat, _ in sorted_stats[:3]}
    values = list(centroid.values())

    def keys_prominent(keys: set[str], *, minimum: float = 0.35) -> bool:
        return keys.issubset(top_three) and all(centroid[key] >= minimum for key in keys)

    if keys_prominent({"performance", "drivability", "power"}):
        return "Performance/sport-focused group"
    if keys_prominent({"cargo", "power", "dependability"}):
        return "Utility/workhorse group"
    if keys_prominent({"luxury", "safety"}):
        return "Luxury/comfort group"
    if keys_prominent({"fuel", "safety", "dependability"}):
        return "Economy/practical group"

    if max(values) < 0.55 and (max(values) - min(values)) < 0.35:
        return "Balanced mainstream group"

    top_stat, _ = sorted_stats[0]
    fallback_labels = {
        "performance": "Performance-focused group",
        "drivability": "Driveability-focused group",
        "luxury": "Luxury-focused group",
        "safety": "Safety-focused group",
        "fuel": "Fuel economy-focused group",
        "power": "Power-focused group",
        "cargo": "Cargo-focused group",
        "dependability": "Dependability-focused group",
    }
    return fallback_labels.get(top_stat, "Balanced mainstream group")


def _validate_group_count(group_count: int, vehicle_type_count: int) -> None:
    if group_count < 2:
        raise ValueError(
            f"group_count must be at least 2 (got {group_count}). "
            "Use 2 or more groups to compare vehicle type clusters."
        )
    if group_count > vehicle_type_count:
        raise ValueError(
            f"group_count cannot exceed the number of vehicle types "
            f"({vehicle_type_count}); got {group_count}."
        )


def _initial_centroids(
    ordered: list[tuple[str, dict[str, float]]],
    group_count: int,
) -> list[dict[str, float]]:
    count = len(ordered)
    if group_count == count:
        return [vector for _, vector in ordered]

    indices: list[int] = []
    for group_index in range(group_count):
        position = round(group_index * (count - 1) / (group_count - 1))
        indices.append(position)

    return [dict(ordered[index][1]) for index in indices]


def _assign_clusters(
    ordered: list[tuple[str, dict[str, float]]],
    centroids: list[dict[str, float]],
) -> list[int]:
    assignments: list[int] = []
    for _, vector in ordered:
        distances = [
            _euclidean_distance(vector, centroid) for centroid in centroids
        ]
        assignments.append(
            min(range(len(distances)), key=lambda index: (distances[index], index))
        )
    return assignments


def _repair_empty_clusters(
    ordered: list[tuple[str, dict[str, float]]],
    centroids: list[dict[str, float]],
    assignments: list[int],
) -> list[int]:
    group_count = len(centroids)
    repaired = list(assignments)
    for group_index in range(group_count):
        if any(assignment == group_index for assignment in repaired):
            continue

        farthest_index = max(
            range(len(ordered)),
            key=lambda index: (
                _euclidean_distance(ordered[index][1], centroids[group_index]),
                -repaired.count(repaired[index]),
                ordered[index][0],
            ),
        )
        repaired[farthest_index] = group_index
    return repaired


def cluster_vehicle_types(
    vehicle_types: list[VehicleType],
    group_count: int,
) -> list[VehicleTypeGroup]:
    """Cluster vehicle types by design-stat importance weights (deterministic k-means)."""
    if not vehicle_types:
        raise ValueError("vehicle_types must not be empty.")

    _validate_group_count(group_count, len(vehicle_types))

    ordered = sorted(
        (
            (vehicle_type.name, get_vehicle_type_feature_vector(vehicle_type))
            for vehicle_type in vehicle_types
        ),
        key=lambda item: item[0],
    )

    centroids = _initial_centroids(ordered, group_count)
    assignments = _assign_clusters(ordered, centroids)

    for _ in range(_KMEANS_MAX_ITERATIONS):
        assignments = _repair_empty_clusters(ordered, centroids, assignments)

        grouped_vectors: list[list[dict[str, float]]] = [
            [] for _ in range(group_count)
        ]
        for (name, vector), assignment in zip(ordered, assignments, strict=True):
            grouped_vectors[assignment].append(vector)

        new_centroids = [_mean_vectors(group) for group in grouped_vectors]
        new_assignments = _assign_clusters(ordered, new_centroids)

        if new_assignments == assignments:
            centroids = new_centroids
            assignments = new_assignments
            break

        centroids = new_centroids
        assignments = new_assignments

    groups: list[VehicleTypeGroup] = []
    for group_index in range(group_count):
        member_names = sorted(
            name
            for (name, _), assignment in zip(ordered, assignments, strict=True)
            if assignment == group_index
        )
        centroid = centroids[group_index]
        top_priorities = _top_priorities(centroid)
        groups.append(
            VehicleTypeGroup(
                group_id=group_index + 1,
                vehicle_types=member_names,
                centroid=centroid,
                top_priorities=top_priorities,
                description=describe_vehicle_type_group(centroid),
            )
        )

    return sorted(groups, key=lambda group: group.group_id)


def distance_to_similarity_score(distance: float) -> float:
    """Map Euclidean distance to a 0-100 similarity score."""
    raw = 100.0 * (1.0 - distance / MAX_POSSIBLE_DISTANCE)
    return max(0.0, raw)


def calculate_vehicle_type_similarity(
    vehicle_types: list[VehicleType],
) -> list[dict[str, object]]:
    """Return pairwise distances and similarity scores for all vehicle type pairs."""
    vectors = {
        vehicle_type.name: get_vehicle_type_feature_vector(vehicle_type)
        for vehicle_type in vehicle_types
    }
    names = sorted(vectors.keys())
    pairs: list[dict[str, object]] = []

    for left_index, left_name in enumerate(names):
        for right_name in names[left_index:]:
            distance = _euclidean_distance(vectors[left_name], vectors[right_name])
            pairs.append(
                {
                    "vehicle_type_a": left_name,
                    "vehicle_type_b": right_name,
                    "distance": distance,
                    "similarity_score": distance_to_similarity_score(distance),
                }
            )

    return pairs


def find_most_similar_vehicle_types(
    vehicle_type_name: str,
    vehicle_types: list[VehicleType],
    top_n: int = 5,
) -> list[tuple[str, float]]:
    """Return the most similar vehicle types excluding the query type itself."""
    by_name = {vehicle_type.name: vehicle_type for vehicle_type in vehicle_types}
    if vehicle_type_name not in by_name:
        raise ValueError(f"Unknown vehicle type: {vehicle_type_name!r}.")

    query_vector = get_vehicle_type_feature_vector(by_name[vehicle_type_name])
    results: list[tuple[str, float]] = []

    for name, vehicle_type in sorted(by_name.items()):
        if name == vehicle_type_name:
            continue
        vector = get_vehicle_type_feature_vector(vehicle_type)
        distance = _euclidean_distance(query_vector, vector)
        results.append((name, distance_to_similarity_score(distance)))

    results.sort(key=lambda item: (-item[1], item[0]))
    return results[:top_n]
