"""Candidate ranking by scoring objective."""

from __future__ import annotations

from gearcity_optimizer.core.models import CandidateDesign, VehicleType
from gearcity_optimizer.core.scoring import calculate_value_score

VALID_OBJECTIVES = ("best_fit", "buyer_rating", "value", "balanced")


def _normalize_column(values: list[float]) -> list[float]:
    """Normalize values to 0–1; equal values all receive 1.0."""
    if not values:
        return []
    min_val = min(values)
    max_val = max(values)
    if min_val == max_val:
        return [1.0] * len(values)
    span = max_val - min_val
    return [(v - min_val) / span for v in values]


def rank_candidates(
    candidates: list[CandidateDesign],
    vehicle_types: dict[str, VehicleType],
    vehicle_type_name: str | None = None,
    year: int = 1901,
    objective: str = "balanced",
) -> list[dict]:
    """
    Rank candidate designs by the chosen objective.

    Args:
        candidates: designs to evaluate
        vehicle_types: lookup of vehicle type definitions
        vehicle_type_name: if set, only rank candidates of this type
        year: simulation year for penalties and buyer rating
        objective: one of best_fit, buyer_rating, value, balanced

    Returns:
        List of result dicts sorted by rank (1 = best).
    """
    if objective not in VALID_OBJECTIVES:
        raise ValueError(
            f"Invalid objective {objective!r}. "
            f"Choose from: {', '.join(VALID_OBJECTIVES)}"
        )

    filtered = candidates
    if vehicle_type_name is not None:
        filtered = [c for c in candidates if c.vehicle_type == vehicle_type_name]

    rows: list[dict] = []
    for candidate in filtered:
        vehicle_type = vehicle_types.get(candidate.vehicle_type)
        if vehicle_type is None:
            continue

        score = calculate_value_score(candidate, vehicle_type, year=year)
        rows.append(
            {
                "name": candidate.name,
                "vehicle_type": candidate.vehicle_type,
                "vehicle_type_fit": score.vehicle_type_fit,
                "buyer_rating_proxy_before_penalties": (
                    score.buyer_rating_proxy_before_penalties
                ),
                "final_buyer_rating_proxy": score.final_buyer_rating_proxy,
                "value_per_cost": score.value_per_cost,
                "unit_cost": candidate.unit_cost,
                "sale_price": candidate.sale_price,
                "penalty_multiplier": score.penalty_multiplier,
                "warnings": score.warnings,
                "notes": candidate.notes,
            }
        )

    if objective == "balanced" and rows:
        fits = [r["vehicle_type_fit"] for r in rows]
        ratings = [r["final_buyer_rating_proxy"] for r in rows]
        values = [r["value_per_cost"] for r in rows]

        norm_fits = _normalize_column(fits)
        norm_ratings = _normalize_column(ratings)
        norm_values = _normalize_column(values)

        for i, row in enumerate(rows):
            row["balanced_score"] = (
                0.35 * norm_fits[i]
                + 0.45 * norm_ratings[i]
                + 0.20 * norm_values[i]
            )

    sort_key = {
        "best_fit": lambda r: r["vehicle_type_fit"],
        "buyer_rating": lambda r: r["final_buyer_rating_proxy"],
        "value": lambda r: r["value_per_cost"],
        "balanced": lambda r: r["balanced_score"],
    }[objective]

    rows.sort(key=sort_key, reverse=True)

    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank

    return rows
