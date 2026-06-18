"""Stock market rate timeline from TurnEvents data."""

from __future__ import annotations

from dataclasses import dataclass

from gearcity_optimizer.importers.map_sources import MapSource
from gearcity_optimizer.importers.turn_events_parser import (
    TurnEventsTimeline,
    load_turn_events_for_map,
)

STOCK_MARKET_BASE = 1.0
_BASE_EPSILON = 1e-9


@dataclass(frozen=True)
class StockMarketTurn:
    """Effective stock market multiplier for one timeline turn."""

    year: int
    turn: int
    stockrate: float
    delta_from_base: float
    delta_from_previous: float | None
    explicit_update: bool


def _is_base_rate(value: float, base: float = STOCK_MARKET_BASE) -> bool:
    return abs(value - base) < _BASE_EPSILON


def build_stock_market_timeline(
    timeline: TurnEventsTimeline,
    *,
    base: float = STOCK_MARKET_BASE,
) -> list[StockMarketTurn]:
    """List turns where the effective stock market rate is not at base."""
    turns = sorted(timeline.turns, key=lambda event: (event.year, event.turn))

    current_rate: float | None = None
    previous_effective: float | None = None
    rows: list[StockMarketTurn] = []

    for event in turns:
        explicit_update = event.stockrate is not None
        if explicit_update:
            current_rate = event.stockrate
        elif current_rate is None:
            current_rate = base

        effective = current_rate if current_rate is not None else base
        if _is_base_rate(effective, base):
            previous_effective = effective
            continue

        delta_previous = None
        if previous_effective is not None:
            delta_previous = effective - previous_effective

        rows.append(
            StockMarketTurn(
                year=event.year,
                turn=event.turn,
                stockrate=effective,
                delta_from_base=effective - base,
                delta_from_previous=delta_previous,
                explicit_update=explicit_update,
            )
        )
        previous_effective = effective

    return rows


def stock_market_timeline_for_map(map_source: MapSource) -> list[StockMarketTurn]:
    """Load a map and build its non-base stock market timeline."""
    timeline = load_turn_events_for_map(map_source)
    return build_stock_market_timeline(timeline)


def format_stockrate(value: float) -> str:
    """Format a stock market rate for display."""
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text if text else "0"


def format_rate_delta(value: float | None) -> str:
    """Format a rate change versus base or the previous turn."""
    if value is None:
        return ""
    text = f"{value:+.6f}".rstrip("0").rstrip(".")
    if not text or text in {"+", "-"}:
        return "0"
    return text
