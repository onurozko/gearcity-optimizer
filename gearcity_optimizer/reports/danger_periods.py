"""Detect map-specific economic danger periods from TurnEvents timelines."""

from __future__ import annotations

from dataclasses import dataclass

from gearcity_optimizer.importers.map_sources import MapSource
from gearcity_optimizer.importers.turn_events_parser import (
    TurnEvent,
    TurnEventsTimeline,
    load_turn_events_for_map,
)

PANIC_IMAGE_KEYWORDS = ("panic", "crash", "depression", "recession")


@dataclass(frozen=True)
class DangerPeriod:
    """A contiguous map-specific period of elevated economic risk."""

    map_id: str
    map_name: str
    start_year: int
    start_turn: int
    end_year: int
    end_turn: int
    danger_type: str
    severity: str
    label: str
    supporting_events: list[str]


def _turn_label(event: TurnEvent) -> str:
    return f"{event.year} turn {event.turn}"


def _severity_for_buyrate(value: float) -> str:
    if value < 0.95:
        return "high"
    if value < 1.0:
        return "medium"
    return "low"


def _severity_for_interest(value: float) -> str:
    if value >= 1.08:
        return "high"
    if value >= 1.05:
        return "medium"
    return "low"


def _severity_for_stockrate(value: float) -> str:
    if value < 0.9:
        return "high"
    if value < 0.97:
        return "medium"
    return "low"


def _is_panic_news(event: TurnEvent) -> bool:
    for comment in event.news_comments:
        image = comment.image.lower()
        if any(keyword in image for keyword in PANIC_IMAGE_KEYWORDS):
            return True
    return False


def _danger_signals_for_turn(event: TurnEvent) -> list[tuple[str, str, str]]:
    """Return (danger_type, severity, label) tuples for one turn."""
    signals: list[tuple[str, str, str]] = []

    if event.buyrate is not None and event.buyrate < 1.0:
        signals.append(
            (
                "weak_buyrate",
                _severity_for_buyrate(event.buyrate),
                f"Weak buyer demand (buyrate {event.buyrate:.4f})",
            )
        )

    if event.interest is not None and event.interest >= 1.04:
        signals.append(
            (
                "high_interest",
                _severity_for_interest(event.interest),
                f"Elevated interest rates ({event.interest:.4f})",
            )
        )

    if event.stockrate is not None and event.stockrate < 0.97:
        signals.append(
            (
                "stock_decline",
                _severity_for_stockrate(event.stockrate),
                f"Weak stock market (stockrate {event.stockrate:.4f})",
            )
        )

    if _is_panic_news(event):
        signals.append(
            (
                "economic_panic",
                "high",
                "Historical panic or crash news event",
            )
        )

    return signals


def _merge_periods(
    *,
    map_id: str,
    map_name: str,
    danger_type: str,
    events: list[TurnEvent],
    labels: list[str],
    severities: list[str],
) -> DangerPeriod:
    severity_rank = {"low": 0, "medium": 1, "high": 2}
    severity = max(severities, key=lambda item: severity_rank[item])
    unique_labels = list(dict.fromkeys(labels))
    return DangerPeriod(
        map_id=map_id,
        map_name=map_name,
        start_year=events[0].year,
        start_turn=events[0].turn,
        end_year=events[-1].year,
        end_turn=events[-1].turn,
        danger_type=danger_type,
        severity=severity,
        label=unique_labels[0],
        supporting_events=[_turn_label(event) for event in events],
    )


def detect_danger_periods(timeline: TurnEventsTimeline) -> list[DangerPeriod]:
    """Find contiguous danger periods for one parsed map timeline."""
    map_id = timeline.map_id or "unknown"
    map_name = timeline.map_name or "Unknown map"

    periods: list[DangerPeriod] = []
    active: dict[str, dict[str, object]] = {}

    for event in timeline.turns:
        signals = _danger_signals_for_turn(event)
        signal_types = {signal[0] for signal in signals}

        for danger_type, bucket in list(active.items()):
            if danger_type not in signal_types:
                events = bucket["events"]  # type: ignore[assignment]
                periods.append(
                    _merge_periods(
                        map_id=map_id,
                        map_name=map_name,
                        danger_type=danger_type,
                        events=events,  # type: ignore[arg-type]
                        labels=bucket["labels"],  # type: ignore[arg-type]
                        severities=bucket["severities"],  # type: ignore[arg-type]
                    )
                )
                del active[danger_type]

        for danger_type, severity, label in signals:
            if danger_type in active:
                bucket = active[danger_type]
                bucket["events"].append(event)  # type: ignore[union-attr]
                bucket["labels"].append(label)  # type: ignore[union-attr]
                bucket["severities"].append(severity)  # type: ignore[union-attr]
            else:
                active[danger_type] = {
                    "events": [event],
                    "labels": [label],
                    "severities": [severity],
                }

    for danger_type, bucket in active.items():
        periods.append(
            _merge_periods(
                map_id=map_id,
                map_name=map_name,
                danger_type=danger_type,
                events=bucket["events"],  # type: ignore[arg-type]
                labels=bucket["labels"],  # type: ignore[arg-type]
                severities=bucket["severities"],  # type: ignore[arg-type]
            )
        )

    periods.sort(
        key=lambda item: (item.start_year, item.start_turn, item.danger_type)
    )
    return periods


def danger_periods_for_map(map_source: MapSource) -> list[DangerPeriod]:
    """Load a map source and detect danger periods."""
    timeline = load_turn_events_for_map(map_source)
    return detect_danger_periods(timeline)


def summarize_timeline(timeline: TurnEventsTimeline) -> dict[str, object]:
    """Return a compact summary for CLI output."""
    years = sorted({event.year for event in timeline.turns})
    turns_with_news = sum(1 for event in timeline.turns if event.news_comments)
    turns_with_world = sum(1 for event in timeline.turns if event.city_changes)
    turns_with_economy = sum(
        1
        for event in timeline.turns
        if any(
            value is not None
            for value in (
                event.buyrate,
                event.stockrate,
                event.interest,
                event.gas,
                event.carprice,
            )
        )
    )
    return {
        "map_id": timeline.map_id,
        "map_name": timeline.map_name,
        "turn_count": len(timeline.turns),
        "year_start": years[0] if years else None,
        "year_end": years[-1] if years else None,
        "turns_with_news": turns_with_news,
        "turns_with_world_events": turns_with_world,
        "turns_with_economy": turns_with_economy,
    }
